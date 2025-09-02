"""
集群管理API路由
提供集群的CRUD操作和状态管理
"""
import logging
from datetime import datetime
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from . import api_bp as api
from app.models.base import db
from app.models.cluster import OpenstackCluster
from app.models.log import OperationLog
from app.services.openstack_service import openstack_service

logger = logging.getLogger(__name__)

@api.route('/clusters', methods=['GET'])
@login_required
def list_clusters():
    """获取集群列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        
        # 构建查询
        query = OpenstackCluster.query
        if active_only:
            query = query.filter_by(is_active=True)
        
        # 分页
        clusters = query.order_by(OpenstackCluster.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        return jsonify({
            'success': True,
            'data': [cluster.to_dict() for cluster in clusters.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': clusters.total,
                'pages': clusters.pages,
                'has_next': clusters.has_next,
                'has_prev': clusters.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list clusters: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/clusters/<int:cluster_id>', methods=['GET'])
@login_required
def get_cluster(cluster_id):
    """获取单个集群详情"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        # 根据用户权限决定是否包含凭据
        include_credentials = current_user.has_role(['super_admin', 'admin'])
        
        return jsonify({
            'success': True,
            'data': cluster.to_dict(include_credentials=include_credentials)
        })
        
    except Exception as e:
        logger.error(f"Failed to get cluster {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/clusters', methods=['POST'])
@login_required
def create_cluster():
    """创建新集群"""
    # 权限检查
    if not current_user.has_role(['super_admin', 'admin']):
        return jsonify({'success': False, 'error': '权限不足'}), 403
    
    try:
        data = request.get_json()
        
        # 验证必需字段
        required_fields = ['name', 'auth_url', 'credentials']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必需字段: {field}'}), 400
        
        # 检查集群名称是否已存在
        if OpenstackCluster.query.filter_by(name=data['name']).first():
            return jsonify({'success': False, 'error': '集群名称已存在'}), 400
        
        # 创建集群
        cluster = OpenstackCluster(
            name=data['name'],
            description=data.get('description', ''),
            auth_url=data['auth_url'],
            region_name=data.get('region_name', 'RegionOne'),
            api_version=data.get('api_version', '3')
        )
        
        # 设置凭据
        cluster.set_credentials(data['credentials'])
        
        db.session.add(cluster)
        db.session.commit()
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster.id,
            operation_type='cluster_create',
            operation_object=f'cluster:{cluster.name}',
            result='success',
            details=f'创建集群: {cluster.name}'
        )
        
        return jsonify({
            'success': True,
            'message': '集群创建成功',
            'data': cluster.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create cluster: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/clusters/<int:cluster_id>', methods=['PUT'])
@login_required
def update_cluster(cluster_id):
    """更新集群"""
    # 权限检查
    if not current_user.has_role(['super_admin', 'admin']):
        return jsonify({'success': False, 'error': '权限不足'}), 403
    
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        data = request.get_json()
        
        # 更新基本信息
        if 'name' in data:
            # 检查新名称是否冲突
            existing = OpenstackCluster.query.filter_by(name=data['name']).first()
            if existing and existing.id != cluster_id:
                return jsonify({'success': False, 'error': '集群名称已存在'}), 400
            cluster.name = data['name']
        
        if 'description' in data:
            cluster.description = data['description']
        if 'auth_url' in data:
            cluster.auth_url = data['auth_url']
        if 'region_name' in data:
            cluster.region_name = data['region_name']
        if 'api_version' in data:
            cluster.api_version = data['api_version']
        if 'is_active' in data:
            cluster.is_active = data['is_active']
        
        # 更新凭据
        if 'credentials' in data:
            cluster.set_credentials(data['credentials'])
        
        cluster.updated_at = datetime.utcnow()
        db.session.commit()
        
        # 清除相关缓存
        openstack_service.clear_cache(cluster_id)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster.id,
            operation_type='cluster_update',
            operation_object=f'cluster:{cluster.name}',
            result='success',
            details=f'更新集群: {cluster.name}'
        )
        
        return jsonify({
            'success': True,
            'message': '集群更新成功',
            'data': cluster.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update cluster {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/clusters/<int:cluster_id>', methods=['DELETE'])
@login_required
def delete_cluster(cluster_id):
    """删除集群"""
    # 权限检查 - 管理员和超级管理员都可以删除
    if not current_user.has_role(['super_admin', 'admin']):
        return jsonify({'success': False, 'error': '权限不足，只有管理员可以删除集群'}), 403
    
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        cluster_name = cluster.name
        
        # 删除集群，不需要密码验证
        db.session.delete(cluster)
        db.session.commit()
        
        # 清除相关缓存
        openstack_service.clear_cache(cluster_id)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=None,
            operation_type='cluster_delete',
            operation_object=f'cluster:{cluster_name}',
            result='success',
            details=f'删除集群: {cluster_name}'
        )
        
        return jsonify({
            'success': True,
            'message': f'集群 {cluster_name} 删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete cluster {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/clusters/<int:cluster_id>/test', methods=['POST'])
@login_required
def test_cluster_connection(cluster_id):
    """测试集群连接"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        # 执行连接测试
        result = cluster.test_connection()
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster.id,
            operation_type='cluster_test',
            operation_object=f'cluster:{cluster.name}',
            result='success' if result['success'] else 'failed',
            details=f'连接测试: {result.get("message", result.get("error", ""))}'
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Failed to test cluster {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/clusters/<int:cluster_id>/resources', methods=['GET'])
@login_required
def get_cluster_resources(cluster_id):
    """获取集群资源统计"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        # 获取资源统计
        try:
            clients = openstack_service.get_cluster_clients(cluster_id)
            nova_client = clients['nova']
            cinder_client = clients['cinder']
            
            # 获取基础数据
            instances = nova_client.servers.list()
            volumes = cinder_client.volumes.list()
            
            # 尝试获取其他资源
            snapshots = []
            networks = []
            images = []
            
            try:
                snapshots = cinder_client.volume_snapshots.list()
            except Exception as e:
                logger.warning(f"Failed to get snapshots: {str(e)}")
                
            try:
                neutron_client = clients.get('neutron')
                if neutron_client:
                    networks = neutron_client.list_networks()['networks']
            except Exception as e:
                logger.warning(f"Failed to get networks: {str(e)}")
                
            try:
                glance_client = clients.get('glance')
                if glance_client:
                    images = list(glance_client.images.list())
            except Exception as e:
                logger.warning(f"Failed to get images: {str(e)}")
            
            # 按状态统计实例
            instance_stats = {}
            for instance in instances:
                status = instance.status
                instance_stats[status] = instance_stats.get(status, 0) + 1
            
            # 按状态统计卷
            volume_stats = {}
            volume_size_total = 0
            for volume in volumes:
                status = volume.status
                volume_stats[status] = volume_stats.get(status, 0) + 1
                volume_size_total += volume.size
            
            # 统计快照
            snapshot_stats = {}
            snapshot_size_total = 0
            for snapshot in snapshots:
                status = snapshot.status
                snapshot_stats[status] = snapshot_stats.get(status, 0) + 1
                snapshot_size_total += getattr(snapshot, 'size', 0)
            
            # 统计镜像
            image_stats = {}
            image_size_total = 0
            for image in images:
                status = image.status
                image_stats[status] = image_stats.get(status, 0) + 1
                size_bytes = getattr(image, 'size', 0) or 0
                image_size_total += size_bytes / (1024 * 1024 * 1024)  # 转换为GB
            
            # 统计网络
            network_stats = {
                'total': len(networks),
                'external': sum(1 for net in networks if net.get('router:external', False)),
                'internal': sum(1 for net in networks if not net.get('router:external', False))
            }
            
            # 更新集群资源计数
            cluster.update_resource_counts(
                instances=len(instances),
                volumes=len(volumes),
                networks=len(networks)
            )
            
            return jsonify({
                'success': True,
                'data': {
                    'cluster_name': cluster.name,
                    'cluster_id': cluster.id,
                    'summary': {
                        'instances': len(instances),
                        'volumes': len(volumes),
                        'snapshots': len(snapshots),
                        'networks': len(networks),
                        'images': len(images),
                        'total_volume_size': volume_size_total,
                        'total_snapshot_size': snapshot_size_total,
                        'total_image_size': image_size_total
                    },
                    'statistics': {
                        'instance_stats': instance_stats,
                        'volume_stats': volume_stats,
                        'snapshot_stats': snapshot_stats,
                        'image_stats': image_stats,
                        'network_stats': network_stats
                    },
                    'connection_status': cluster.connection_status,
                    'last_connection_test': cluster.last_connection_test.isoformat() if cluster.last_connection_test else None,
                    'last_updated': datetime.utcnow().isoformat(),
                    'error_message': cluster.error_message
                }
            })
            
        except Exception as e:
            logger.warning(f"Failed to fetch resources for cluster {cluster_id}: {str(e)}")
            return jsonify({
                'success': True,
                'data': {
                    'cluster_name': cluster.name,
                    'cluster_id': cluster.id,
                    'summary': {
                        'instances': cluster.instance_count or 0,
                        'volumes': cluster.volume_count or 0,
                        'snapshots': 0,
                        'networks': cluster.network_count or 0,
                        'images': 0,
                        'total_volume_size': 0,
                        'total_snapshot_size': 0,
                        'total_image_size': 0
                    },
                    'statistics': {
                        'instance_stats': {},
                        'volume_stats': {},
                        'snapshot_stats': {},
                        'image_stats': {},
                        'network_stats': {}
                    },
                    'connection_status': cluster.connection_status,
                    'last_connection_test': cluster.last_connection_test.isoformat() if cluster.last_connection_test else None,
                    'last_updated': cluster.updated_at.isoformat() if cluster.updated_at else None,
                    'error_message': cluster.error_message,
                    'note': '无法连接到集群，显示缓存数据'
                }
            })
        
    except Exception as e:
        logger.error(f"Failed to get cluster resources {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/clusters/status', methods=['GET'])
@login_required
def get_clusters_status():
    """获取所有集群状态概览"""
    try:
        clusters = OpenstackCluster.get_active_clusters()
        
        status_summary = {
            'total': len(clusters),
            'connected': 0,
            'failed': 0,
            'unknown': 0,
            'clusters': []
        }
        
        for cluster in clusters:
            cluster_data = {
                'id': cluster.id,
                'name': cluster.name,
                'status': cluster.connection_status,
                'last_test': cluster.last_connection_test.isoformat() if cluster.last_connection_test else None,
                'error': cluster.error_message,
                'resources': {
                    'instances': cluster.instance_count,
                    'volumes': cluster.volume_count,
                    'networks': cluster.network_count
                }
            }
            
            status_summary['clusters'].append(cluster_data)
            
            # 统计状态
            if cluster.connection_status == 'connected':
                status_summary['connected'] += 1
            elif cluster.connection_status == 'failed':
                status_summary['failed'] += 1
            else:
                status_summary['unknown'] += 1
        
        return jsonify({
            'success': True,
            'data': status_summary
        })
        
    except Exception as e:
        logger.error(f"Failed to get clusters status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500