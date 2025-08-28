"""
卷管理API路由
提供OpenStack卷的管理操作
"""
import logging
from datetime import datetime
from flask import request, jsonify, send_file
from flask_login import login_required, current_user
from . import api_bp as api
from app.models.base import db
from app.models.cluster import OpenstackCluster
from app.models.log import OperationLog
from app.services.openstack_service import openstack_service

logger = logging.getLogger(__name__)

@api.route('/volumes', methods=['GET'])
@login_required
def list_volumes():
    """获取卷列表"""
    try:
        # 获取查询参数
        cluster_id = request.args.get('cluster_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        volume_type = request.args.get('volume_type')
        
        # 如果没有指定集群ID，选择默认集群
        if not cluster_id:
            default_cluster = OpenstackCluster.query.filter_by(is_active=True).first()
            if not default_cluster:
                return jsonify({'success': False, 'error': '没有可用的集群'}), 400
            clusters = [default_cluster]
        else:
            clusters = [OpenstackCluster.query.get_or_404(cluster_id)]
        
        # 获取所有卷数据
        all_volumes = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                cinder_client = clients['cinder']
                
                # 获取集群卷
                logger.info(f"Getting volumes for cluster {cluster.name}")
                volumes = cinder_client.volumes.list(detailed=True)
                
                # 处理每个卷
                for volume in volumes:
                    all_volumes.append((volume, cluster))
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get volumes from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式
        volumes_data = []
        
        for volume, cluster in all_volumes:
            # 获取挂载信息
            attachments = []
            for attachment in getattr(volume, 'attachments', []):
                attachments.append({
                    'instance_id': attachment.get('server_id'),
                    'device': attachment.get('device'),
                    'attached_at': attachment.get('attached_at')
                })
            
            volume_data = {
                'id': volume.id,
                'name': volume.name or volume.id,
                'description': getattr(volume, 'description', ''),
                'status': volume.status,
                'size': volume.size,
                'volume_type': getattr(volume, 'volume_type', 'Unknown'),
                'created_at': volume.created_at,
                'updated_at': getattr(volume, 'updated_at', None),
                'cluster_id': cluster.id,
                'cluster_name': cluster.name,
                'availability_zone': getattr(volume, 'availability_zone', None),
                'bootable': getattr(volume, 'bootable', False),
                'encrypted': getattr(volume, 'encrypted', False),
                'attachments': attachments,
                'metadata': getattr(volume, 'metadata', {}),
                'snapshot_id': getattr(volume, 'snapshot_id', None),
                'source_volid': getattr(volume, 'source_volid', None)
            }
            volumes_data.append(volume_data)
        
        # 应用过滤器
        filtered_volumes = volumes_data
        
        # 状态过滤
        if status:
            filtered_volumes = [vol for vol in filtered_volumes if vol['status'].lower() == status.lower()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_volumes = [
                vol for vol in filtered_volumes
                if search_lower in vol['name'].lower() or search_lower in vol['id']
            ]
        
        # 分页
        total = len(filtered_volumes)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_volumes = filtered_volumes[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        for volume in volumes_data:
            status = volume['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return jsonify({
            'success': True,
            'data': paginated_volumes,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_volumes': len(volumes_data),
                'filtered_volumes': total,
                'status_counts': status_counts,
                'cluster_name': cluster_names[0] if len(cluster_names) == 1 else f"共 {len(cluster_names)} 个集群"
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list volumes: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/volumes/all-clusters', methods=['GET'])
@login_required
def list_all_cluster_volumes():
    """获取所有集群的卷列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        volume_type = request.args.get('volume_type')
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        
        # 获取所有卷数据
        all_volumes = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                cinder_client = clients['cinder']
                
                # 获取集群卷
                logger.info(f"Getting volumes for cluster {cluster.name}")
                volumes = cinder_client.volumes.list(detailed=True)
                
                # 处理每个卷
                for volume in volumes:
                    all_volumes.append((volume, cluster))
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get volumes from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式
        volumes_data = []
        
        for volume, cluster in all_volumes:
            # 获取挂载信息
            attachments = []
            for attachment in getattr(volume, 'attachments', []):
                attachments.append({
                    'instance_id': attachment.get('server_id'),
                    'device': attachment.get('device'),
                    'attached_at': attachment.get('attached_at')
                })
            
            volume_data = {
                'id': volume.id,
                'name': volume.name or volume.id,
                'description': getattr(volume, 'description', ''),
                'status': volume.status,
                'size': volume.size,
                'volume_type': getattr(volume, 'volume_type', 'Unknown'),
                'created_at': volume.created_at,
                'updated_at': getattr(volume, 'updated_at', None),
                'cluster_id': cluster.id,
                'cluster_name': cluster.name,
                'availability_zone': getattr(volume, 'availability_zone', None),
                'bootable': getattr(volume, 'bootable', False),
                'encrypted': getattr(volume, 'encrypted', False),
                'attachments': attachments,
                'metadata': getattr(volume, 'metadata', {}),
                'snapshot_id': getattr(volume, 'snapshot_id', None),
                'source_volid': getattr(volume, 'source_volid', None)
            }
            volumes_data.append(volume_data)
        
        # 应用过滤器
        filtered_volumes = volumes_data
        
        # 状态过滤
        if status:
            filtered_volumes = [vol for vol in filtered_volumes if vol['status'].lower() == status.lower()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_volumes = [
                vol for vol in filtered_volumes
                if search_lower in vol['name'].lower() or search_lower in vol['id']
            ]
        
        # 分页
        total = len(filtered_volumes)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_volumes = filtered_volumes[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        for volume in volumes_data:
            status = volume['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return jsonify({
            'success': True,
            'data': paginated_volumes,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_volumes': len(volumes_data),
                'filtered_volumes': total,
                'status_counts': status_counts,
                'cluster_name': f'所有集群 ({", ".join(cluster_names)})'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list all cluster volumes: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/volumes/<volume_id>', methods=['GET'])
@login_required
def get_volume_detail(volume_id):
    """获取卷详细信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        cinder_client = clients['cinder']
        
        # 获取卷详情
        volume = cinder_client.volumes.get(volume_id)
        
        # 获取挂载信息
        attachments = []
        for attachment in getattr(volume, 'attachments', []):
            attachments.append({
                'instance_id': attachment.get('server_id'),
                'device': attachment.get('device'),
                'attached_at': attachment.get('attached_at')
            })
        
        volume_detail = {
            'id': volume.id,
            'name': volume.name or volume.id,
            'description': getattr(volume, 'description', ''),
            'status': volume.status,
            'size': volume.size,
            'volume_type': getattr(volume, 'volume_type', 'Unknown'),
            'created_at': volume.created_at,
            'updated_at': getattr(volume, 'updated_at', None),
            'availability_zone': getattr(volume, 'availability_zone', None),
            'bootable': getattr(volume, 'bootable', False),
            'encrypted': getattr(volume, 'encrypted', False),
            'attachments': attachments,
            'metadata': getattr(volume, 'metadata', {}),
            'snapshot_id': getattr(volume, 'snapshot_id', None),
            'source_volid': getattr(volume, 'source_volid', None),
            'cluster_name': cluster.name
        }
        
        return jsonify({
            'success': True,
            'data': volume_detail
        })
        
    except Exception as e:
        logger.error(f"Failed to get volume detail {volume_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/volumes/<volume_id>/action', methods=['POST'])
@login_required
def volume_action(volume_id):
    """执行卷操作"""
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
        cinder_client = clients['cinder']
        
        # 获取卷信息用于日志记录
        volume = cinder_client.volumes.get(volume_id)
        volume_name = volume.name or volume.id
        
        result_message = ""
        
        # 执行不同的操作
        if action == 'attach':
            instance_id = data.get('instance_id')
            if not instance_id:
                return jsonify({'success': False, 'error': '挂载卷需要指定实例ID'}), 400
            
            # 获取Nova客户端来挂载卷
            nova_client = clients['nova']
            nova_client.volumes.create_server_volume(instance_id, volume_id)
            result_message = f"卷 {volume_name} 挂载到实例 {instance_id} 的命令已发送"
            
        elif action == 'detach':
            instance_id = data.get('instance_id')
            if not instance_id:
                return jsonify({'success': False, 'error': '卸载卷需要指定实例ID'}), 400
            
            # 获取Nova客户端来卸载卷
            nova_client = clients['nova']
            nova_client.volumes.delete_server_volume(instance_id, volume_id)
            result_message = f"卷 {volume_name} 从实例 {instance_id} 卸载命令已发送"
            
        elif action == 'extend':
            new_size = data.get('new_size')
            if not new_size:
                return jsonify({'success': False, 'error': '扩展卷需要指定新大小'}), 400
            
            cinder_client.volumes.extend(volume_id, new_size)
            result_message = f"卷 {volume_name} 扩展到 {new_size}GB 的命令已发送"
            
        elif action == 'delete':
            # 删除操作需要管理员权限
            if not current_user.has_role(['super_admin', 'admin']):
                return jsonify({'success': False, 'error': '删除卷需要管理员权限'}), 403
            cinder_client.volumes.delete(volume_id)
            result_message = f"卷 {volume_name} 删除命令已发送"
            
        else:
            return jsonify({'success': False, 'error': f'不支持的操作: {action}'}), 400
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'volume_{action}',
            operation_object=f'volume:{volume_name}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'action': action,
            'volume_id': volume_id,
            'volume_name': volume_name
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to perform action {action} on volume {volume_id}: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type=f'volume_{action}',
                operation_object=f'volume:{volume_id}',
                result='failed',
                details=f'操作失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/volumes/create', methods=['POST'])
@login_required
def create_volume():
    """创建卷"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        # 验证必填字段
        required_fields = ['name', 'size']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        clients = openstack_service.get_cluster_clients(cluster_id)
        cinder_client = clients['cinder']
        
        # 构建创建参数
        volume_params = {
            'name': data['name'],
            'size': int(data['size'])
        }
        
        # 可选参数
        if data.get('description'):
            volume_params['description'] = data['description']
        
        if data.get('volume_type'):
            volume_params['volume_type'] = data['volume_type']
        
        if data.get('availability_zone'):
            volume_params['availability_zone'] = data['availability_zone']
        
        if data.get('snapshot_id'):
            volume_params['snapshot_id'] = data['snapshot_id']
        
        if data.get('source_volid'):
            volume_params['source_volid'] = data['source_volid']
        
        # 创建卷
        logger.info(f"Creating volume: {data['name']} on cluster {cluster.name}")
        volume = cinder_client.volumes.create(**volume_params)
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='volume_create',
            operation_object=f'volume:{data["name"]}',
            result='success',
            details=f'创建卷: {data["name"]}, 大小: {data["size"]}GB'
        )
        
        return jsonify({
            'success': True,
            'message': f'卷 {data["name"]} 创建任务已提交',
            'data': {
                'volume_id': volume.id,
                'name': volume.name,
                'status': volume.status,
                'size': volume.size
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create volume: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type='volume_create',
                operation_object=f'volume:{data.get("name", "unknown")}',
                result='failed',
                details=f'创建卷失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/volumes/batch-action', methods=['POST'])
@login_required
def batch_volume_action():
    """批量卷操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        data = request.get_json()
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '缺少集群ID参数'}), 400
        
        if not data or not data.get('volume_ids') or not data.get('action'):
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        volume_ids = data['volume_ids']
        action = data['action']
        
        # 验证操作类型
        if action not in ['delete', 'detach']:
            return jsonify({'success': False, 'error': '不支持的操作类型'}), 400
        
        cluster = OpenstackCluster.query.get(cluster_id)
        if not cluster:
            return jsonify({'success': False, 'error': '集群不存在'}), 404
        
        results = []
        success_count = 0
        
        for volume_id in volume_ids:
            try:
                # 获取卷信息
                volume_info = openstack_service.get_volume_detail(cluster_id, volume_id)
                volume_name = volume_info.get('name', volume_id) if volume_info else volume_id
                
                # 执行操作
                if action == 'delete':
                    success = openstack_service.delete_volume(cluster_id, volume_id)
                    if success:
                        message = '删除成功'
                        success_count += 1
                        # 记录成功日志
                        OperationLog.log_operation(
                            user_id=current_user.id,
                            cluster_id=cluster_id,
                            operation_type='volume_batch_delete',
                            operation_object=f'volume:{volume_id}',
                            result='success',
                            details=f'批量删除卷: {volume_name}'
                        )
                    else:
                        message = '删除失败'
                elif action == 'detach':
                    success = openstack_service.detach_all_volume(cluster_id, volume_id)
                    if success:
                        message = '卸载成功'
                        success_count += 1
                        # 记录成功日志
                        OperationLog.log_operation(
                            user_id=current_user.id,
                            cluster_id=cluster_id,
                            operation_type='volume_batch_detach',
                            operation_object=f'volume:{volume_id}',
                            result='success',
                            details=f'批量卸载卷: {volume_name}'
                        )
                    else:
                        message = '卸载失败'
                
                results.append({
                    'volume_id': volume_id,
                    'volume_name': volume_name,
                    'cluster_name': cluster.name,
                    'success': success,
                    'message': message if success else '操作失败',
                    'error': None if success else '操作执行失败'
                })
                
            except Exception as e:
                error_msg = str(e)
                results.append({
                    'volume_id': volume_id,
                    'volume_name': volume_id,  # 如果获取不到名称就用ID
                    'cluster_name': cluster.name,
                    'success': False,
                    'message': None,
                    'error': error_msg
                })
        
        return jsonify({
            'success': True,
            'message': f'批量{action}操作完成，成功: {success_count}/{len(volume_ids)}',
            'data': {
                'total_count': len(volume_ids),
                'success_count': success_count,
                'results': results
            },
            'total_count': len(volume_ids),
            'success_count': success_count,
            'results': results
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Batch volume action failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/volumes/batch-action-cross-cluster', methods=['POST'])
@login_required
def batch_volume_action_cross_cluster():
    """跨集群批量卷操作"""
    try:
        data = request.get_json()
        
        if not data or not data.get('volume_ids') or not data.get('action'):
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        volume_ids = data['volume_ids']
        action = data['action']
        
        # 验证操作类型
        if action not in ['delete', 'detach']:
            return jsonify({'success': False, 'error': '不支持的操作类型'}), 400
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        if not clusters:
            return jsonify({'success': False, 'error': '没有可用的集群'}), 404
        
        results = []
        success_count = 0
        
        for volume_id in volume_ids:
            volume_found = False
            
            # 在所有集群中查找该卷
            for cluster in clusters:
                try:
                    volume_info = openstack_service.get_volume_detail(cluster.id, volume_id)
                    if volume_info:
                        volume_found = True
                        volume_name = volume_info.get('name', volume_id)
                        
                        # 执行操作
                        success = False
                        if action == 'delete':
                            success = openstack_service.delete_volume(cluster.id, volume_id)
                            if success:
                                message = '删除成功'
                                success_count += 1
                                # 记录成功日志
                                OperationLog.log_operation(
                                    user_id=current_user.id,
                                    cluster_id=cluster.id,
                                    operation_type='volume_batch_delete_cross',
                                    operation_object=f'volume:{volume_id}',
                                    result='success',
                                    details=f'跨集群批量删除卷: {volume_name}'
                                )
                            else:
                                message = '删除失败'
                        elif action == 'detach':
                            success = openstack_service.detach_all_volume(cluster.id, volume_id)
                            if success:
                                message = '卸载成功'
                                success_count += 1
                                # 记录成功日志
                                OperationLog.log_operation(
                                    user_id=current_user.id,
                                    cluster_id=cluster.id,
                                    operation_type='volume_batch_detach_cross',
                                    operation_object=f'volume:{volume_id}',
                                    result='success',
                                    details=f'跨集群批量卸载卷: {volume_name}'
                                )
                            else:
                                message = '卸载失败'
                        
                        results.append({
                            'volume_id': volume_id,
                            'volume_name': volume_name,
                            'cluster_name': cluster.name,
                            'success': success,
                            'message': message if success else '操作失败',
                            'error': None if success else '操作执行失败'
                        })
                        break
                        
                except Exception as e:
                    # 继续尝试下一个集群
                    continue
            
            if not volume_found:
                results.append({
                    'volume_id': volume_id,
                    'volume_name': volume_id,
                    'cluster_name': '未找到',
                    'success': False,
                    'message': None,
                    'error': '在所有集群中都未找到该卷'
                })
        
        return jsonify({
            'success': True,
            'message': f'跨集群批量{action}操作完成，成功: {success_count}/{len(volume_ids)}',
            'data': {
                'total_count': len(volume_ids),
                'success_count': success_count,
                'results': results
            },
            'total_count': len(volume_ids),
            'success_count': success_count,
            'results': results
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Cross cluster batch volume action failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/volumes/export', methods=['POST'])
@login_required
def export_volumes():
    """导出卷数据到Excel"""
    try:
        import pandas as pd
        from io import BytesIO
        from datetime import datetime
        
        cluster_id = request.args.get('cluster_id', type=int)
        data = request.get_json()
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '缺少集群ID参数'}), 400
        
        cluster = OpenstackCluster.query.get(cluster_id)
        if not cluster:
            return jsonify({'success': False, 'error': '集群不存在'}), 404
        
        export_all = data.get('export_all', True)
        volume_ids = data.get('volume_ids', [])
        filters = data.get('filters', {})
        
        # 获取卷列表
        if export_all:
            # 导出所有卷（可能包含过滤条件）
            volumes = openstack_service.list_volumes(
                cluster_id,
                status=filters.get('status'),
                search=filters.get('search'), 
                volume_type=filters.get('volume_type')
            )
        else:
            # 导出选中的卷
            volumes = []
            for volume_id in volume_ids:
                volume = openstack_service.get_volume_detail(cluster_id, volume_id)
                if volume:
                    volumes.append(volume)
        
        if not volumes:
            return jsonify({'success': False, 'error': '没有找到要导出的卷'}), 400
        
        # 准备Excel数据
        excel_data = []
        for volume in volumes:
            # 处理挂载信息
            attachments_info = ""
            if volume.get('attachments'):
                attachments_info = "; ".join([
                    f"实例:{att.get('server_id', 'N/A')},设备:{att.get('device', 'N/A')}" 
                    for att in volume['attachments']
                ])
            
            excel_data.append({
                '卷ID': volume.get('id', ''),
                '卷名称': volume.get('name', ''),
                '状态': volume.get('status', ''),
                '大小(GB)': volume.get('size', 0),
                '卷类型': volume.get('volume_type', ''),
                '可用区': volume.get('availability_zone', ''),
                '描述': volume.get('description', ''),
                '挂载信息': attachments_info,
                '创建时间': volume.get('created_at', ''),
                '集群名称': cluster.name
            })
        
        # 创建DataFrame
        df = pd.DataFrame(excel_data)
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='卷列表', index=False)
            
            # 设置列宽
            worksheet = writer.sheets['卷列表']
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
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'volumes_{cluster.name}_{timestamp}.xlsx'
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='volume_export',
            operation_object=f'volumes:export',
            result='success',
            details=f'导出卷数据: {len(excel_data)}个卷'
        )
        
        return send_file(
            BytesIO(output.getvalue()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Volume export failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/volumes/export-cross-cluster', methods=['POST'])
@login_required
def export_volumes_cross_cluster():
    """跨集群导出卷数据到Excel"""
    try:
        import pandas as pd
        from io import BytesIO
        from datetime import datetime
        
        data = request.get_json()
        
        export_all = data.get('export_all', True)
        volume_ids = data.get('volume_ids', [])
        filters = data.get('filters', {})
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        if not clusters:
            return jsonify({'success': False, 'error': '没有可用的集群'}), 404
        
        all_volumes = []
        
        if export_all:
            # 导出所有集群的卷
            for cluster in clusters:
                try:
                    volumes = openstack_service.list_volumes(
                        cluster.id,
                        status=filters.get('status'),
                        search=filters.get('search'),
                        volume_type=filters.get('volume_type')
                    )
                    # 为每个卷添加集群信息
                    for volume in volumes:
                        volume['cluster_name'] = cluster.name
                        volume['cluster_id'] = cluster.id
                        all_volumes.append(volume)
                except Exception as e:
                    logger.warning(f"Failed to get volumes from cluster {cluster.name}: {str(e)}")
                    continue
        else:
            # 导出选中的卷
            for volume_id in volume_ids:
                volume_found = False
                for cluster in clusters:
                    try:
                        volume = openstack_service.get_volume_detail(cluster.id, volume_id)
                        if volume:
                            volume['cluster_name'] = cluster.name
                            volume['cluster_id'] = cluster.id
                            all_volumes.append(volume)
                            volume_found = True
                            break
                    except Exception:
                        continue
                
                if not volume_found:
                    logger.warning(f"Volume {volume_id} not found in any cluster")
        
        if not all_volumes:
            return jsonify({'success': False, 'error': '没有找到要导出的卷'}), 400
        
        # 准备Excel数据
        excel_data = []
        for volume in all_volumes:
            # 处理挂载信息
            attachments_info = ""
            if volume.get('attachments'):
                attachments_info = "; ".join([
                    f"实例:{att.get('server_id', 'N/A')},设备:{att.get('device', 'N/A')}" 
                    for att in volume['attachments']
                ])
            
            excel_data.append({
                '卷ID': volume.get('id', ''),
                '卷名称': volume.get('name', ''),
                '状态': volume.get('status', ''),
                '大小(GB)': volume.get('size', 0),
                '卷类型': volume.get('volume_type', ''),
                '可用区': volume.get('availability_zone', ''),
                '描述': volume.get('description', ''),
                '挂载信息': attachments_info,
                '创建时间': volume.get('created_at', ''),
                '集群名称': volume.get('cluster_name', '')
            })
        
        # 创建DataFrame
        df = pd.DataFrame(excel_data)
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='卷列表', index=False)
            
            # 设置列宽
            worksheet = writer.sheets['卷列表']
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
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'volumes_all_clusters_{timestamp}.xlsx'
        
        # 记录操作日志（记录到第一个集群）
        if clusters:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=clusters[0].id,
                operation_type='volume_export_cross',
                operation_object=f'volumes:cross_cluster_export',
                result='success',
                details=f'跨集群导出卷数据: {len(excel_data)}个卷'
            )
        
        return send_file(
            BytesIO(output.getvalue()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Cross cluster volume export failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500