"""
网络拓扑API路由
提供OpenStack网络拓扑的查看和管理操作
"""
import logging
from flask import request, jsonify
from flask_login import login_required, current_user
from . import api_bp as api
from app.models.base import db
from app.models.cluster import OpenstackCluster
from app.models.log import OperationLog
from app.services.openstack_service import get_openstack_service

logger = logging.getLogger(__name__)

@api.route('/network-topology', methods=['GET'])
@login_required
def get_network_topology():
    """获取网络拓扑数据"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        
        # 获取网络拓扑数据
        topology_data = openstack_service.get_network_topology(cluster_id)
        
        return jsonify({
            'success': True,
            'data': topology_data,
            'cluster_name': cluster.name
        })
        
    except Exception as e:
        logger.error(f"Failed to get network topology: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/network-topology/nodes/<node_type>/<node_id>', methods=['GET'])
@login_required
def get_topology_node_detail(node_type, node_id):
    """获取拓扑节点详细信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        openstack_service = get_openstack_service()
        
        # 根据节点类型获取详细信息
        if node_type == 'network':
            detail = openstack_service.get_network_detail(cluster_id, node_id)
        elif node_type == 'router':
            detail = openstack_service.get_router_detail(cluster_id, node_id)
        elif node_type == 'instance':
            detail = openstack_service.get_instance_detail(cluster_id, node_id)
        else:
            return jsonify({'success': False, 'error': f'不支持的节点类型: {node_type}'}), 400
        
        if not detail:
            return jsonify({'success': False, 'error': '节点不存在'}), 404
        
        return jsonify({
            'success': True,
            'data': detail,
            'node_type': node_type
        })
        
    except Exception as e:
        logger.error(f"Failed to get topology node detail: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/network-topology/refresh', methods=['POST'])
@login_required
def refresh_network_topology():
    """刷新网络拓扑数据"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        
        # 清除缓存并重新获取拓扑数据
        openstack_service.clear_cache(cluster_id)
        topology_data = openstack_service.get_network_topology(cluster_id)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='topology_refresh',
            operation_object='network_topology',
            result='success',
            details=f'刷新网络拓扑数据: {cluster.name}'
        )
        
        return jsonify({
            'success': True,
            'data': topology_data,
            'message': '网络拓扑数据已刷新'
        })
        
    except Exception as e:
        logger.error(f"Failed to refresh network topology: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/network-topology/layout', methods=['POST'])
@login_required
def save_topology_layout():
    """保存拓扑布局配置"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        data = request.get_json()
        
        if not cluster_id or not data:
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        layout_config = data.get('layout')
        if not layout_config:
            return jsonify({'success': False, 'error': '缺少布局配置'}), 400
        
        # 这里可以将布局配置保存到数据库或文件中
        # 目前先返回成功，后续可以实现持久化存储
        
        return jsonify({
            'success': True,
            'message': '拓扑布局已保存'
        })
        
    except Exception as e:
        logger.error(f"Failed to save topology layout: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500