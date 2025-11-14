"""
集群管理API路由
提供集群的CRUD操作和状态管理
"""
import logging
from datetime import datetime, timedelta
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from . import api_bp as api
from app.models.base import db
from app.models.cluster import OpenstackCluster
from app.models.log import OperationLog
from app.services.openstack_service import openstack_service

logger = logging.getLogger(__name__)

# 集群状态缓存 - 格式: {cluster_id: {'status': {...}, 'timestamp': datetime}}
_cluster_status_cache = {}
_CACHE_DURATION = timedelta(seconds=30)  # 30秒缓存

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

def _get_cluster_status_cached(cluster):
    """
    获取集群状态（带缓存）
    
    Args:
        cluster: OpenstackCluster对象
        
    Returns:
        dict: 集群状态信息
    """
    global _cluster_status_cache
    
    now = datetime.utcnow()
    cache_key = cluster.id
    
    # 检查缓存是否有效
    if cache_key in _cluster_status_cache:
        cached_data = _cluster_status_cache[cache_key]
        if now - cached_data['timestamp'] < _CACHE_DURATION:
            logger.debug(f"Using cached status for cluster {cluster.name}")
            return cached_data['status']
    
    # 缓存失效或不存在，重新获取状态
    logger.debug(f"Fetching fresh status for cluster {cluster.name}")
    
    try:
        # 尝试连接集群获取实时状态
        result = cluster.test_connection()
        
        if result['success']:
            status = 'connected'
            error_message = None
        else:
            status = 'failed'
            error_message = result.get('error', 'Connection failed')
    except Exception as e:
        logger.warning(f"Failed to test connection for cluster {cluster.name}: {e}")
        status = cluster.connection_status or 'unknown'
        error_message = str(e)
    
    # 构建状态数据
    cluster_status = {
        'id': cluster.id,
        'name': cluster.name,
        'status': status,
        'last_test': now.isoformat(),
        'error': error_message,
        'resources': {
            'instances': cluster.instance_count or 0,
            'volumes': cluster.volume_count or 0,
            'networks': cluster.network_count or 0
        }
    }
    
    # 更新缓存
    _cluster_status_cache[cache_key] = {
        'status': cluster_status,
        'timestamp': now
    }
    
    return cluster_status


@api.route('/clusters/status', methods=['GET'])
@login_required
def get_clusters_status():
    """获取所有集群状态概览（带30秒缓存）"""
    try:
        clusters = OpenstackCluster.get_active_clusters()
        
        status_summary = {
            'total': len(clusters),
            'connected': 0,
            'failed': 0,
            'unknown': 0,
            'clusters': [],
            'cached_at': datetime.utcnow().isoformat()
        }
        
        for cluster in clusters:
            cluster_status = _get_cluster_status_cached(cluster)
            status_summary['clusters'].append(cluster_status)
            
            # 统计状态
            if cluster_status['status'] == 'connected':
                status_summary['connected'] += 1
            elif cluster_status['status'] == 'failed':
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


@api.route('/clusters/<int:cluster_id>/status', methods=['GET'])
@login_required
def get_single_cluster_status(cluster_id):
    """获取单个集群状态（带30秒缓存）"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        # 检查是否强制刷新
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if force_refresh:
            # 清除该集群的缓存
            global _cluster_status_cache
            if cluster_id in _cluster_status_cache:
                del _cluster_status_cache[cluster_id]
                logger.info(f"Cleared cache for cluster {cluster.name}")
        
        cluster_status = _get_cluster_status_cached(cluster)
        
        return jsonify({
            'success': True,
            'data': cluster_status
        })
        
    except Exception as e:
        logger.error(f"Failed to get cluster {cluster_id} status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api.route('/clusters/<int:cluster_id>/projects', methods=['GET'])
@login_required
def get_cluster_projects(cluster_id):
    """获取集群的项目列表（OpenStack）"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        # 获取OpenStack客户端
        clients = openstack_service.get_cluster_clients(cluster_id)
        
        # 检查是否有keystone客户端（用于获取项目列表）
        if 'keystone' not in clients:
            logger.warning(f"Keystone client not available for cluster {cluster.name}")
            return jsonify({
                'success': False,
                'error': 'Keystone服务不可用，无法获取项目列表'
            }), 400
        
        keystone_client = clients['keystone']
        
        # 获取项目列表
        projects = keystone_client.projects.list()
        
        # 转换为字典格式
        projects_data = []
        for project in projects:
            project_info = {
                'id': project.id,
                'name': project.name,
                'description': getattr(project, 'description', ''),
                'enabled': getattr(project, 'enabled', True),
                'domain_id': getattr(project, 'domain_id', None),
                'is_domain': getattr(project, 'is_domain', False)
            }
            projects_data.append(project_info)
        
        # 按名称排序
        projects_data.sort(key=lambda x: x['name'])
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='cluster_list_projects',
            operation_object=f'cluster:{cluster.name}',
            result='success',
            details=f'获取项目列表: {len(projects_data)} 个项目'
        )
        
        return jsonify({
            'success': True,
            'data': {
                'cluster_id': cluster_id,
                'cluster_name': cluster.name,
                'projects': projects_data,
                'total': len(projects_data)
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get projects for cluster {cluster_id}: {str(e)}")
        
        # 如果是认证错误或服务不可用，返回友好的错误信息
        error_msg = str(e)
        if 'Unauthorized' in error_msg or 'Authentication' in error_msg:
            error_msg = '集群认证失败，请检查集群凭据'
        elif 'Connection' in error_msg or 'Timeout' in error_msg:
            error_msg = '无法连接到集群，请检查集群状态'
        
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500


@api.route('/clusters/<int:cluster_id>/projects/<project_id>/switch', methods=['POST'])
@login_required
def switch_cluster_project(cluster_id, project_id):
    """切换集群的当前项目（保存到session）"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        # 验证项目是否存在
        clients = openstack_service.get_cluster_clients(cluster_id)
        
        if 'keystone' not in clients:
            return jsonify({
                'success': False,
                'error': 'Keystone服务不可用'
            }), 400
        
        keystone_client = clients['keystone']
        
        try:
            project = keystone_client.projects.get(project_id)
        except Exception as e:
            logger.warning(f"Project {project_id} not found in cluster {cluster.name}: {e}")
            return jsonify({
                'success': False,
                'error': '项目不存在'
            }), 404
        
        # 更新session中的集群上下文
        from flask import session
        cluster_context = session.get('cluster_context', {})
        
        # 确保当前选择的集群是这个集群
        if cluster_context.get('selectedClusterId') != cluster_id:
            cluster_context['selectedClusterId'] = cluster_id
        
        # 更新选择的项目
        cluster_context['selectedProjectId'] = project_id
        cluster_context['selectedProjectName'] = project.name
        cluster_context['lastUpdated'] = datetime.utcnow().isoformat()
        
        session['cluster_context'] = cluster_context
        session.modified = True
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='cluster_switch_project',
            operation_object=f'cluster:{cluster.name}',
            result='success',
            details=f'切换到项目: {project.name}'
        )
        
        return jsonify({
            'success': True,
            'message': f'已切换到项目: {project.name}',
            'data': {
                'cluster_id': cluster_id,
                'cluster_name': cluster.name,
                'project_id': project_id,
                'project_name': project.name
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to switch project for cluster {cluster_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api.route('/clusters/<int:cluster_id>/enhanced', methods=['GET'])
@login_required
def get_cluster_enhanced(cluster_id):
    """获取集群增强信息（版本、响应时间、配额、服务健康等）"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        # 基础信息
        enhanced_data = {
            'id': cluster.id,
            'name': cluster.name,
            'description': cluster.description,
            'auth_url': cluster.auth_url,
            'region_name': cluster.region_name,
            'connection_status': cluster.connection_status,
            'last_connection_test': cluster.last_connection_test.isoformat() if cluster.last_connection_test else None,
        }
        
        # 尝试获取增强信息
        try:
            clients = openstack_service.get_cluster_clients(cluster_id)
            keystone_client = clients['keystone']
            
            # 获取OpenStack版本
            try:
                version_info = keystone_client.version
                if hasattr(version_info, 'version'):
                    enhanced_data['version'] = version_info.version
                else:
                    # 尝试从API版本推断
                    enhanced_data['version'] = 'Unknown'
            except Exception as e:
                logger.warning(f"Failed to get version for cluster {cluster_id}: {e}")
                enhanced_data['version'] = 'Unknown'
            
            # 测量响应时间
            import time
            start_time = time.time()
            try:
                keystone_client.projects.list(limit=1)
                response_time_ms = int((time.time() - start_time) * 1000)
                enhanced_data['response_time_ms'] = response_time_ms
            except Exception as e:
                logger.warning(f"Failed to measure response time for cluster {cluster_id}: {e}")
                enhanced_data['response_time_ms'] = None
            
            # 获取当前项目信息
            from flask import session
            cluster_context = session.get('cluster_context', {})
            if cluster_context.get('selectedClusterId') == cluster_id:
                enhanced_data['current_project'] = {
                    'id': cluster_context.get('selectedProjectId'),
                    'name': cluster_context.get('selectedProjectName')
                }
            else:
                enhanced_data['current_project'] = None
            
            # 获取项目数量
            try:
                projects = keystone_client.projects.list()
                enhanced_data['project_count'] = len(projects)
            except Exception as e:
                logger.warning(f"Failed to get project count for cluster {cluster_id}: {e}")
                enhanced_data['project_count'] = 0
            
            # 获取配额/资源信息
            try:
                nova_client = clients['nova']
                cinder_client = clients['cinder']
                
                # 获取当前项目ID（如果有）
                project_id = cluster_context.get('selectedProjectId') if cluster_context.get('selectedClusterId') == cluster_id else None
                
                if project_id:
                    # 如果选择了项目，返回项目配额
                    try:
                        # Nova配额
                        nova_quota = nova_client.quotas.get(project_id)
                        # Cinder配额
                        cinder_quota = cinder_client.quotas.get(project_id)
                        
                        # 获取实际使用量
                        instances = nova_client.servers.list()
                        volumes = cinder_client.volumes.list()
                        
                        # 计算存储使用量
                        volume_storage_used = sum(v.size for v in volumes)
                        
                        enhanced_data['quota'] = {
                            'instances': {
                                'used': len(instances),
                                'limit': nova_quota.instances
                            },
                            'vcpus': {
                                'used': sum(getattr(nova_client.flavors.get(i.flavor['id']), 'vcpus', 0) for i in instances),
                                'limit': nova_quota.cores
                            },
                            'ram_mb': {
                                'used': sum(getattr(nova_client.flavors.get(i.flavor['id']), 'ram', 0) for i in instances),
                                'limit': nova_quota.ram
                            },
                            'volumes': {
                                'used': len(volumes),
                                'limit': cinder_quota.volumes
                            },
                            'storage_gb': {
                                'used': volume_storage_used,
                                'limit': cinder_quota.gigabytes
                            }
                        }
                    except Exception as e:
                        logger.warning(f"Failed to get project quota: {e}, falling back to cluster stats")
                        project_id = None  # 回退到集群统计
                
                if not project_id:
                    # 如果没有选择项目，返回集群级别的资源统计
                    try:
                        # 获取hypervisor统计信息
                        stats = nova_client.hypervisor_stats.statistics()
                        
                        # 获取所有卷的统计
                        try:
                            volumes = cinder_client.volumes.list(search_opts={'all_tenants': True})
                            volume_storage_used = sum(v.size for v in volumes)
                            volume_storage_total = volume_storage_used * 2  # 估算总容量
                        except:
                            volume_storage_used = 0
                            volume_storage_total = 0
                        
                        enhanced_data['quota'] = {
                            'vcpus': {
                                'used': stats.vcpus_used,
                                'limit': stats.vcpus
                            },
                            'ram_mb': {
                                'used': stats.memory_mb_used,
                                'limit': stats.memory_mb
                            },
                            'storage_gb': {
                                'used': volume_storage_used,
                                'limit': max(volume_storage_total, volume_storage_used + 100)  # 确保有可用空间显示
                            }
                        }
                        logger.info(f"Using cluster-level stats for cluster {cluster_id}")
                    except Exception as e2:
                        logger.warning(f"Failed to get cluster stats: {e2}")
                        enhanced_data['quota'] = None
                    
            except Exception as e:
                logger.error(f"Failed to get quota/stats for cluster {cluster_id}: {e}")
                enhanced_data['quota'] = None
            
            # 获取服务健康状态
            try:
                service_health = openstack_service.get_service_health(cluster_id)
                enhanced_data['service_health'] = service_health
            except Exception as e:
                logger.warning(f"Failed to get service health for cluster {cluster_id}: {e}")
                enhanced_data['service_health'] = {
                    'nova': 'unknown',
                    'cinder': 'unknown',
                    'neutron': 'unknown',
                    'glance': 'unknown'
                }
            
            # 检查告警（配额警告）
            alerts = []
            if enhanced_data.get('quota'):
                for resource, quota_info in enhanced_data['quota'].items():
                    if quota_info['limit'] > 0:
                        usage_percent = (quota_info['used'] / quota_info['limit']) * 100
                        if usage_percent >= 80:
                            alerts.append({
                                'type': 'quota_warning',
                                'severity': 'warning' if usage_percent < 90 else 'critical',
                                'message': f'{resource} 配额使用率达到 {usage_percent:.1f}%'
                            })
            
            enhanced_data['alerts'] = alerts
            
        except Exception as e:
            logger.error(f"Failed to get enhanced info for cluster {cluster_id}: {e}")
            # 返回基础信息
            enhanced_data['version'] = 'Unknown'
            enhanced_data['response_time_ms'] = None
            enhanced_data['current_project'] = None
            enhanced_data['project_count'] = 0
            enhanced_data['quota'] = None
            enhanced_data['service_health'] = {
                'nova': 'unknown',
                'cinder': 'unknown',
                'neutron': 'unknown',
                'glance': 'unknown'
            }
            enhanced_data['alerts'] = []
            enhanced_data['error'] = str(e)
        
        return jsonify({
            'success': True,
            'data': enhanced_data
        })
        
    except Exception as e:
        logger.error(f"Failed to get enhanced cluster info {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api.route('/clusters/<int:cluster_id>/services', methods=['GET'])
@login_required
def get_cluster_services(cluster_id):
    """获取集群服务健康状态详情"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        service_health = openstack_service.get_service_health(cluster_id)
        
        return jsonify({
            'success': True,
            'data': {
                'cluster_id': cluster_id,
                'cluster_name': cluster.name,
                'services': service_health
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get services for cluster {cluster_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@api.route('/clusters/<int:cluster_id>/hosts', methods=['GET'])
@login_required
def get_cluster_hosts(cluster_id):
    """获取集群的计算节点（主机）列表"""
    try:
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        
        logger.info(f"Getting hosts for cluster {cluster_id} ({cluster.name})")
        
        # 获取主机列表
        hosts_data = openstack_service.get_cluster_hosts(cluster_id)
        
        logger.info(f"Retrieved {len(hosts_data)} hosts for cluster {cluster_id}")
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='cluster_list_hosts',
            operation_object=f'cluster:{cluster.name}',
            result='success',
            details=f'获取主机列表: {len(hosts_data)} 个主机'
        )
        
        return jsonify({
            'success': True,
            'data': hosts_data
        })
        
    except Exception as e:
        logger.error(f"Failed to get hosts for cluster {cluster_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500
