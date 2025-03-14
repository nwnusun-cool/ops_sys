from flask import Blueprint, request, jsonify, send_file
from datetime import datetime

from flask.scaffold import F
from models.openstack_manager import OpenstackManager
from utils.error_handler import error_handler
from utils.cache import cache_with_timeout
from utils.performance_logger import performance_logger
from config.loadconfig import CLOUDS,SECRET_KEY
import logging
import io

instances_bp = Blueprint('instances', __name__)
logger = logging.getLogger(__name__)

manager = OpenstackManager(CLOUDS)
@instances_bp.route("/list", methods=["GET"])
@error_handler
def list_instances():
    """
    查询实例列表
    """
    manager = OpenstackManager(CLOUDS)
    cloud_name = request.args.get("cloud_name")
    if not cloud_name:
        raise ValueError("Missing cloud_name parameter")

    logger.info(f"Received request with parameters: {request.args}")

    filters = {
        "status": request.args.get("status"),
        "instance_type": request.args.get("instance_type"),
        "ip": request.args.get("ip"),
        "created_date": request.args.get("created_date"),
        "name": request.args.get("name"),
        "page": request.args.get("page", "1"),
        "per_page": request.args.get("per_page", "10"),
        "sort_by": request.args.get("sort_by"),
        "sort_order": request.args.get("sort_order", "desc"),
    }

    logger.info(f"Applied filters: {filters}")

    result = manager.search_instances(cloud_name, filters)

    logger.info(f"Found {result['total']} instances after filtering")

    return jsonify({"status": "success", **result})



@instances_bp.route("/export", methods=["GET"])
@error_handler
def export_instances():
    """导出实例数据"""
    cloud_name = request.args.get("cloud_name")
    logger.info(f"Received request to export instances for cloud: {cloud_name}")
    if not cloud_name:
        raise ValueError("Missing cloud_name parameter")

    format = request.args.get("format", "excel")
    filters = {
        "status": request.args.get("status"),
        "instance_type": request.args.get("instance_type"),
        "ip": request.args.get("ip"),
        "created_date": request.args.get("created_date"),
        "name": request.args.get("name"),
    }

    output = manager.export_instances(cloud_name, filters, format)

    if format == "excel":
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f'instances_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.xlsx',
        )
    else:
        return send_file(
            # io.BytesIO(output.encode()),
            output,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f'instances_{cloud_name}_{datetime.now().strftime("%Y%m%d")}.csv',
        )


@instances_bp.route("/<cloud_name>/<instance_id>", methods=["GET"])
@error_handler
def get_instance(cloud_name, instance_id):
    """获取实例详情"""
    instance = manager.get_instance_details(cloud_name, instance_id)
    return jsonify({"status": "success", "data": instance})


@instances_bp.route("/<cloud_name>/<instance_id>/<action>", methods=["POST"])
@error_handler
def perform_instance_action(cloud_name, instance_id, action):
    """执行实例操作"""
    try:
        # 如果是删除操作，验证token
        if action == "delete":
            import jwt  # 导入 jwt 模块
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return jsonify({"status": "error", "message": "缺少授权token"}), 401

            token = auth_header.split(" ")[1]
            try:
                jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return jsonify({"status": "error", "message": "删除授权已过期"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"status": "error", "message": "无效的删除授权"}), 401

        result = manager.perform_action(cloud_name, instance_id, action)
        return jsonify({"status": "success", "message": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500