from flask import Blueprint, request, jsonify
from models.ssh_model import Database, SSHConnection
from utils.error_handler import error_handler
import paramiko
import logging

ssh_bp = Blueprint('ssh', __name__)
logger = logging.getLogger(__name__)
db = Database()
@ssh_bp.route("/connections", methods=["GET"])
@error_handler
def get_ssh_connections(db):
    connections = db.get_all_connections()
    return jsonify({"status": "success", "data": connections})

# 其他 SSH 相关路由方法保持不变，此处省略...
@ssh_bp.route("/api/ssh/connections", methods=["POST"])
@error_handler
def add_ssh_connection():
    """添加新的SSH连接"""
    data = request.json
    if data is None:
        raise ValueError("Missing JSON data in the request")
    required_fields = ["name", "host", "username", "password"]
    for field in required_fields:
        if data is None or field not in data:
            raise ValueError(f"Missing required field: {field}")

    # 假设 db 是 Database 类的实例，需要在函数中获取或创建
    connection_id = db.add_connection(
        name=data["name"],
        host=data["host"],
        username=data["username"],
        password=data["password"],
        port=int(data.get("port", 22)),
        description=data.get("description", ""),
    )
    return jsonify({"status": "success", "id": connection_id})


@ssh_bp.route("/api/ssh/connections/<int:connection_id>", methods=["PUT"])
@error_handler
def update_ssh_connection(connection_id):
    """更新SSH连接"""
    data = request.json
    if data is None:
        raise ValueError("Missing JSON data in the request")
    required_fields = ["name", "host", "username", "password"]
    for field in required_fields:
        if field not in data:
            raise ValueError(f"Missing required field: {field}")

    db.update_connection(
        connection_id=connection_id,
        name=data["name"],
        host=data["host"],
        username=data["username"],
        password=data["password"],
        port=int(data.get("port", 22)),
        description=data.get("description", ""),
    )
    return jsonify({"status": "success"})


@ssh_bp.route("/api/ssh/connections/<int:connection_id>", methods=["DELETE"])
@error_handler
def delete_ssh_connection(connection_id):
    """删除SSH连接"""
    db.delete_connection(connection_id)
    return jsonify({"status": "success"})


@ssh_bp.route("/api/ssh/test-connection", methods=["POST"])
@error_handler
def test_ssh_connection():
    """测试SSH连接"""
    data = request.json
    if data is None:
        raise ValueError("Missing JSON data in the request")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 设置超时时间
        ssh.connect(
            hostname=data["host"],
            port=int(data.get("port", 22)),
            username=data["username"],
            password=data["password"],
            timeout=5,
        )

        # 测试执行简单命令
        stdin, stdout, stderr = ssh.exec_command('echo "Connection test successful"')
        output = stdout.read().decode()
        logger.warning(f"SSH连接测试输出：{output}")
        ssh.close()
        return jsonify({"status": "success", "message": "SSH连接测试成功！"})
    except paramiko.AuthenticationException:
        return (
            jsonify({"status": "error", "message": "认证失败：用户名或密码错误"}),
            401,
        )
    except paramiko.SSHException as e:
        return jsonify({"status": "error", "message": f"SSH连接错误：{str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"连接测试失败：{str(e)}"}), 500
