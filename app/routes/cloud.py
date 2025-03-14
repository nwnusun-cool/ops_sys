from flask import Blueprint, request, jsonify
from utils.error_handler import error_handler
from utils.cache import cache_with_timeout
from config.loadconfig import CLOUDS,SECRET_KEY,SECURITY,CORRECT_PASSWORD

import paramiko
import logging
import time
import jwt

index_bp = Blueprint('index', __name__)
logger = logging.getLogger(__name__)

@index_bp.route("/api/cloud/verify-delete-password", methods=["POST"])
@error_handler
def verify_delete_password():
    """验证删除密码"""
    try:
        data = request.get_json()
        if not data or "password" not in data:
            raise ValueError("Missing password")

        # 获取输入的密码和配置的密码
        input_password = data["password"]
        correct_password = SECURITY.get("delete_password")

        # 添加调试日志
        logger.warning(f"real password: {correct_password}")
        logger.warning(f"reciver password: {input_password}")
        logger.warning(f"real password type: {type(correct_password)}")
        logger.warning(f"reciver password type: {type(input_password)}")

        if not correct_password:
            logger.error("Delete password not configured in config file")
            raise ValueError("Delete password not configured")

        # 将两个密码都转换为字符串进行比较
        if str(input_password) == str(correct_password):
            return jsonify(
                {
                    "status": "success",
                    "message": "密码验证成功",
                    "token": generate_delete_token(),
                }
            )
        else:
            logger.warning(f"Invalid delete password attempt")
            return jsonify({"status": "error", "message": "删除密码错误"}), 401

    except ValueError as e:
        logger.error(f"Password verification error: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error in password verification: {str(e)}")
        return jsonify({"status": "error", "message": "密码验证失败"}), 500



def generate_delete_token():
    """生成删除操作的临时token"""
    try:
        expires = time.time() + int(SECURITY.get("delete_password_expires", 3600))
        return jwt.encode(
            {"exp": expires},
            SECRET_KEY,
            algorithm="HS256",
        )
    except Exception as e:
        logger.error(f"Error generating delete token: {str(e)}")
        raise


    # 优化云环境列表接口
# 这里应该使用之前定义的蓝图 index_bp 而不是未定义的 app
@index_bp.route("/list", methods=["GET"])
@error_handler
@cache_with_timeout(timeout=300)
def list_clouds():
    """获取云环境列表"""
    return jsonify({"status": "success", "data": list(CLOUDS.keys())})

# 优化环境列表接口
@index_bp.route("/environments", methods=["GET"])
@error_handler
@cache_with_timeout(timeout=300)
def list_environments():
    """获取所有 OpenStack 环境"""
    environments = list(CLOUDS.keys())
    return jsonify({"status": "success", "data": environments})


@index_bp.route('/check-password', methods=['POST'])
@error_handler
def check_password():
    data = request.get_json()
    # 检查 data 是否为 None
    if data is None:
        return jsonify({'status': 'error', 'message': '请求数据为空'}), 400
    password = data.get('password')

    if password == CORRECT_PASSWORD:
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': '密码错误'}), 401