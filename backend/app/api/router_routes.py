"""
路由器管理API路由
提供OpenStack路由器的管理操作
"""
import logging
from datetime import datetime
from flask import request, jsonify, send_file
from flask_login import login_required, current_user
from . import api_bp as api
from app.models.base import db
from app.models.cluster import OpenstackCluster
from app.models.log import OperationLog
from app.services.openstack_service import get_openstack_service

logger = logging.getLogger(__name__)

@api.route('/routers', methods=['GET'])
@login_required
def list_routers():
    """获取路由器列表"""
    try:
        # 获取查询参数
        cluster_id = request.args.get('cluster_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
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
        
        openstack_service = get_openstack_service()
        
        # 获取所有路由器数据
        all_routers = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                neutron_client = clients['neutron']
                
                # 获取集群路由器
                logger.info(f"Getting routers for cluster {cluster.name}")
                routers = neutron_client.list_routers()['routers']
                
                # 处理每个路由器
                for router in routers:
                    # 获取路由器端口信息
                    ports = neutron_client.list_ports(device_id=router['id'])['ports']
                    
                    router_data = {
                        'id': router['id'],
                        'name': router['name'],
                        'description': router.get('description', ''),
                        'status': router['status'],
                        'admin_state_up': router.get('admin_state_up', True),
                        'external_gateway_info': router.get('external_gateway_info'),
                        'routes': router.get('routes', []),
                        'distributed': router.get('distributed', False),
                        'ha': router.get('ha', False),
                        'created_at': router.get('created_at'),
                        'updated_at': router.get('updated_at'),
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'ports_count': len(ports),
                        'tenant_id': router.get('tenant_id'),
                        'project_id': router.get('project_id')
                    }
                    all_routers.append(router_data)
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get routers from cluster {cluster.name}: {e}")
                continue
        
        # 应用过滤器
        filtered_routers = all_routers
        
        # 状态过滤
        if status:
            filtered_routers = [r for r in filtered_routers if r['status'].upper() == status.upper()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_routers = [
                r for r in filtered_routers
                if search_lower in r['name'].lower() or search_lower in r['id']
            ]
        
        # 分页
        total = len(filtered_routers)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_routers = filtered_routers[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        for router in all_routers:
            status = router['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return jsonify({
            'success': True,
            'data': paginated_routers,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_routers': len(all_routers),
                'filtered_routers': total,
                'status_counts': status_counts,
                'cluster_name': cluster_names[0] if len(cluster_names) == 1 else f"共 {len(cluster_names)} 个集群"
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list routers: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/routers/all-clusters', methods=['GET'])
@login_required
def list_all_cluster_routers():
    """获取所有集群的路由器列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        openstack_service = get_openstack_service()
        
        # 获取所有路由器数据
        all_routers = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                neutron_client = clients['neutron']
                
                # 获取集群路由器
                logger.info(f"Getting routers for cluster {cluster.name}")
                routers = neutron_client.list_routers()['routers']
                
                # 处理每个路由器
                for router in routers:
                    # 获取路由器端口信息
                    ports = neutron_client.list_ports(device_id=router['id'])['ports']
                    
                    router_data = {
                        'id': router['id'],
                        'name': router['name'],
                        'description': router.get('description', ''),
                        'status': router['status'],
                        'admin_state_up': router.get('admin_state_up', True),
                        'external_gateway_info': router.get('external_gateway_info'),
                        'routes': router.get('routes', []),
                        'distributed': router.get('distributed', False),
                        'ha': router.get('ha', False),
                        'created_at': router.get('created_at'),
                        'updated_at': router.get('updated_at'),
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'ports_count': len(ports),
                        'tenant_id': router.get('tenant_id'),
                        'project_id': router.get('project_id')
                    }
                    all_routers.append(router_data)
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get routers from cluster {cluster.name}: {e}")
                continue
        
        # 应用过滤器
        filtered_routers = all_routers
        
        # 状态过滤
        if status:
            filtered_routers = [r for r in filtered_routers if r['status'].upper() == status.upper()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_routers = [
                r for r in filtered_routers
                if search_lower in r['name'].lower() or search_lower in r['id']
            ]
        
        # 分页
        total = len(filtered_routers)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_routers = filtered_routers[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        for router in all_routers:
            status = router['status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return jsonify({
            'success': True,
            'data': paginated_routers,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_routers': len(all_routers),
                'filtered_routers': total,
                'status_counts': status_counts,
                'cluster_name': f'所有集群 ({", ".join(cluster_names)})'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list all cluster routers: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/routers/<router_id>', methods=['GET'])
@login_required
def get_router_detail(router_id):
    """获取路由器详细信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        
        # 获取路由器详情
        router_detail = openstack_service.get_router_detail(cluster_id, router_id)
        
        if not router_detail:
            return jsonify({'success': False, 'error': '路由器不存在'}), 404
        
        router_detail['cluster_name'] = cluster.name
        
        return jsonify({
            'success': True,
            'data': router_detail
        })
        
    except Exception as e:
        logger.error(f"Failed to get router detail {router_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/routers/<router_id>/action', methods=['POST'])
@login_required
def router_action(router_id):
    """执行路由器操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        action = data.get('action')
        
        if not action:
            return jsonify({'success': False, 'error': '必须指定操作类型'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        clients = openstack_service.get_cluster_clients(cluster_id)
        neutron_client = clients['neutron']
        
        # 获取路由器信息用于日志记录
        router = neutron_client.show_router(router_id)['router']
        router_name = router['name']
        
        result_message = ""
        
        # 执行不同的操作
        if action == 'update_admin_state':
            admin_state_up = data.get('admin_state_up', True)
            neutron_client.update_router(router_id, {'router': {'admin_state_up': admin_state_up}})
            state_text = "启用" if admin_state_up else "禁用"
            result_message = f"路由器 {router_name} 已{state_text}"
            
        elif action == 'update_name':
            new_name = data.get('name', '').strip()
            if not new_name:
                return jsonify({'success': False, 'error': '路由器名称不能为空'}), 400
            neutron_client.update_router(router_id, {'router': {'name': new_name}})
            result_message = f"路由器已重命名为: {new_name}"
            
        elif action == 'update_description':
            description = data.get('description', '')
            neutron_client.update_router(router_id, {'router': {'description': description}})
            result_message = f"路由器 {router_name} 描述已更新"
            
        elif action == 'set_gateway':
            external_network_id = data.get('external_network_id')
            if not external_network_id:
                return jsonify({'success': False, 'error': '必须指定外部网络ID'}), 400
            
            gateway_info = {
                'network_id': external_network_id,
                'enable_snat': data.get('enable_snat', True)
            }
            
            neutron_client.update_router(router_id, {
                'router': {'external_gateway_info': gateway_info}
            })
            result_message = f"路由器 {router_name} 外部网关已设置"
            
        elif action == 'clear_gateway':
            neutron_client.update_router(router_id, {
                'router': {'external_gateway_info': None}
            })
            result_message = f"路由器 {router_name} 外部网关已清除"
            
        elif action == 'add_interface':
            subnet_id = data.get('subnet_id')
            port_id = data.get('port_id')
            
            if not subnet_id and not port_id:
                return jsonify({'success': False, 'error': '必须指定子网ID或端口ID'}), 400
            
            interface_info = {}
            if subnet_id:
                interface_info['subnet_id'] = subnet_id
            if port_id:
                interface_info['port_id'] = port_id
            
            neutron_client.add_interface_router(router_id, interface_info)
            result_message = f"路由器 {router_name} 接口已添加"
            
        elif action == 'remove_interface':
            subnet_id = data.get('subnet_id')
            port_id = data.get('port_id')
            
            if not subnet_id and not port_id:
                return jsonify({'success': False, 'error': '必须指定子网ID或端口ID'}), 400
            
            interface_info = {}
            if subnet_id:
                interface_info['subnet_id'] = subnet_id
            if port_id:
                interface_info['port_id'] = port_id
            
            neutron_client.remove_interface_router(router_id, interface_info)
            result_message = f"路由器 {router_name} 接口已移除"
            
        elif action == 'delete':
            # 删除操作需要管理员权限
            if not current_user.has_role(['super_admin', 'admin']):
                return jsonify({'success': False, 'error': '删除路由器需要管理员权限'}), 403
            neutron_client.delete_router(router_id)
            result_message = f"路由器 {router_name} 删除命令已发送"
            
        else:
            return jsonify({'success': False, 'error': f'不支持的操作: {action}'}), 400
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'router_{action}',
            operation_object=f'router:{router_name}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'action': action,
            'router_id': router_id,
            'router_name': router_name
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to perform action {action} on router {router_id}: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type=f'router_{action}',
                operation_object=f'router:{router_id}',
                result='failed',
                details=f'操作失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/routers/create', methods=['POST'])
@login_required
def create_router():
    """创建路由器"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        # 验证必填字段
        required_fields = ['name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        clients = openstack_service.get_cluster_clients(cluster_id)
        neutron_client = clients['neutron']
        
        # 构建创建参数
        router_params = {
            'name': data['name'],
            'admin_state_up': data.get('admin_state_up', True)
        }
        
        # 可选参数
        if data.get('description'):
            router_params['description'] = data['description']
        
        if data.get('distributed'):
            router_params['distributed'] = data['distributed']
        
        if data.get('ha'):
            router_params['ha'] = data['ha']
        
        # 外部网关配置
        if data.get('external_network_id'):
            router_params['external_gateway_info'] = {
                'network_id': data['external_network_id'],
                'enable_snat': data.get('enable_snat', True)
            }
        
        # 创建路由器
        logger.info(f"Creating router: {data['name']} on cluster {cluster.name}")
        router = neutron_client.create_router({'router': router_params})['router']
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='router_create',
            operation_object=f'router:{data["name"]}',
            result='success',
            details=f'创建路由器: {data["name"]}'
        )
        
        return jsonify({
            'success': True,
            'message': f'路由器 {data["name"]} 创建成功',
            'data': {
                'router_id': router['id'],
                'name': router['name'],
                'status': router['status']
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create router: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type='router_create',
                operation_object=f'router:{data.get("name", "unknown")}',
                result='failed',
                details=f'创建路由器失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/routers/external-networks', methods=['GET'])
@login_required
def get_external_networks():
    """获取外部网络列表（用于设置路由器网关）"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        openstack_service = get_openstack_service()
        clients = openstack_service.get_cluster_clients(cluster_id)
        neutron_client = clients['neutron']
        
        # 获取外部网络
        networks = neutron_client.list_networks(**{'router:external': True})['networks']
        
        external_networks = []
        for network in networks:
            external_networks.append({
                'id': network['id'],
                'name': network['name'],
                'status': network['status'],
                'admin_state_up': network.get('admin_state_up', True),
                'shared': network.get('shared', False)
            })
        
        return jsonify({
            'success': True,
            'data': external_networks
        })
        
    except Exception as e:
        logger.error(f"Failed to get external networks: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/routers/batch-action', methods=['POST'])
@login_required
def batch_router_action():
    """批量路由器操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        data = request.get_json()
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '缺少集群ID参数'}), 400
        
        if not data or not data.get('router_ids') or not data.get('action'):
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        router_ids = data['router_ids']
        action = data['action']
        
        # 验证操作类型
        if action not in ['delete', 'enable', 'disable']:
            return jsonify({'success': False, 'error': '不支持的操作类型'}), 400
        
        cluster = OpenstackCluster.query.get(cluster_id)
        if not cluster:
            return jsonify({'success': False, 'error': '集群不存在'}), 404
        
        openstack_service = get_openstack_service()
        results = []
        success_count = 0
        
        for router_id in router_ids:
            try:
                # 获取路由器信息
                router_info = openstack_service.get_router_detail(cluster_id, router_id)
                router_name = router_info.get('name', router_id) if router_info else router_id
                
                # 执行操作
                clients = openstack_service.get_cluster_clients(cluster_id)
                neutron_client = clients['neutron']
                
                success = True
                message = ""
                
                try:
                    if action == 'delete':
                        neutron_client.delete_router(router_id)
                        message = '删除成功'
                    elif action == 'enable':
                        neutron_client.update_router(router_id, {'router': {'admin_state_up': True}})
                        message = '启用成功'
                    elif action == 'disable':
                        neutron_client.update_router(router_id, {'router': {'admin_state_up': False}})
                        message = '禁用成功'
                    
                    success_count += 1
                    
                    # 记录成功日志
                    OperationLog.log_operation(
                        user_id=current_user.id,
                        cluster_id=cluster_id,
                        operation_type=f'router_batch_{action}',
                        operation_object=f'router:{router_id}',
                        result='success',
                        details=f'批量{message}路由器: {router_name}'
                    )
                    
                except Exception as op_error:
                    success = False
                    message = f'操作失败: {str(op_error)}'
                
                results.append({
                    'router_id': router_id,
                    'router_name': router_name,
                    'cluster_name': cluster.name,
                    'success': success,
                    'message': message if success else '操作失败',
                    'error': None if success else message
                })
                
            except Exception as e:
                error_msg = str(e)
                results.append({
                    'router_id': router_id,
                    'router_name': router_id,  # 如果获取不到名称就用ID
                    'cluster_name': cluster.name,
                    'success': False,
                    'message': None,
                    'error': error_msg
                })
        
        return jsonify({
            'success': True,
            'message': f'批量{action}操作完成，成功: {success_count}/{len(router_ids)}',
            'data': {
                'total_count': len(router_ids),
                'success_count': success_count,
                'results': results
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Batch router action failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500