import sqlite3
import json
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import os
import logging
import paramiko
import time
import asyncio
import websockets
import threading
from queue import Queue
import functools

logger = logging.getLogger(__name__)


# 添加缓存装饰器
def cache_with_timeout(timeout=300):  # 5分钟缓存
    def decorator(f):
        cache = {}

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            now = time.time()

            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < timeout:
                    return result

            result = f(*args, **kwargs)
            cache[key] = (result, now)
            return result

        return wrapper

    return decorator


class Database:
    _instance = None
    _conn = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.db_file = os.path.join("database", "ssh_connections.db")
            self._init_db()
            self.initialized = True

    def _get_connection(self):
        """获取数据库连接（使用连接池）"""
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_file, check_same_thread=False, timeout=30
            )
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        """初始化数据库"""
        try:
            os.makedirs(os.path.dirname(self.db_file), exist_ok=True)
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS ssh_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER DEFAULT 22,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        except Exception as e:
            logger.error(f"Database initialization error: {str(e)}")
            raise

    def __del__(self):
        """析构函数，确保关闭数据库连接"""
        if hasattr(self, "_conn") and self._conn:
            self._conn.close()

    def _get_or_create_key(self):
        """获取或创建加密密钥"""
        key_file = "../../ssh_key.key"
        if os.path.exists(key_file):
            with open(key_file, "rb") as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(key_file, "wb") as f:
                f.write(key)
            return key

    def _encrypt_password(self, password):
        """加密密码"""
        return self.cipher.encrypt(password.encode()).decode()

    def _decrypt_password(self, encrypted_password):
        """解密密码"""
        return self.cipher.decrypt(encrypted_password.encode()).decode()

    def get_connection(self):
        """获取数据库连接"""
        return self._conn

    def add_connection(self, name, host, username, password, port=22, description=""):
        """添加新的SSH连接"""
        try:
            cursor = self.get_connection().cursor()
            cursor.execute(
                """
                INSERT INTO ssh_connections 
                (name, host, username, password, port, description) 
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, host, username, password, port, description),
            )
            self.get_connection().commit()
            return cursor.lastrowid
        except Exception as e:
            self.get_connection().rollback()
            raise e

    # @cache_with_timeout(timeout=60)
    def get_all_connections(self):
        """获取所有SSH连接信息（带缓存）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, name, host, port, username, description, 
                           created_at, updated_at 
                    FROM ssh_connections
                """
                )

                columns = [description[0] for description in cursor.description]
                result = []
                for row in cursor.fetchall():
                    connection_dict = dict(zip(columns, row))
                    # 不返回密码字段
                    if "password" in connection_dict:
                        del connection_dict["password"]
                    result.append(connection_dict)

                return result

        except Exception as e:
            logger.error(f"Error getting connections: {str(e)}")
            return []

    def get_connection_by_id(self, connection_id):
        """根据ID获取单个SSH连接信息"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM ssh_connections WHERE id = ?", (connection_id,)
                )

                # 获取列名
                columns = [description[0] for description in cursor.description]

                # 获取行数据
                row = cursor.fetchone()

                # 如果找到数据，转换为字典
                if row:
                    return dict(zip(columns, row))
                return None

        except Exception as e:
            logger.error(f"Error getting connection by id {connection_id}: {str(e)}")
            return None

    def update_connection(
        self, connection_id, name, host, username, password, port=22, description=""
    ):
        """更新SSH连接"""
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE ssh_connections 
                SET name=?, host=?, port=?, username=?, password=?, description=?, updated_at=?
                WHERE id=?
            """,
                (
                    name,
                    host,
                    port,
                    username,
                    password,
                    description,
                    datetime.now(),
                    connection_id,
                ),
            )

    def delete_connection(self, connection_id):
        """删除SSH连接"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM ssh_connections WHERE id = ?", (connection_id,))


class SSHConnection:
    def __init__(self):
        self.connections = {}
        self.ws_connections = {}
        self.message_queues = {}
        self.loop = None

    async def ws_handler(self, websocket, path):
        """处理WebSocket连接"""
        connection_id = None
        try:
            message = await websocket.recv()
            data = json.loads(message)

            if data.get("action") == "connect":
                connection_info = {
                    "id": data["connection_id"],
                    "host": data["host"],
                    "port": int(data["port"]),
                    "username": data["username"],
                    "password": data["password"],
                }

                result = self.connect_and_get_shell(connection_info)
                if result["status"] == "success":
                    connection_id = str(data["connection_id"])
                    self.ws_connections[connection_id] = websocket

                    # 发送初始输出
                    if "initial_output" in result:
                        await websocket.send(
                            json.dumps(
                                {"type": "output", "data": result["initial_output"]}
                            )
                        )

                    while True:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)

                            if data["type"] == "input":
                                shell = self.connections[connection_id]["shell"]
                                shell.send(data["data"])

                                # 等待输出
                                await asyncio.sleep(0.1)

                                # 读取输出
                                while shell.recv_ready():
                                    output = shell.recv(4096).decode(
                                        "utf-8", errors="ignore"
                                    )
                                    if output:
                                        await websocket.send(
                                            json.dumps(
                                                {"type": "output", "data": output}
                                            )
                                        )

                        except websockets.exceptions.ConnectionClosed:
                            break

                else:
                    await websocket.send(
                        json.dumps({"type": "error", "message": result["message"]})
                    )

        except Exception as e:
            logger.error(f"WebSocket处理错误: {str(e)}")
            try:
                await websocket.send(
                    json.dumps({"type": "error", "message": f"连接错误: {str(e)}"})
                )
            except:
                pass

        finally:
            if connection_id:
                self.close_connection(connection_id)
                if connection_id in self.ws_connections:
                    del self.ws_connections[connection_id]

    def start_server(self, host="0.0.0.0", port=8765):
        """启动WebSocket服务器"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

            start_server = websockets.serve(self.ws_handler, host, port, loop=self.loop)

            self.loop.run_until_complete(start_server)
            logger.info(f"WebSocket server started on ws://{host}:{port}")

            return start_server

        except Exception as e:
            logger.error(f"启动WebSocket服务器失败: {str(e)}")
            raise

    def run_server(self):
        """在新线程中运行WebSocket服务器"""
        try:
            if self.loop and self.loop.is_running():
                return

            self.start_server()
            self.loop.run_forever()

        except Exception as e:
            logger.error(f"运行WebSocket服务器失败: {str(e)}")
            raise

    def connect_and_get_shell(self, connection_info):
        """建立SSH连接并返回shell会话"""
        try:
            # 创建SSH客户端
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # 建立连接
            ssh.connect(
                hostname=connection_info["host"],
                port=connection_info["port"],
                username=connection_info["username"],
                password=connection_info["password"],
                timeout=10,
            )

            # 获取交互式shell
            shell = ssh.invoke_shell(term="xterm", width=120, height=30)

            # 设置非阻塞模式
            shell.setblocking(0)

            # 存储连接信息
            connection_id = str(connection_info["id"])
            self.connections[connection_id] = {
                "client": ssh,
                "shell": shell,
                "last_active": time.time(),
            }

            # 等待初始提示符
            time.sleep(1)
            initial_output = shell.recv(4096).decode("utf-8", errors="ignore")

            return {
                "status": "success",
                "message": "连接成功",
                "connection_id": connection_id,
                "initial_output": initial_output,
            }

        except Exception as e:
            logger.error(f"SSH连接错误: {str(e)}")
            return {"status": "error", "message": f"连接失败: {str(e)}"}

    def read_shell_output(self, connection_id):
        """读取shell输出"""
        try:
            connection = self.connections.get(str(connection_id))
            if not connection:
                return {"status": "error", "message": "连接不存在"}

            shell = connection["shell"]
            output = ""

            # 读取所有可用输出
            while shell.recv_ready():
                output += shell.recv(4096).decode("utf-8", errors="ignore")

            return {"status": "success", "data": output}

        except Exception as e:
            logger.error(f"读取shell输出错误: {str(e)}")
            return {"status": "error", "message": f"读取输出失败: {str(e)}"}

    def write_to_shell(self, connection_id, command):
        """向shell写入命令"""
        try:
            connection = self.connections.get(str(connection_id))
            if not connection:
                return {"status": "error", "message": "连接不存在"}

            shell = connection["shell"]
            shell.send(command + "\n")

            # 等待输出
            time.sleep(0.1)

            return {"status": "success", "message": "命令已发送"}

        except Exception as e:
            logger.error(f"发送命令错误: {str(e)}")
            return {"status": "error", "message": f"发送命令失败: {str(e)}"}

    def close_connection(self, connection_id):
        """关闭SSH连接"""
        try:
            connection = self.connections.get(str(connection_id))
            if connection:
                connection["shell"].close()
                connection["client"].close()
                del self.connections[str(connection_id)]

            return {"status": "success", "message": "连接已关闭"}

        except Exception as e:
            logger.error(f"关闭连接错误: {str(e)}")
            return {"status": "error", "message": f"关闭连接失败: {str(e)}"}
