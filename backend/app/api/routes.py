"""
API路由
"""
from flask import jsonify
from . import api_bp

# 导入子模块路由
from . import cluster_routes
from . import instance_routes
from . import volume_routes
from . import network_routes
from . import network_topology_routes
from . import router_routes
from . import security_group_routes
from . import snapshot_routes
from . import user_routes
from . import image_routes

@api_bp.route('/health')
def health_check():
    return jsonify({'status': 'ok', 'message': '系统运行正常'})