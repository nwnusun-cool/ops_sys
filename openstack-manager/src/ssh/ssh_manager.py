import asyncio
import json
import paramiko
import websockets
import logging
from base64 import b64decode

logger = logging.getLogger(__name__)


class SSHManager:
    def __init__(self):
        self.clients = {}

    async def handle_websocket(self, websocket, path):
        """处理WebSocket连接"""
        try:
            # 等待接收连接信息
            connection_data = await websocket.recv()
            conn_info = json.loads(connection_data)

            # 创建SSH客户端
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                # 连接到服务器
                ssh.connect(
                    hostname=conn_info["host"],
                    port=int(conn_info.get("port", 22)),
                    username=conn_info["username"],
                    password=conn_info.get("password"),
                    key_filename=conn_info.get("key_path"),
                )

                # 获取Shell通道
                channel = ssh.invoke_shell(term="xterm")
                channel.setblocking(0)

                # 存储客户端信息
                client_id = id(websocket)
                self.clients[client_id] = {
                    "ssh": ssh,
                    "channel": channel,
                    "websocket": websocket,
                }

                try:
                    while True:
                        # 检查SSH通道是否可读
                        if channel.recv_ready():
                            data = channel.recv(1024)
                            if data:
                                await websocket.send(
                                    data.decode("utf-8", errors="ignore")
                                )

                        # 检查WebSocket是否有数据
                        try:
                            data = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                            if data:
                                channel.send(data)
                        except asyncio.TimeoutError:
                            pass

                        # 检查通道是否关闭
                        if channel.exit_status_ready():
                            break

                except websockets.exceptions.ConnectionClosed:
                    logger.info("WebSocket connection closed")

            except paramiko.AuthenticationException:
                await websocket.send(json.dumps({"error": "Authentication failed"}))
            except Exception as e:
                logger.error(f"SSH connection error: {str(e)}")
                await websocket.send(
                    json.dumps({"error": f"Connection failed: {str(e)}"})
                )

        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
        finally:
            # 清理连接
            client_id = id(websocket)
            if client_id in self.clients:
                client = self.clients[client_id]
                if "channel" in client:
                    client["channel"].close()
                if "ssh" in client:
                    client["ssh"].close()
                del self.clients[client_id]

    def start_server(self, host="0.0.0.0", port=8765):
        """启动WebSocket服务器"""
        return websockets.serve(self.handle_websocket, host, port)
