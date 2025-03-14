from flask import Blueprint, request, jsonify, send_file
from models.openstack_manager import OpenstackManager
from utils.error_handler import error_handler
from utils.cache import cache_with_timeout
from utils.performance_logger import performance_logger
import logging
from flask import request, jsonify
import jwt
from config.loadconfig import CLOUDS,SECRET_KEY,SECURITY
from flask import current_app as app
from datetime import datetime  # 添加datetime导入
import io  # 确保io模块被导入

manager = OpenstackManager(CLOUDS)
volumes_bp = Blueprint('volumes', __name__)
logger = logging.getLogger(__name__)

@volumes_bp.route("/list", methods=["GET"])
@error_handler
def get_volumes():
    cloud_name = request.args.get("cloud_name")
    name = request.args.get("name", "")
    status = request.args.get("status", "")
    size = request.args.get("size", "")
    volume_type = request.args.get("type", "")

    # 分页参数处理
    def safe_int(value, default):
        if not value or value == "undefined" or value == "null":
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    page = safe_int(request.args.get("page"), 1)
    per_page = safe_int(request.args.get("per_page"), 10)
    sort_by = request.args.get("sort_by") or "created_at"
    sort_order = request.args.get("sort_order") or "desc"

    logger.info(
        f"Processing volume request with: page={page}, per_page={per_page}, sort_by={sort_by}, sort_order={sort_order}"
    )

    result = manager.search_volumes(
        cloud_name,
        {
            "name": name,
            "status": status,
            "size": size,
            "type": volume_type,
            "page": page,
            "per_page": per_page,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )
    logger.info(f"Found {len(result.get('data', []))} volumes after filtering")
    return jsonify({"status": "success", **result})

# 其他卷相关路由方法保持不变，此处省略...

@volumes_bp.route("/<cloud_name>/<volume_id>", methods=["GET"])
@error_handler
def get_volume(cloud_name, volume_id):
    """获取卷详情"""
    volume = manager.get_volume_details(cloud_name, volume_id)
    return jsonify({"status": "success", "data": volume})

@volumes_bp.route("/export", methods=["GET"])
@error_handler
def export_volumes():
    """导出卷数据"""
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("Missing cloud_name parameter")

    format = request.args.get("format", "excel")
    filters = {
        "name": request.args.get("name"),
        "status": request.args.get("status"),
        "size": request.args.get("size"),
        "type": request.args.get("type"),
    }

    output = manager.export_volumes(cloud_name, filters, format)

    if format == "excel":
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f'volumes_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.xlsx',
        )
    else:
        return send_file(
            io.BytesIO(output.encode()),
            mimetype="text/csv",
            as_attachment=True,
            download_name=f'volumes_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.csv',
        )

@volumes_bp.route("/verify-delete-password", methods=["POST"])
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
                    "token": generate_delete_token(str(input_password)),
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


def generate_delete_token(generate_delete_token:str):
    """生成删除操作的临时token"""
    try:
        import time
        expires = time.time() + int(SECURITY.get("delete_password_expires", 3600))
        return jwt.encode(
            {"exp": expires},
            generate_delete_token,
            algorithm="HS256",
        )
    except Exception as e:
        logger.error(f"Error generating delete token: {str(e)}")
        raise



@volumes_bp.route("/<cloud_name>/<volume_id>/<action>", methods=["POST"])
@error_handler
def perform_volume_action(cloud_name, volume_id, action):
    """执行卷操作"""
    data = request.get_json() or {}

    # 如果是删除操作，验证token
    if action == "delete":
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"status": "error", "message": "缺少授权token"}), 401

        token = auth_header.split(" ")[1]
        try:
            jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"status": "error", "message": "删除授权已过期"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"status": "error", "message": "无效的删除授权"}), 401

    result = manager.perform_volume_action(cloud_name, volume_id, action, **data)
    return jsonify({"status": "success", "message": result})