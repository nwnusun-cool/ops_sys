from flask import Blueprint, request, jsonify
from models.openstack_manager import OpenstackManager
from utils.error_handler import error_handler
from config.loadconfig import CLOUDS,SECRET_KEY,SECURITY
import logging

snapshots_bp = Blueprint('snapshots', __name__)
logger = logging.getLogger(__name__)
manager = OpenstackManager(CLOUDS)

@snapshots_bp.route("/create/<cloud_name>/<volume_id>", methods=["POST"])
@error_handler
def create_volume_snapshot(cloud_name, volume_id):
    data = request.get_json()
    # 检查 data 是否为 None
    if data is None:
        return jsonify({'status': 'error', 'message': '请求数据为空'}), 400
    snapshot_name = data.get('name')
    snapshot_description = data.get('description')

    if not snapshot_name:
        return jsonify({'status': 'error', 'message': '快照名称不能为空'}), 400

    try:
        snapshot = manager.create_snapshot(cloud_name, volume_id, snapshot_name, snapshot_description)
        return jsonify({'status': 'success', 'data': snapshot})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 其他快照相关路由方法保持不变，此处省略...
@snapshots_bp.route('/<cloud_name>/<volume_id>/snapshots', methods=['GET'])
def get_volume_snapshots(manager,cloud_name, volume_id): # 假设使用 OpenstackManager，根据实际情况修改
    try:
        snapshots = manager.get_snapshots(cloud_name, volume_id)
        return jsonify({'status': 'success', 'data': snapshots})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@snapshots_bp.route('/api/volumes/<cloud_name>/<volume_id>/snapshots/<snapshot_id>', methods=['DELETE'])
def delete_volume_snapshot(manager,cloud_name, volume_id, snapshot_id):
    try:
        manager.delete_snapshot(cloud_name, snapshot_id)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
