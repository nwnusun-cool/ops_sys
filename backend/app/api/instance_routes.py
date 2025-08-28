"""
实例管理API路由
提供OpenStack实例的管理操作
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

@api.route('/instances', methods=['GET'])
@login_required
def list_instances():
    """获取实例列表"""
    try:
        # 获取查询参数
        cluster_id = request.args.get('cluster_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        expire_filter = request.args.get('expire_filter')  # normal, warning, expired
        
        # 如果没有指定集群ID，返回错误或选择默认集群
        if not cluster_id:
            # 可以选择默认显示第一个活跃集群，或者返回错误要求用户选择
            default_cluster = OpenstackCluster.query.filter_by(is_active=True).first()
            if not default_cluster:
                return jsonify({'success': False, 'error': '没有可用的集群'}), 400
            clusters = [default_cluster]
        else:
            clusters = [OpenstackCluster.query.get_or_404(cluster_id)]
        
        # 获取所有实例数据
        all_instances = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                nova_client = clients['nova']
                
                # 获取集群实例
                logger.info(f"Getting instances for cluster {cluster.name}")
                servers = nova_client.servers.list(detailed=True)
                
                # 处理每个实例
                for server in servers:
                    all_instances.append((server, cluster))
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get instances from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式，并添加到期状态
        instances = []
        current_time = datetime.utcnow()
        
        for server, cluster in all_instances:
            metadata = getattr(server, 'metadata', {})
            expire_status = 'normal'  # normal, warning, expired
            
            # 检查销毁时间
            if 'destroy_at' in metadata:
                try:
                    destroy_time = datetime.fromisoformat(metadata['destroy_at'].replace('Z', '+00:00'))
                    if destroy_time.tzinfo:
                        destroy_time = destroy_time.replace(tzinfo=None)
                    
                    if current_time >= destroy_time:
                        expire_status = 'expired'
                    elif (destroy_time - current_time).total_seconds() <= 86400:  # 24小时内
                        expire_status = 'warning'
                except Exception:
                    pass
            
            instance_data = {
                'id': server.id,
                'name': server.name,
                'status': server.status,
                'power_state': getattr(server, 'OS-EXT-STS:power_state', 0),
                'task_state': getattr(server, 'OS-EXT-STS:task_state', None),
                'vm_state': getattr(server, 'OS-EXT-STS:vm_state', None),
                'created': server.created,
                'updated': server.updated,
                'cluster_id': cluster.id,
                'cluster_name': cluster.name,
                'flavor': {
                    'id': server.flavor['id'],
                    'name': getattr(server.flavor, 'name', 'Unknown')
                },
                'image': {
                    'id': server.image['id'] if server.image else None,
                    'name': getattr(server.image, 'name', 'Unknown') if server.image else 'Boot from volume'
                },
                'key_name': getattr(server, 'key_name', None),
                'availability_zone': getattr(server, 'OS-EXT-AZ:availability_zone', None),
                'host': getattr(server, 'OS-EXT-SRV-ATTR:host', None),
                'addresses': dict(server.addresses) if hasattr(server, 'addresses') else {},
                'metadata': metadata,
                'security_groups': [sg['name'] for sg in getattr(server, 'security_groups', [])],
                'volumes_attached': getattr(server, 'os-extended-volumes:volumes_attached', []),
                'expire_status': expire_status
            }
            instances.append(instance_data)
        
        # 应用过滤器
        filtered_instances = instances
        
        # 状态过滤
        if status:
            filtered_instances = [inst for inst in filtered_instances if inst['status'].lower() == status.lower()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_instances = [
                inst for inst in filtered_instances
                if search_lower in inst['name'].lower() or search_lower in inst['id']
            ]
        
        # 到期状态过滤
        if expire_filter:
            filtered_instances = [
                inst for inst in filtered_instances
                if inst['expire_status'] == expire_filter
            ]
        
        # 分页
        total = len(filtered_instances)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_instances = filtered_instances[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        expire_counts = {'normal': 0, 'warning': 0, 'expired': 0}
        
        for instance in instances:
            status = instance['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # 统计到期状态
            expire_status = instance['expire_status']
            expire_counts[expire_status] = expire_counts.get(expire_status, 0) + 1
        
        return jsonify({
            'success': True,
            'data': paginated_instances,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_instances': len(instances),
                'filtered_instances': total,
                'status_counts': status_counts,
                'expire_counts': expire_counts,
                'cluster_name': cluster.name
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list instances: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/<instance_id>', methods=['GET'])
@login_required
def get_instance_detail(instance_id):
    """获取实例详细信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 获取实例详情
        server = nova_client.servers.get(instance_id)
        
        # 获取实例的控制台日志
        try:
            console_log = nova_client.servers.get_console_output(instance_id, length=50)
        except Exception as e:
            logger.warning(f"Failed to get console log for instance {instance_id}: {e}")
            console_log = "Unable to retrieve console log"
        
        # 详细实例信息
        instance_detail = {
            'id': server.id,
            'name': server.name,
            'status': server.status,
            'power_state': getattr(server, 'OS-EXT-STS:power_state', 0),
            'task_state': getattr(server, 'OS-EXT-STS:task_state', None),
            'vm_state': getattr(server, 'OS-EXT-STS:vm_state', None),
            'created': server.created,
            'updated': server.updated,
            'launched_at': getattr(server, 'OS-SRV-USG:launched_at', None),
            'terminated_at': getattr(server, 'OS-SRV-USG:terminated_at', None),
            'flavor': {
                'id': server.flavor['id'],
                'name': getattr(server.flavor, 'name', 'Unknown'),
                'vcpus': getattr(server.flavor, 'vcpus', 0),
                'ram': getattr(server.flavor, 'ram', 0),
                'disk': getattr(server.flavor, 'disk', 0)
            },
            'image': {
                'id': server.image['id'] if server.image else None,
                'name': getattr(server.image, 'name', 'Unknown') if server.image else 'Boot from volume'
            },
            'key_name': getattr(server, 'key_name', None),
            'availability_zone': getattr(server, 'OS-EXT-AZ:availability_zone', None),
            'host': getattr(server, 'OS-EXT-SRV-ATTR:host', None),
            'instance_name': getattr(server, 'OS-EXT-SRV-ATTR:instance_name', None),
            'addresses': dict(server.addresses) if hasattr(server, 'addresses') else {},
            'metadata': getattr(server, 'metadata', {}),
            'security_groups': [sg['name'] for sg in getattr(server, 'security_groups', [])],
            'volumes_attached': getattr(server, 'os-extended-volumes:volumes_attached', []),
            'fault': getattr(server, 'fault', None),
            'console_log': console_log,
            'cluster_name': cluster.name
        }
        
        return jsonify({
            'success': True,
            'data': instance_detail
        })
        
    except Exception as e:
        logger.error(f"Failed to get instance detail {instance_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/<instance_id>/action', methods=['POST'])
@login_required
def instance_action(instance_id):
    """执行实例操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        action = data.get('action')
        
        if not action:
            return jsonify({'success': False, 'error': '必须指定操作类型'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 获取实例信息用于日志记录
        server = nova_client.servers.get(instance_id)
        instance_name = server.name
        
        result_message = ""
        
        # 执行不同的操作
        if action == 'start':
            nova_client.servers.start(instance_id)
            result_message = f"实例 {instance_name} 启动命令已发送"
            
        elif action == 'stop':
            nova_client.servers.stop(instance_id)
            result_message = f"实例 {instance_name} 停止命令已发送"
            
        elif action == 'restart':
            restart_type = data.get('restart_type', 'soft')  # soft or hard
            if restart_type == 'hard':
                nova_client.servers.reboot(instance_id, 'HARD')
            else:
                nova_client.servers.reboot(instance_id, 'SOFT')
            result_message = f"实例 {instance_name} 重启命令已发送 ({restart_type})"
            
        elif action == 'pause':
            nova_client.servers.pause(instance_id)
            result_message = f"实例 {instance_name} 暂停命令已发送"
            
        elif action == 'unpause':
            nova_client.servers.unpause(instance_id)
            result_message = f"实例 {instance_name} 恢复命令已发送"
            
        elif action == 'suspend':
            nova_client.servers.suspend(instance_id)
            result_message = f"实例 {instance_name} 挂起命令已发送"
            
        elif action == 'resume':
            nova_client.servers.resume(instance_id)
            result_message = f"实例 {instance_name} 恢复命令已发送"
            
        elif action == 'delete':
            # 删除操作需要管理员权限
            if not current_user.has_role(['super_admin', 'admin']):
                return jsonify({'success': False, 'error': '删除实例需要管理员权限'}), 403
            nova_client.servers.delete(instance_id)
            result_message = f"实例 {instance_name} 删除命令已发送"
            
        else:
            return jsonify({'success': False, 'error': f'不支持的操作: {action}'}), 400
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'instance_{action}',
            operation_object=f'instance:{instance_name}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'action': action,
            'instance_id': instance_id,
            'instance_name': instance_name
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to perform action {action} on instance {instance_id}: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type=f'instance_{action}',
                operation_object=f'instance:{instance_id}',
                result='failed',
                details=f'操作失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/instances/<instance_id>/console', methods=['GET'])
@login_required
def get_instance_console(instance_id):
    """获取实例控制台"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        console_type = request.args.get('type', 'vnc')  # vnc, spice, rdp, serial
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 获取控制台URL
        if console_type == 'vnc':
            console = nova_client.servers.get_vnc_console(instance_id, 'novnc')
        elif console_type == 'spice':
            console = nova_client.servers.get_spice_console(instance_id, 'spice-html5')
        elif console_type == 'serial':
            console = nova_client.servers.get_serial_console(instance_id, 'serial')
        else:
            return jsonify({'success': False, 'error': f'不支持的控制台类型: {console_type}'}), 400
        
        return jsonify({
            'success': True,
            'data': {
                'type': console_type,
                'url': console['console']['url'],
                'protocol': console['console'].get('protocol', console_type)
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get console for instance {instance_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/<instance_id>/rename', methods=['PUT'])
@login_required
def rename_instance(instance_id):
    """重命名实例"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return jsonify({'success': False, 'error': '实例名称不能为空'}), 400
        
        # 权限检查
        if not current_user.has_role(['super_admin', 'admin', 'operator']):
            return jsonify({'success': False, 'error': '权限不足'}), 403
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 获取当前实例信息
        server = nova_client.servers.get(instance_id)
        old_name = server.name
        
        # 重命名实例
        nova_client.servers.update(instance_id, name=new_name)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='instance_rename',
            operation_object=f'instance:{old_name}',
            result='success',
            details=f'实例重命名: {old_name} -> {new_name}'
        )
        
        return jsonify({
            'success': True,
            'message': f'实例已重命名为: {new_name}',
            'old_name': old_name,
            'new_name': new_name
        })
        
    except Exception as e:
        logger.error(f"Failed to rename instance {instance_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/batch-action-cross-cluster', methods=['POST'])
@login_required
def batch_instance_action_cross_cluster():
    """跨集群批量实例操作"""
    try:
        data = request.get_json()
        instance_ids = data.get('instance_ids', [])
        action = data.get('action')
        
        if not instance_ids:
            return jsonify({'success': False, 'error': '必须指定实例ID列表'}), 400
        
        if not action:
            return jsonify({'success': False, 'error': '必须指定操作类型'}), 400
        
        # 删除操作需要管理员权限
        if action == 'delete' and not current_user.has_role(['super_admin', 'admin']):
            return jsonify({'success': False, 'error': '批量删除需要管理员权限'}), 403
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        
        # 按集群分组实例ID（需要从数据库中查找每个实例属于哪个集群）
        instance_cluster_map = {}
        
        for cluster in clusters:
            try:
                clients = openstack_service.get_cluster_clients(cluster.id)
                nova_client = clients['nova']
                
                # 获取该集群的所有实例
                servers = nova_client.servers.list(detailed=False)
                for server in servers:
                    if server.id in instance_ids:
                        instance_cluster_map[server.id] = {
                            'cluster': cluster,
                            'server': server
                        }
            except Exception as e:
                logger.warning(f"Failed to get instances from cluster {cluster.name}: {e}")
                continue
        
        results = []
        success_count = 0
        
        # 按集群分组执行操作
        cluster_operations = {}
        for instance_id, info in instance_cluster_map.items():
            cluster_id = info['cluster'].id
            if cluster_id not in cluster_operations:
                cluster_operations[cluster_id] = {
                    'cluster': info['cluster'],
                    'instances': []
                }
            cluster_operations[cluster_id]['instances'].append({
                'id': instance_id,
                'server': info['server']
            })
        
        # 对每个集群执行批量操作
        for cluster_id, operation_info in cluster_operations.items():
            cluster = operation_info['cluster']
            instances = operation_info['instances']
            
            try:
                clients = openstack_service.get_cluster_clients(cluster_id)
                nova_client = clients['nova']
                
                for instance_info in instances:
                    instance_id = instance_info['id']
                    server = instance_info['server']
                    instance_name = server.name
                    
                    try:
                        # 执行操作
                        if action == 'start':
                            nova_client.servers.start(instance_id)
                        elif action == 'stop':
                            nova_client.servers.stop(instance_id)
                        elif action == 'restart':
                            restart_type = data.get('restart_type', 'soft')
                            if restart_type == 'hard':
                                nova_client.servers.reboot(instance_id, 'HARD')
                            else:
                                nova_client.servers.reboot(instance_id, 'SOFT')
                        elif action == 'delete':
                            nova_client.servers.delete(instance_id)
                        else:
                            results.append({
                                'instance_id': instance_id,
                                'instance_name': instance_name,
                                'cluster_name': cluster.name,
                                'success': False,
                                'error': f'不支持的操作: {action}'
                            })
                            continue
                        
                        results.append({
                            'instance_id': instance_id,
                            'instance_name': instance_name,
                            'cluster_name': cluster.name,
                            'success': True,
                            'message': f'{instance_name} ({cluster.name}) 操作成功'
                        })
                        success_count += 1
                        
                        # 记录操作日志
                        OperationLog.log_operation(
                            user_id=current_user.id,
                            cluster_id=cluster_id,
                            operation_type=f'instance_batch_{action}',
                            operation_object=f'instance:{instance_name}',
                            result='success',
                            details=f'跨集群批量操作: {action}'
                        )
                        
                    except Exception as e:
                        results.append({
                            'instance_id': instance_id,
                            'instance_name': instance_name,
                            'cluster_name': cluster.name,
                            'success': False,
                            'error': str(e)
                        })
                        
            except Exception as e:
                # 如果整个集群操作失败，为该集群的所有实例添加失败记录
                for instance_info in instances:
                    results.append({
                        'instance_id': instance_info['id'],
                        'instance_name': instance_info['server'].name,
                        'cluster_name': cluster.name,
                        'success': False,
                        'error': f'集群连接失败: {str(e)}'
                    })
        
        # 为未找到的实例添加错误记录
        found_instances = set(instance_cluster_map.keys())
        missing_instances = set(instance_ids) - found_instances
        for instance_id in missing_instances:
            results.append({
                'instance_id': instance_id,
                'instance_name': 'Unknown',
                'cluster_name': 'Unknown',
                'success': False,
                'error': '实例不存在或无法访问'
            })
        
        return jsonify({
            'success': True,
            'message': f'跨集群批量操作完成: {success_count}/{len(instance_ids)} 成功',
            'results': results,
            'success_count': success_count,
            'total_count': len(instance_ids)
        })
        
    except Exception as e:
        logger.error(f"Cross-cluster batch operation failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/batch-action', methods=['POST'])
@login_required
def batch_instance_action():
    """批量实例操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        instance_ids = data.get('instance_ids', [])
        action = data.get('action')
        
        if not instance_ids:
            return jsonify({'success': False, 'error': '必须指定实例ID列表'}), 400
        
        if not action:
            return jsonify({'success': False, 'error': '必须指定操作类型'}), 400
        
        # 删除操作需要管理员权限
        if action == 'delete' and not current_user.has_role(['super_admin', 'admin']):
            return jsonify({'success': False, 'error': '批量删除需要管理员权限'}), 403
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        results = []
        success_count = 0
        
        for instance_id in instance_ids:
            try:
                server = nova_client.servers.get(instance_id)
                instance_name = server.name
                
                # 执行操作
                if action == 'start':
                    nova_client.servers.start(instance_id)
                elif action == 'stop':
                    nova_client.servers.stop(instance_id)
                elif action == 'restart':
                    restart_type = data.get('restart_type', 'soft')
                    if restart_type == 'hard':
                        nova_client.servers.reboot(instance_id, 'HARD')
                    else:
                        nova_client.servers.reboot(instance_id, 'SOFT')
                elif action == 'delete':
                    nova_client.servers.delete(instance_id)
                else:
                    results.append({
                        'instance_id': instance_id,
                        'instance_name': instance_name,
                        'success': False,
                        'error': f'不支持的操作: {action}'
                    })
                    continue
                
                results.append({
                    'instance_id': instance_id,
                    'instance_name': instance_name,
                    'success': True,
                    'message': f'{instance_name} 操作成功'
                })
                success_count += 1
                
                # 记录操作日志
                OperationLog.log_operation(
                    user_id=current_user.id,
                    cluster_id=cluster_id,
                    operation_type=f'instance_batch_{action}',
                    operation_object=f'instance:{instance_name}',
                    result='success',
                    details=f'批量操作: {action}'
                )
                
            except Exception as e:
                results.append({
                    'instance_id': instance_id,
                    'instance_name': 'Unknown',
                    'success': False,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'message': f'批量操作完成: {success_count}/{len(instance_ids)} 成功',
            'results': results,
            'success_count': success_count,
            'total_count': len(instance_ids)
        })
        
    except Exception as e:
        logger.error(f"Batch operation failed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/export', methods=['POST'])
@login_required
def export_instances():
    """导出实例数据到Excel"""
    try:
        import pandas as pd
        from io import BytesIO
        from datetime import datetime
        
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        instance_ids = data.get('instance_ids', [])
        export_all = data.get('export_all', False)
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 获取实例数据
        if export_all or not instance_ids:
            servers = nova_client.servers.list(detailed=True)
        else:
            servers = [nova_client.servers.get(instance_id) for instance_id in instance_ids]
        
        # 转换为DataFrame
        instance_data = []
        for server in servers:
            # 获取IP地址
            ips = []
            for network, addresses in server.addresses.items():
                for addr in addresses:
                    ips.append(f"{network}: {addr['addr']}")
            ip_str = '; '.join(ips) if ips else '无'
            
            instance_data.append({
                '实例ID': server.id,
                '实例名称': server.name,
                '状态': server.status,
                '规格ID': server.flavor['id'],
                '镜像ID': server.image['id'] if server.image else 'Boot from volume',
                '可用区': getattr(server, 'OS-EXT-AZ:availability_zone', ''),
                '主机': getattr(server, 'OS-EXT-SRV-ATTR:host', ''),
                '密钥对': getattr(server, 'key_name', ''),
                'IP地址': ip_str,
                '安全组': '; '.join([sg['name'] for sg in getattr(server, 'security_groups', [])]),
                '创建时间': server.created,
                '更新时间': server.updated,
                '集群': cluster.name
            })
        
        if not instance_data:
            return jsonify({'success': False, 'error': '没有找到实例数据'}), 400
        
        df = pd.DataFrame(instance_data)
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='实例列表', index=False)
            
            # 设置列宽
            worksheet = writer.sheets['实例列表']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='instance_export',
            operation_object=f'cluster:{cluster.name}',
            result='success',
            details=f'导出实例数据: {len(instance_data)} 条'
        )
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"instances_{cluster.name}_{timestamp}.xlsx"
        
        from flask import make_response
        response = make_response(output.read())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to export instances: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/<instance_id>/destroy-timer', methods=['POST'])
@login_required
def set_destroy_timer(instance_id):
    """设置实例销毁时间"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        destroy_at = data.get('destroy_at')  # ISO格式时间字符串
        
        if not destroy_at:
            return jsonify({'success': False, 'error': '必须指定销毁时间'}), 400
        
        # 权限检查
        if not current_user.has_role(['super_admin', 'admin']):
            return jsonify({'success': False, 'error': '设置销毁时间需要管理员权限'}), 403
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 获取实例信息
        server = nova_client.servers.get(instance_id)
        instance_name = server.name
        
        # 这里使用metadata来存储销毁时间
        # 在真实环境中，你可能需要创建专门的数据库表来管理这些定时任务
        metadata = server.metadata or {}
        metadata['destroy_at'] = destroy_at
        metadata['destroy_set_by'] = current_user.username
        metadata['destroy_set_at'] = datetime.utcnow().isoformat()
        
        nova_client.servers.set_meta(instance_id, metadata)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='instance_set_destroy_timer',
            operation_object=f'instance:{instance_name}',
            result='success',
            details=f'设置销毁时间: {destroy_at}'
        )
        
        return jsonify({
            'success': True,
            'message': f'实例 {instance_name} 销毁时间已设置为: {destroy_at}',
            'destroy_at': destroy_at
        })
        
    except Exception as e:
        logger.error(f"Failed to set destroy timer for instance {instance_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/check-expired', methods=['GET'])
@login_required
def check_expired_instances():
    """检查到期的实例"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 获取所有实例
        servers = nova_client.servers.list(detailed=True)
        expired_instances = []
        warning_instances = []
        current_time = datetime.utcnow()
        
        for server in servers:
            metadata = getattr(server, 'metadata', {})
            if 'destroy_at' in metadata:
                try:
                    destroy_time = datetime.fromisoformat(metadata['destroy_at'].replace('Z', '+00:00'))
                    if destroy_time.tzinfo:
                        destroy_time = destroy_time.replace(tzinfo=None)
                    
                    # 检查是否已到期
                    if current_time >= destroy_time:
                        expired_instances.append({
                            'id': server.id,
                            'name': server.name,
                            'status': server.status,
                            'destroy_at': metadata['destroy_at'],
                            'destroy_set_by': metadata.get('destroy_set_by', 'Unknown'),
                            'days_expired': (current_time - destroy_time).days
                        })
                    # 检查是否在24小时内到期
                    elif (destroy_time - current_time).total_seconds() <= 86400:  # 24小时
                        hours_left = int((destroy_time - current_time).total_seconds() / 3600)
                        warning_instances.append({
                            'id': server.id,
                            'name': server.name,
                            'status': server.status,
                            'destroy_at': metadata['destroy_at'],
                            'destroy_set_by': metadata.get('destroy_set_by', 'Unknown'),
                            'hours_left': hours_left
                        })
                except Exception as e:
                    logger.warning(f"Invalid destroy_at format for instance {server.id}: {e}")
        
        return jsonify({
            'success': True,
            'data': {
                'expired_instances': expired_instances,
                'warning_instances': warning_instances,
                'expired_count': len(expired_instances),
                'warning_count': len(warning_instances),
                'cluster_name': cluster.name,
                'check_time': current_time.isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to check expired instances: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/create-data', methods=['GET'])
@login_required
def get_create_data():
    """获取创建实例所需的数据"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        neutron_client = clients['neutron']
        glance_client = clients['glance']
        
        # 获取镜像列表
        logger.info("获取镜像列表")
        try:
            images = list(glance_client.images.list())
            image_list = []
            for image in images:
                if hasattr(image, 'status') and image.status == 'active':
                    image_info = {
                        'id': image.id,
                        'name': image.name,
                        'status': image.status,
                        'size': getattr(image, 'size', 0),
                        'disk_format': getattr(image, 'disk_format', 'unknown'),
                        'container_format': getattr(image, 'container_format', 'unknown'),
                        'visibility': getattr(image, 'visibility', 'private'),
                        'min_disk': getattr(image, 'min_disk', 0),
                        'min_ram': getattr(image, 'min_ram', 0),
                        'created_at': getattr(image, 'created_at', None),
                        'updated_at': getattr(image, 'updated_at', None)
                    }
                    image_list.append(image_info)
        except Exception as e:
            logger.warning(f"获取镜像列表失败: {e}")
            image_list = []
        
        # 获取规格列表
        logger.info("获取规格列表")
        try:
            flavors = nova_client.flavors.list(detailed=True)
            flavor_list = []
            for flavor in flavors:
                if not getattr(flavor, 'OS-FLV-DISABLED:disabled', False):
                    flavor_info = {
                        'id': flavor.id,
                        'name': flavor.name,
                        'vcpus': flavor.vcpus,
                        'ram': flavor.ram,
                        'disk': flavor.disk,
                        'swap': getattr(flavor, 'swap', 0),
                        'ephemeral': getattr(flavor, 'OS-FLV-EXT-DATA:ephemeral', 0),
                        'rxtx_factor': getattr(flavor, 'rxtx_factor', 1.0),
                        'is_public': getattr(flavor, 'os-flavor-access:is_public', True)
                    }
                    flavor_list.append(flavor_info)
        except Exception as e:
            logger.warning(f"获取规格列表失败: {e}")
            flavor_list = []
        
        # 获取网络列表
        logger.info("获取网络列表")
        try:
            networks = neutron_client.list_networks()['networks']
            network_list = []
            for network in networks:
                if network.get('status') == 'ACTIVE':
                    # 获取子网信息
                    subnets = []
                    for subnet_id in network.get('subnets', []):
                        try:
                            subnet = neutron_client.show_subnet(subnet_id)['subnet']
                            subnets.append({
                                'id': subnet['id'],
                                'name': subnet['name'],
                                'cidr': subnet['cidr'],
                                'gateway_ip': subnet.get('gateway_ip'),
                                'ip_version': subnet['ip_version']
                            })
                        except:
                            pass
                    
                    network_info = {
                        'id': network['id'],
                        'name': network['name'],
                        'status': network['status'],
                        'admin_state_up': network.get('admin_state_up', True),
                        'shared': network.get('shared', False),
                        'external': network.get('router:external', False),
                        'subnets': subnets
                    }
                    network_list.append(network_info)
        except Exception as e:
            logger.warning(f"获取网络列表失败: {e}")
            network_list = []
        
        # 获取密钥对列表
        logger.info("获取密钥对列表")
        try:
            keypairs = nova_client.keypairs.list()
            keypair_list = []
            for kp in keypairs:
                keypair_info = {
                    'name': kp.name,
                    'fingerprint': getattr(kp, 'fingerprint', ''),
                    'type': getattr(kp, 'type', 'ssh')
                }
                keypair_list.append(keypair_info)
        except Exception as e:
            logger.warning(f"获取密钥对列表失败: {e}")
            keypair_list = []
        
        # 获取安全组列表
        logger.info("获取安全组列表")
        try:
            security_groups = neutron_client.list_security_groups()['security_groups']
            sg_list = []
            for sg in security_groups:
                sg_info = {
                    'id': sg['id'],
                    'name': sg['name'],
                    'description': sg.get('description', ''),
                    'tenant_id': sg.get('tenant_id', ''),
                    'rules_count': len(sg.get('security_group_rules', []))
                }
                sg_list.append(sg_info)
        except Exception as e:
            logger.warning(f"获取安全组列表失败: {e}")
            sg_list = []
        
        # 获取可用区列表
        logger.info("获取可用区列表")
        try:
            availability_zones = nova_client.availability_zones.list()
            az_list = []
            for az in availability_zones:
                if az.zoneState.get('available'):
                    az_info = {
                        'name': az.zoneName,
                        'available': az.zoneState.get('available', False),
                        'hosts': list(az.hosts.keys()) if hasattr(az, 'hosts') else []
                    }
                    az_list.append(az_info)
        except Exception as e:
            logger.warning(f"获取可用区列表失败: {e}")
            az_list = []
        
        return jsonify({
            'success': True,
            'data': {
                'images': image_list,
                'flavors': flavor_list,
                'networks': network_list,
                'keypairs': keypair_list,
                'security_groups': sg_list,
                'availability_zones': az_list,
                'cluster_name': cluster.name
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get create data: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/create', methods=['POST'])
@login_required
def create_instance():
    """创建实例"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        # 验证必填字段
        required_fields = ['name', 'image_id', 'flavor_id', 'networks']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        nova_client = clients['nova']
        
        # 构建创建参数
        instance_params = {
            'name': data['name'],
            'image': data['image_id'],
            'flavor': data['flavor_id'],
            'nics': []
        }
        
        # 处理网络配置
        for network_id in data['networks']:
            instance_params['nics'].append({'net-id': network_id})
        
        # 可选参数
        if data.get('key_name'):
            instance_params['key_name'] = data['key_name']
        
        if data.get('security_groups'):
            instance_params['security_groups'] = data['security_groups']
        
        if data.get('availability_zone'):
            instance_params['availability_zone'] = data['availability_zone']
        
        if data.get('user_data'):
            instance_params['userdata'] = data['user_data']
        
        if data.get('count') and data['count'] > 1:
            instance_params['min_count'] = data['count']
            instance_params['max_count'] = data['count']
        
        # 添加元数据
        metadata = {
            'created_by': current_user.username,
            'created_at': datetime.utcnow().isoformat(),
            'cluster_name': cluster.name
        }
        
        if data.get('description'):
            metadata['description'] = data['description']
        
        instance_params['meta'] = metadata
        
        # 创建实例
        logger.info(f"Creating instance: {data['name']} on cluster {cluster.name}")
        server = nova_client.servers.create(**instance_params)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='instance_create',
            operation_object=f'instance:{data["name"]}',
            result='success',
            details=f'创建实例: {data["name"]}, 镜像: {data["image_id"]}, 规格: {data["flavor_id"]}'
        )
        
        return jsonify({
            'success': True,
            'message': f'实例 {data["name"]} 创建任务已提交',
            'data': {
                'instance_id': server.id,
                'name': server.name,
                'status': server.status,
                'created': server.created
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create instance: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type='instance_create',
                operation_object=f'instance:{data.get("name", "unknown")}',
                result='failed',
                details=f'创建实例失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/instances/all-clusters', methods=['GET'])
@login_required
def list_all_cluster_instances():
    """获取所有集群的实例列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        expire_filter = request.args.get('expire_filter')  # normal, warning, expired
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        
        # 获取所有实例数据
        all_instances = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                nova_client = clients['nova']
                
                # 获取集群实例
                logger.info(f"Getting instances for cluster {cluster.name}")
                servers = nova_client.servers.list(detailed=True)
                
                # 处理每个实例
                for server in servers:
                    all_instances.append((server, cluster))
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get instances from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式，并添加到期状态
        instances = []
        current_time = datetime.utcnow()
        
        for server, cluster in all_instances:
            metadata = getattr(server, 'metadata', {})
            expire_status = 'normal'  # normal, warning, expired
            
            # 检查销毁时间
            if 'destroy_at' in metadata:
                try:
                    destroy_time = datetime.fromisoformat(metadata['destroy_at'].replace('Z', '+00:00'))
                    if destroy_time.tzinfo:
                        destroy_time = destroy_time.replace(tzinfo=None)
                    
                    if current_time >= destroy_time:
                        expire_status = 'expired'
                    elif (destroy_time - current_time).total_seconds() <= 86400:  # 24小时内
                        expire_status = 'warning'
                except Exception:
                    pass
            
            instance_data = {
                'id': server.id,
                'name': server.name,
                'status': server.status,
                'power_state': getattr(server, 'OS-EXT-STS:power_state', 0),
                'task_state': getattr(server, 'OS-EXT-STS:task_state', None),
                'vm_state': getattr(server, 'OS-EXT-STS:vm_state', None),
                'created': server.created,
                'updated': server.updated,
                'cluster_id': cluster.id,
                'cluster_name': cluster.name,
                'flavor': {
                    'id': server.flavor['id'],
                    'name': getattr(server.flavor, 'name', 'Unknown')
                },
                'image': {
                    'id': server.image['id'] if server.image else None,
                    'name': getattr(server.image, 'name', 'Unknown') if server.image else 'Boot from volume'
                },
                'key_name': getattr(server, 'key_name', None),
                'availability_zone': getattr(server, 'OS-EXT-AZ:availability_zone', None),
                'host': getattr(server, 'OS-EXT-SRV-ATTR:host', None),
                'addresses': dict(server.addresses) if hasattr(server, 'addresses') else {},
                'metadata': metadata,
                'security_groups': [sg['name'] for sg in getattr(server, 'security_groups', [])],
                'volumes_attached': getattr(server, 'os-extended-volumes:volumes_attached', []),
                'expire_status': expire_status
            }
            instances.append(instance_data)
        
        # 应用过滤器
        filtered_instances = instances
        
        # 状态过滤
        if status:
            filtered_instances = [inst for inst in filtered_instances if inst['status'].lower() == status.lower()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_instances = [
                inst for inst in filtered_instances
                if search_lower in inst['name'].lower() or search_lower in inst['id']
            ]
        
        # 到期状态过滤
        if expire_filter:
            filtered_instances = [
                inst for inst in filtered_instances
                if inst['expire_status'] == expire_filter
            ]
        
        # 分页
        total = len(filtered_instances)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_instances = filtered_instances[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        expire_counts = {'normal': 0, 'warning': 0, 'expired': 0}
        
        for instance in instances:
            status = instance['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # 统计到期状态
            expire_status = instance['expire_status']
            expire_counts[expire_status] = expire_counts.get(expire_status, 0) + 1
        
        return jsonify({
            'success': True,
            'data': paginated_instances,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_instances': len(instances),
                'filtered_instances': total,
                'status_counts': status_counts,
                'expire_counts': expire_counts,
                'cluster_name': f'所有集群 ({", ".join(cluster_names)})'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list all cluster instances: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/instances/statistics', methods=['GET'])
@login_required
def get_instances_statistics():
    """获取实例统计信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        
        if cluster_id:
            # 单个集群统计
            clusters = [OpenstackCluster.query.get_or_404(cluster_id)]
        else:
            # 所有集群统计
            clusters = OpenstackCluster.get_active_clusters()
        
        total_stats = {
            'total_instances': 0,
            'status_counts': {},
            'clusters': []
        }
        
        for cluster in clusters:
            try:
                clients = openstack_service.get_cluster_clients(cluster.id)
                nova_client = clients['nova']
                servers = nova_client.servers.list(detailed=False)
                
                cluster_stats = {
                    'cluster_id': cluster.id,
                    'cluster_name': cluster.name,
                    'instance_count': len(servers),
                    'status_counts': {}
                }
                
                # 统计各状态实例数量
                for server in servers:
                    status = server.status
                    cluster_stats['status_counts'][status] = cluster_stats['status_counts'].get(status, 0) + 1
                    total_stats['status_counts'][status] = total_stats['status_counts'].get(status, 0) + 1
                
                total_stats['total_instances'] += len(servers)
                total_stats['clusters'].append(cluster_stats)
                
            except Exception as e:
                logger.warning(f"Failed to get statistics for cluster {cluster.name}: {e}")
                cluster_stats = {
                    'cluster_id': cluster.id,
                    'cluster_name': cluster.name,
                    'instance_count': 0,
                    'status_counts': {},
                    'error': str(e)
                }
                total_stats['clusters'].append(cluster_stats)
        
        return jsonify({
            'success': True,
            'data': total_stats
        })
        
    except Exception as e:
        logger.error(f"Failed to get instances statistics: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500