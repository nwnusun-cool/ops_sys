"""
快照管理API路由
提供OpenStack卷快照和实例快照的管理操作
"""
import logging
from datetime import datetime
from flask import request, jsonify
from flask_login import login_required, current_user
from . import api_bp as api
from app.models.base import db
from app.models.cluster import OpenstackCluster
from app.models.log import OperationLog
from app.services.openstack_service import openstack_service

logger = logging.getLogger(__name__)

@api.route('/snapshots', methods=['GET'])
@login_required
def list_snapshots():
    """获取快照列表"""
    try:
        # 获取查询参数
        cluster_id = request.args.get('cluster_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        snapshot_type = request.args.get('type')  # volume, instance
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        
        # 如果没有指定集群ID，选择默认集群
        if not cluster_id:
            default_cluster = OpenstackCluster.query.filter_by(is_active=True).first()
            if not default_cluster:
                return jsonify({'success': False, 'error': '没有可用的集群'}), 400
            clusters = [default_cluster]
        else:
            clusters = [OpenstackCluster.query.get_or_404(cluster_id)]
        
        # 获取所有快照数据
        all_snapshots = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                cinder_client = clients['cinder']
                nova_client = clients['nova']
                
                logger.info(f"Getting snapshots for cluster {cluster.name}")
                
                # 获取卷快照
                if not snapshot_type or snapshot_type == 'volume':
                    try:
                        volume_snapshots = cinder_client.volume_snapshots.list(detailed=True)
                        for snapshot in volume_snapshots:
                            all_snapshots.append((snapshot, cluster, 'volume'))
                    except Exception as e:
                        logger.warning(f"Failed to get volume snapshots: {e}")
                
                # 获取实例快照（镜像）
                if not snapshot_type or snapshot_type == 'instance':
                    try:
                        glance_client = clients['glance']
                        # 获取所有镜像，过滤出快照类型的
                        images = list(glance_client.images.list())
                        for image in images:
                            # 判断是否为实例快照（通常有instance_uuid属性或image_type为snapshot）
                            if (hasattr(image, 'instance_uuid') or 
                                getattr(image, 'image_type', None) == 'snapshot' or
                                'snapshot' in getattr(image, 'name', '').lower()):
                                all_snapshots.append((image, cluster, 'instance'))
                    except Exception as e:
                        logger.warning(f"Failed to get instance snapshots: {e}")
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get snapshots from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式
        snapshots_data = []
        
        for snapshot, cluster, snap_type in all_snapshots:
            if snap_type == 'volume':
                # 卷快照
                try:
                    # 获取源卷信息
                    volume_name = 'Unknown'
                    if hasattr(snapshot, 'volume_id') and snapshot.volume_id:
                        try:
                            clients = openstack_service.get_cluster_clients(cluster.id)
                            cinder_client = clients['cinder']
                            volume = cinder_client.volumes.get(snapshot.volume_id)
                            volume_name = volume.name or volume.id
                        except:
                            volume_name = snapshot.volume_id[:8] + '...'
                    
                    snapshot_data = {
                        'id': snapshot.id,
                        'name': snapshot.name or snapshot.id,
                        'description': getattr(snapshot, 'description', ''),
                        'status': snapshot.status,
                        'size': snapshot.size,
                        'volume_id': getattr(snapshot, 'volume_id', None),
                        'volume_name': volume_name,
                        'created_at': snapshot.created_at,
                        'updated_at': getattr(snapshot, 'updated_at', None),
                        'progress': getattr(snapshot, 'os-extended-snapshot-attributes:progress', '100%'),
                        'project_id': getattr(snapshot, 'os-extended-snapshot-attributes:project_id', None),
                        'metadata': getattr(snapshot, 'metadata', {}),
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'type': 'volume'
                    }
                except Exception as e:
                    logger.warning(f"Error processing volume snapshot {snapshot.id}: {e}")
                    continue
            
            else:
                # 实例快照（镜像）
                try:
                    snapshot_data = {
                        'id': snapshot.id,
                        'name': snapshot.name or snapshot.id,
                        'description': getattr(snapshot, 'description', ''),
                        'status': snapshot.status,
                        'size': getattr(snapshot, 'size', 0),
                        'instance_id': getattr(snapshot, 'instance_uuid', None),
                        'instance_name': getattr(snapshot, 'instance_uuid', 'Unknown'),
                        'created_at': snapshot.created_at,
                        'updated_at': snapshot.updated_at,
                        'disk_format': getattr(snapshot, 'disk_format', 'unknown'),
                        'container_format': getattr(snapshot, 'container_format', 'unknown'),
                        'visibility': getattr(snapshot, 'visibility', 'private'),
                        'min_disk': getattr(snapshot, 'min_disk', 0),
                        'min_ram': getattr(snapshot, 'min_ram', 0),
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'type': 'instance'
                    }
                    
                    # 尝试获取实例名称
                    if snapshot_data['instance_id']:
                        try:
                            clients = openstack_service.get_cluster_clients(cluster.id)
                            nova_client = clients['nova']
                            instance = nova_client.servers.get(snapshot_data['instance_id'])
                            snapshot_data['instance_name'] = instance.name
                        except:
                            pass
                
                except Exception as e:
                    logger.warning(f"Error processing instance snapshot {snapshot.id}: {e}")
                    continue
            
            snapshots_data.append(snapshot_data)
        
        # 应用过滤器
        filtered_snapshots = snapshots_data
        
        # 类型过滤
        if snapshot_type:
            filtered_snapshots = [snap for snap in filtered_snapshots if snap['type'] == snapshot_type]
        
        # 状态过滤
        if status:
            filtered_snapshots = [snap for snap in filtered_snapshots if snap['status'].upper() == status.upper()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_snapshots = [
                snap for snap in filtered_snapshots
                if search_lower in snap['name'].lower() or search_lower in snap['id']
            ]
        
        # 分页
        total = len(filtered_snapshots)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_snapshots = filtered_snapshots[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        type_counts = {'volume': 0, 'instance': 0}
        total_size = 0
        
        for snapshot in snapshots_data:
            status = snapshot['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
            snap_type = snapshot['type']
            type_counts[snap_type] = type_counts.get(snap_type, 0) + 1
            
            # 计算总大小
            size = snapshot.get('size', 0)
            if isinstance(size, (int, float)):
                total_size += size
        
        return jsonify({
            'success': True,
            'data': paginated_snapshots,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_snapshots': len(snapshots_data),
                'filtered_snapshots': total,
                'status_counts': status_counts,
                'type_counts': type_counts,
                'total_size_gb': total_size,
                'cluster_name': cluster_names[0] if len(cluster_names) == 1 else f"共 {len(cluster_names)} 个集群"
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list snapshots: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/snapshots/all-clusters', methods=['GET'])
@login_required
def list_all_cluster_snapshots():
    """获取所有集群的快照列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        snapshot_type = request.args.get('type')  # volume, instance
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        
        # 获取所有快照数据
        all_snapshots = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                cinder_client = clients['cinder']
                nova_client = clients['nova']
                
                logger.info(f"Getting snapshots for cluster {cluster.name}")
                
                # 获取卷快照
                if not snapshot_type or snapshot_type == 'volume':
                    try:
                        volume_snapshots = cinder_client.volume_snapshots.list(detailed=True)
                        for snapshot in volume_snapshots:
                            all_snapshots.append((snapshot, cluster, 'volume'))
                    except Exception as e:
                        logger.warning(f"Failed to get volume snapshots: {e}")
                
                # 获取实例快照
                if not snapshot_type or snapshot_type == 'instance':
                    try:
                        glance_client = clients['glance']
                        images = list(glance_client.images.list())
                        for image in images:
                            if (hasattr(image, 'instance_uuid') or 
                                getattr(image, 'image_type', None) == 'snapshot' or
                                'snapshot' in getattr(image, 'name', '').lower()):
                                all_snapshots.append((image, cluster, 'instance'))
                    except Exception as e:
                        logger.warning(f"Failed to get instance snapshots: {e}")
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get snapshots from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式（与单集群相同的逻辑）
        snapshots_data = []
        
        for snapshot, cluster, snap_type in all_snapshots:
            if snap_type == 'volume':
                try:
                    volume_name = 'Unknown'
                    if hasattr(snapshot, 'volume_id') and snapshot.volume_id:
                        try:
                            clients = openstack_service.get_cluster_clients(cluster.id)
                            cinder_client = clients['cinder']
                            volume = cinder_client.volumes.get(snapshot.volume_id)
                            volume_name = volume.name or volume.id
                        except:
                            volume_name = snapshot.volume_id[:8] + '...'
                    
                    snapshot_data = {
                        'id': snapshot.id,
                        'name': snapshot.name or snapshot.id,
                        'description': getattr(snapshot, 'description', ''),
                        'status': snapshot.status,
                        'size': snapshot.size,
                        'volume_id': getattr(snapshot, 'volume_id', None),
                        'volume_name': volume_name,
                        'created_at': snapshot.created_at,
                        'updated_at': getattr(snapshot, 'updated_at', None),
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'type': 'volume'
                    }
                except Exception as e:
                    logger.warning(f"Error processing volume snapshot: {e}")
                    continue
            else:
                try:
                    snapshot_data = {
                        'id': snapshot.id,
                        'name': snapshot.name or snapshot.id,
                        'description': getattr(snapshot, 'description', ''),
                        'status': snapshot.status,
                        'size': getattr(snapshot, 'size', 0),
                        'instance_id': getattr(snapshot, 'instance_uuid', None),
                        'instance_name': 'Unknown',
                        'created_at': snapshot.created_at,
                        'updated_at': snapshot.updated_at,
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'type': 'instance'
                    }
                    
                    # 尝试获取实例名称
                    if snapshot_data['instance_id']:
                        try:
                            clients = openstack_service.get_cluster_clients(cluster.id)
                            nova_client = clients['nova']
                            instance = nova_client.servers.get(snapshot_data['instance_id'])
                            snapshot_data['instance_name'] = instance.name
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"Error processing instance snapshot: {e}")
                    continue
            
            snapshots_data.append(snapshot_data)
        
        # 应用过滤器
        filtered_snapshots = snapshots_data
        
        if snapshot_type:
            filtered_snapshots = [snap for snap in filtered_snapshots if snap['type'] == snapshot_type]
        
        if status:
            filtered_snapshots = [snap for snap in filtered_snapshots if snap['status'].upper() == status.upper()]
        
        if search:
            search_lower = search.lower()
            filtered_snapshots = [
                snap for snap in filtered_snapshots
                if search_lower in snap['name'].lower() or search_lower in snap['id']
            ]
        
        # 分页
        total = len(filtered_snapshots)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_snapshots = filtered_snapshots[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        type_counts = {'volume': 0, 'instance': 0}
        total_size = 0
        
        for snapshot in snapshots_data:
            status = snapshot['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
            snap_type = snapshot['type']
            type_counts[snap_type] = type_counts.get(snap_type, 0) + 1
            
            size = snapshot.get('size', 0)
            if isinstance(size, (int, float)):
                total_size += size
        
        return jsonify({
            'success': True,
            'data': paginated_snapshots,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_snapshots': len(snapshots_data),
                'filtered_snapshots': total,
                'status_counts': status_counts,
                'type_counts': type_counts,
                'total_size_gb': total_size,
                'cluster_name': f'所有集群 ({", ".join(cluster_names)})'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list all cluster snapshots: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/snapshots/<snapshot_id>', methods=['GET'])
@login_required
def get_snapshot_detail(snapshot_id):
    """获取快照详细信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        snapshot_type = request.args.get('type', 'volume')  # volume, instance
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        
        if snapshot_type == 'volume':
            # 卷快照详情
            cinder_client = clients['cinder']
            snapshot = cinder_client.volume_snapshots.get(snapshot_id)
            
            # 获取源卷信息
            volume_info = {}
            if hasattr(snapshot, 'volume_id') and snapshot.volume_id:
                try:
                    volume = cinder_client.volumes.get(snapshot.volume_id)
                    volume_info = {
                        'id': volume.id,
                        'name': volume.name or volume.id,
                        'size': volume.size,
                        'status': volume.status,
                        'volume_type': getattr(volume, 'volume_type', 'Unknown')
                    }
                except Exception as e:
                    logger.warning(f"Failed to get volume info: {e}")
            
            snapshot_detail = {
                'id': snapshot.id,
                'name': snapshot.name or snapshot.id,
                'description': getattr(snapshot, 'description', ''),
                'status': snapshot.status,
                'size': snapshot.size,
                'volume_id': getattr(snapshot, 'volume_id', None),
                'volume_info': volume_info,
                'created_at': snapshot.created_at,
                'updated_at': getattr(snapshot, 'updated_at', None),
                'progress': getattr(snapshot, 'os-extended-snapshot-attributes:progress', '100%'),
                'project_id': getattr(snapshot, 'os-extended-snapshot-attributes:project_id', None),
                'metadata': getattr(snapshot, 'metadata', {}),
                'cluster_name': cluster.name,
                'type': 'volume'
            }
        else:
            # 实例快照（镜像）详情
            glance_client = clients['glance']
            snapshot = glance_client.images.get(snapshot_id)
            
            # 获取实例信息
            instance_info = {}
            instance_uuid = getattr(snapshot, 'instance_uuid', None)
            if instance_uuid:
                try:
                    nova_client = clients['nova']
                    instance = nova_client.servers.get(instance_uuid)
                    instance_info = {
                        'id': instance.id,
                        'name': instance.name,
                        'status': instance.status,
                        'flavor': getattr(instance.flavor, 'name', 'Unknown')
                    }
                except Exception as e:
                    logger.warning(f"Failed to get instance info: {e}")
            
            snapshot_detail = {
                'id': snapshot.id,
                'name': snapshot.name or snapshot.id,
                'description': getattr(snapshot, 'description', ''),
                'status': snapshot.status,
                'size': getattr(snapshot, 'size', 0),
                'instance_id': instance_uuid,
                'instance_info': instance_info,
                'created_at': snapshot.created_at,
                'updated_at': snapshot.updated_at,
                'disk_format': getattr(snapshot, 'disk_format', 'unknown'),
                'container_format': getattr(snapshot, 'container_format', 'unknown'),
                'visibility': getattr(snapshot, 'visibility', 'private'),
                'min_disk': getattr(snapshot, 'min_disk', 0),
                'min_ram': getattr(snapshot, 'min_ram', 0),
                'checksum': getattr(snapshot, 'checksum', None),
                'cluster_name': cluster.name,
                'type': 'instance'
            }
        
        return jsonify({
            'success': True,
            'data': snapshot_detail
        })
        
    except Exception as e:
        logger.error(f"Failed to get snapshot detail {snapshot_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/snapshots/<snapshot_id>/action', methods=['POST'])
@login_required
def snapshot_action(snapshot_id):
    """执行快照操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        action = data.get('action')
        snapshot_type = data.get('type', 'volume')  # volume, instance
        
        if not action:
            return jsonify({'success': False, 'error': '必须指定操作类型'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        
        result_message = ""
        snapshot_name = ""
        
        if snapshot_type == 'volume':
            # 卷快照操作
            cinder_client = clients['cinder']
            snapshot = cinder_client.volume_snapshots.get(snapshot_id)
            snapshot_name = snapshot.name or snapshot.id
            
            if action == 'create_volume':
                # 从快照创建卷
                volume_name = data.get('volume_name', f"vol-from-{snapshot_name}")
                volume_size = data.get('volume_size', snapshot.size)
                
                volume_params = {
                    'size': volume_size,
                    'name': volume_name,
                    'snapshot_id': snapshot_id
                }
                
                if data.get('description'):
                    volume_params['description'] = data['description']
                
                if data.get('volume_type'):
                    volume_params['volume_type'] = data['volume_type']
                
                volume = cinder_client.volumes.create(**volume_params)
                result_message = f"从快照 {snapshot_name} 创建卷 {volume_name} 的任务已提交"
                
            elif action == 'delete':
                # 删除快照需要管理员权限
                if not current_user.has_role(['super_admin', 'admin']):
                    return jsonify({'success': False, 'error': '删除快照需要管理员权限'}), 403
                cinder_client.volume_snapshots.delete(snapshot_id)
                result_message = f"卷快照 {snapshot_name} 删除命令已发送"
                
            else:
                return jsonify({'success': False, 'error': f'不支持的卷快照操作: {action}'}), 400
        
        else:
            # 实例快照（镜像）操作
            glance_client = clients['glance']
            snapshot = glance_client.images.get(snapshot_id)
            snapshot_name = snapshot.name or snapshot.id
            
            if action == 'create_instance':
                # 从快照创建实例
                instance_name = data.get('instance_name', f"instance-from-{snapshot_name}")
                flavor_id = data.get('flavor_id')
                networks = data.get('networks', [])
                
                if not flavor_id:
                    return jsonify({'success': False, 'error': '必须指定实例规格'}), 400
                
                if not networks:
                    return jsonify({'success': False, 'error': '必须指定网络'}), 400
                
                nova_client = clients['nova']
                instance_params = {
                    'name': instance_name,
                    'image': snapshot_id,
                    'flavor': flavor_id,
                    'nics': [{'net-id': net_id} for net_id in networks]
                }
                
                # 可选参数
                if data.get('key_name'):
                    instance_params['key_name'] = data['key_name']
                
                if data.get('security_groups'):
                    instance_params['security_groups'] = data['security_groups']
                
                if data.get('availability_zone'):
                    instance_params['availability_zone'] = data['availability_zone']
                
                server = nova_client.servers.create(**instance_params)
                result_message = f"从快照 {snapshot_name} 创建实例 {instance_name} 的任务已提交"
                
            elif action == 'delete':
                # 删除快照需要管理员权限
                if not current_user.has_role(['super_admin', 'admin']):
                    return jsonify({'success': False, 'error': '删除快照需要管理员权限'}), 403
                glance_client.images.delete(snapshot_id)
                result_message = f"实例快照 {snapshot_name} 删除命令已发送"
                
            else:
                return jsonify({'success': False, 'error': f'不支持的实例快照操作: {action}'}), 400
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'{snapshot_type}_snapshot_{action}',
            operation_object=f'snapshot:{snapshot_name}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'action': action,
            'snapshot_id': snapshot_id,
            'snapshot_name': snapshot_name,
            'type': snapshot_type
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to perform action {action} on snapshot {snapshot_id}: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type=f'snapshot_{action}',
                operation_object=f'snapshot:{snapshot_id}',
                result='failed',
                details=f'操作失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/snapshots/create', methods=['POST'])
@login_required
def create_snapshot():
    """创建快照"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        snapshot_type = data.get('type', 'volume')  # volume, instance
        
        # 验证必填字段
        required_fields = ['name']
        if snapshot_type == 'volume':
            required_fields.append('volume_id')
        else:
            required_fields.append('instance_id')
        
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        
        result_message = ""
        snapshot_id = ""
        
        if snapshot_type == 'volume':
            # 创建卷快照
            cinder_client = clients['cinder']
            
            # 验证卷是否存在
            try:
                volume = cinder_client.volumes.get(data['volume_id'])
                volume_name = volume.name or volume.id
            except Exception:
                return jsonify({'success': False, 'error': '指定的卷不存在'}), 400
            
            # 构建快照创建参数
            snapshot_params = {
                'volume_id': data['volume_id'],
                'name': data['name'],
                'force': data.get('force', False)  # 是否强制创建（卷在使用中时）
            }
            
            if data.get('description'):
                snapshot_params['description'] = data['description']
            
            # 创建快照
            logger.info(f"Creating volume snapshot: {data['name']} from volume {volume_name}")
            snapshot = cinder_client.volume_snapshots.create(**snapshot_params)
            snapshot_id = snapshot.id
            result_message = f"卷 {volume_name} 的快照 {data['name']} 创建任务已提交"
            
        else:
            # 创建实例快照
            nova_client = clients['nova']
            
            # 验证实例是否存在
            try:
                instance = nova_client.servers.get(data['instance_id'])
                instance_name = instance.name
            except Exception:
                return jsonify({'success': False, 'error': '指定的实例不存在'}), 400
            
            # 创建实例快照
            logger.info(f"Creating instance snapshot: {data['name']} from instance {instance_name}")
            
            # Nova的create_image方法会返回镜像ID
            image_id = nova_client.servers.create_image(
                data['instance_id'], 
                data['name'], 
                metadata=data.get('metadata', {})
            )
            
            snapshot_id = image_id
            result_message = f"实例 {instance_name} 的快照 {data['name']} 创建任务已提交"
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'{snapshot_type}_snapshot_create',
            operation_object=f'snapshot:{data["name"]}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'data': {
                'snapshot_id': snapshot_id,
                'name': data['name'],
                'type': snapshot_type
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create snapshot: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type=f'snapshot_create',
                operation_object=f'snapshot:{data.get("name", "unknown")}',
                result='failed',
                details=f'创建快照失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500