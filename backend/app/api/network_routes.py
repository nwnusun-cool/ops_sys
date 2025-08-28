"""
网络管理API路由
提供OpenStack网络的管理操作
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

@api.route('/networks', methods=['GET'])
@login_required
def list_networks():
    """获取网络列表"""
    try:
        # 获取查询参数
        cluster_id = request.args.get('cluster_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        network_type = request.args.get('network_type')  # external, internal
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
        
        # 获取所有网络数据
        all_networks = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                openstack_service = get_openstack_service()
                clients = openstack_service.get_cluster_clients(cluster.id)
                neutron_client = clients['neutron']
                
                # 获取集群网络
                logger.info(f"Getting networks for cluster {cluster.name}")
                networks = neutron_client.list_networks()['networks']
                
                # 处理每个网络
                for network in networks:
                    all_networks.append((network, cluster))
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get networks from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式
        networks_data = []
        
        for network, cluster in all_networks:
            # 获取子网信息
            subnets = []
            for subnet_id in network.get('subnets', []):
                try:
                    openstack_service = get_openstack_service()
                    clients = openstack_service.get_cluster_clients(cluster.id)
                    neutron_client = clients['neutron']
                    subnet = neutron_client.show_subnet(subnet_id)['subnet']
                    subnets.append({
                        'id': subnet['id'],
                        'name': subnet['name'],
                        'cidr': subnet['cidr'],
                        'gateway_ip': subnet.get('gateway_ip'),
                        'ip_version': subnet['ip_version'],
                        'enable_dhcp': subnet.get('enable_dhcp', False),
                        'allocation_pools': subnet.get('allocation_pools', []),
                        'dns_nameservers': subnet.get('dns_nameservers', [])
                    })
                except Exception as e:
                    logger.warning(f"Failed to get subnet {subnet_id}: {e}")
                    continue
            
            network_data = {
                'id': network['id'],
                'name': network['name'],
                'description': network.get('description', ''),
                'status': network['status'],
                'admin_state_up': network.get('admin_state_up', True),
                'shared': network.get('shared', False),
                'external': network.get('router:external', False),
                'provider_network_type': network.get('provider:network_type'),
                'provider_physical_network': network.get('provider:physical_network'),
                'provider_segmentation_id': network.get('provider:segmentation_id'),
                'mtu': network.get('mtu', 1500),
                'port_security_enabled': network.get('port_security_enabled', True),
                'tenant_id': network.get('tenant_id'),
                'project_id': network.get('project_id'),
                'created_at': network.get('created_at'),
                'updated_at': network.get('updated_at'),
                'cluster_id': cluster.id,
                'cluster_name': cluster.name,
                'subnets': subnets,
                'subnets_count': len(subnets)
            }
            networks_data.append(network_data)
        
        # 应用过滤器
        filtered_networks = networks_data
        
        # 网络类型过滤
        if network_type:
            if network_type == 'external':
                filtered_networks = [net for net in filtered_networks if net['external']]
            elif network_type == 'internal':
                filtered_networks = [net for net in filtered_networks if not net['external']]
        
        # 状态过滤
        if status:
            filtered_networks = [net for net in filtered_networks if net['status'].upper() == status.upper()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_networks = [
                net for net in filtered_networks
                if search_lower in net['name'].lower() or search_lower in net['id']
            ]
        
        # 分页
        total = len(filtered_networks)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_networks = filtered_networks[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        type_counts = {'external': 0, 'internal': 0}
        
        for network in networks_data:
            status = network['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if network['external']:
                type_counts['external'] += 1
            else:
                type_counts['internal'] += 1
        
        return jsonify({
            'success': True,
            'data': paginated_networks,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_networks': len(networks_data),
                'filtered_networks': total,
                'status_counts': status_counts,
                'type_counts': type_counts,
                'cluster_name': cluster_names[0] if len(cluster_names) == 1 else f"共 {len(cluster_names)} 个集群"
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list networks: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/networks/all-clusters', methods=['GET'])
@login_required
def list_all_cluster_networks():
    """获取所有集群的网络列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        network_type = request.args.get('network_type')  # external, internal
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        
        # 获取所有网络数据
        all_networks = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                openstack_service = get_openstack_service()
                clients = openstack_service.get_cluster_clients(cluster.id)
                neutron_client = clients['neutron']
                
                # 获取集群网络
                logger.info(f"Getting networks for cluster {cluster.name}")
                networks = neutron_client.list_networks()['networks']
                
                # 处理每个网络
                for network in networks:
                    all_networks.append((network, cluster))
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get networks from cluster {cluster.name}: {e}")
                continue
        
        # 转换为字典格式
        networks_data = []
        
        for network, cluster in all_networks:
            # 获取子网信息
            subnets = []
            for subnet_id in network.get('subnets', []):
                try:
                    openstack_service = get_openstack_service()
                    clients = openstack_service.get_cluster_clients(cluster.id)
                    neutron_client = clients['neutron']
                    subnet = neutron_client.show_subnet(subnet_id)['subnet']
                    subnets.append({
                        'id': subnet['id'],
                        'name': subnet['name'],
                        'cidr': subnet['cidr'],
                        'gateway_ip': subnet.get('gateway_ip'),
                        'ip_version': subnet['ip_version'],
                        'enable_dhcp': subnet.get('enable_dhcp', False)
                    })
                except Exception as e:
                    logger.warning(f"Failed to get subnet {subnet_id}: {e}")
                    continue
            
            network_data = {
                'id': network['id'],
                'name': network['name'],
                'description': network.get('description', ''),
                'status': network['status'],
                'admin_state_up': network.get('admin_state_up', True),
                'shared': network.get('shared', False),
                'external': network.get('router:external', False),
                'provider_network_type': network.get('provider:network_type'),
                'mtu': network.get('mtu', 1500),
                'cluster_id': cluster.id,
                'cluster_name': cluster.name,
                'subnets': subnets,
                'subnets_count': len(subnets)
            }
            networks_data.append(network_data)
        
        # 应用过滤器
        filtered_networks = networks_data
        
        # 网络类型过滤
        if network_type:
            if network_type == 'external':
                filtered_networks = [net for net in filtered_networks if net['external']]
            elif network_type == 'internal':
                filtered_networks = [net for net in filtered_networks if not net['external']]
        
        # 状态过滤
        if status:
            filtered_networks = [net for net in filtered_networks if net['status'].upper() == status.upper()]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_networks = [
                net for net in filtered_networks
                if search_lower in net['name'].lower() or search_lower in net['id']
            ]
        
        # 分页
        total = len(filtered_networks)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_networks = filtered_networks[start_idx:end_idx]
        
        # 统计信息
        status_counts = {}
        type_counts = {'external': 0, 'internal': 0}
        
        for network in networks_data:
            status = network['status']
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if network['external']:
                type_counts['external'] += 1
            else:
                type_counts['internal'] += 1
        
        return jsonify({
            'success': True,
            'data': paginated_networks,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_networks': len(networks_data),
                'filtered_networks': total,
                'status_counts': status_counts,
                'type_counts': type_counts,
                'cluster_name': f'所有集群 ({", ".join(cluster_names)})'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list all cluster networks: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/networks/<network_id>', methods=['GET'])
@login_required
def get_network_detail(network_id):
    """获取网络详细信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        clients = openstack_service.get_cluster_clients(cluster_id)
        neutron_client = clients['neutron']
        
        # 获取网络详情
        network = neutron_client.show_network(network_id)['network']
        
        # 获取子网详情
        subnets = []
        for subnet_id in network.get('subnets', []):
            try:
                subnet = neutron_client.show_subnet(subnet_id)['subnet']
                subnets.append({
                    'id': subnet['id'],
                    'name': subnet['name'],
                    'cidr': subnet['cidr'],
                    'gateway_ip': subnet.get('gateway_ip'),
                    'ip_version': subnet['ip_version'],
                    'enable_dhcp': subnet.get('enable_dhcp', False),
                    'allocation_pools': subnet.get('allocation_pools', []),
                    'dns_nameservers': subnet.get('dns_nameservers', []),
                    'host_routes': subnet.get('host_routes', []),
                    'created_at': subnet.get('created_at'),
                    'updated_at': subnet.get('updated_at')
                })
            except Exception as e:
                logger.warning(f"Failed to get subnet {subnet_id}: {e}")
                continue
        
        # 获取端口信息
        try:
            ports = neutron_client.list_ports(network_id=network_id)['ports']
            port_count = len(ports)
        except Exception as e:
            logger.warning(f"Failed to get ports for network {network_id}: {e}")
            port_count = 0
        
        network_detail = {
            'id': network['id'],
            'name': network['name'],
            'description': network.get('description', ''),
            'status': network['status'],
            'admin_state_up': network.get('admin_state_up', True),
            'shared': network.get('shared', False),
            'external': network.get('router:external', False),
            'provider_network_type': network.get('provider:network_type'),
            'provider_physical_network': network.get('provider:physical_network'),
            'provider_segmentation_id': network.get('provider:segmentation_id'),
            'mtu': network.get('mtu', 1500),
            'port_security_enabled': network.get('port_security_enabled', True),
            'tenant_id': network.get('tenant_id'),
            'project_id': network.get('project_id'),
            'created_at': network.get('created_at'),
            'updated_at': network.get('updated_at'),
            'availability_zones': network.get('availability_zones', []),
            'availability_zone_hints': network.get('availability_zone_hints', []),
            'cluster_name': cluster.name,
            'subnets': subnets,
            'port_count': port_count
        }
        
        return jsonify({
            'success': True,
            'data': network_detail
        })
        
    except Exception as e:
        logger.error(f"Failed to get network detail {network_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/networks/<network_id>/action', methods=['POST'])
@login_required
def network_action(network_id):
    """执行网络操作"""
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
        
        # 获取网络信息用于日志记录
        network = neutron_client.show_network(network_id)['network']
        network_name = network['name']
        
        result_message = ""
        
        # 执行不同的操作
        if action == 'update_admin_state':
            admin_state_up = data.get('admin_state_up', True)
            neutron_client.update_network(network_id, {'network': {'admin_state_up': admin_state_up}})
            state_text = "启用" if admin_state_up else "禁用"
            result_message = f"网络 {network_name} 已{state_text}"
            
        elif action == 'update_shared':
            shared = data.get('shared', False)
            neutron_client.update_network(network_id, {'network': {'shared': shared}})
            share_text = "设为共享" if shared else "取消共享"
            result_message = f"网络 {network_name} 已{share_text}"
            
        elif action == 'update_name':
            new_name = data.get('name', '').strip()
            if not new_name:
                return jsonify({'success': False, 'error': '网络名称不能为空'}), 400
            neutron_client.update_network(network_id, {'network': {'name': new_name}})
            result_message = f"网络已重命名为: {new_name}"
            
        elif action == 'update_description':
            description = data.get('description', '')
            neutron_client.update_network(network_id, {'network': {'description': description}})
            result_message = f"网络 {network_name} 描述已更新"
            
        elif action == 'delete':
            # 删除操作需要管理员权限
            if not current_user.has_role(['super_admin', 'admin']):
                return jsonify({'success': False, 'error': '删除网络需要管理员权限'}), 403
            neutron_client.delete_network(network_id)
            result_message = f"网络 {network_name} 删除命令已发送"
            
        else:
            return jsonify({'success': False, 'error': f'不支持的操作: {action}'}), 400
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'network_{action}',
            operation_object=f'network:{network_name}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'action': action,
            'network_id': network_id,
            'network_name': network_name
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to perform action {action} on network {network_id}: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type=f'network_{action}',
                operation_object=f'network:{network_id}',
                result='failed',
                details=f'操作失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/networks/create', methods=['POST'])
@login_required
def create_network():
    """创建网络"""
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
        network_params = {
            'name': data['name'],
            'admin_state_up': data.get('admin_state_up', True)
        }
        
        # 可选参数
        if 'description' in data:
            network_params['description'] = data['description']
        
        if 'shared' in data:
            network_params['shared'] = data['shared']
        
        if 'external' in data and data['external']:
            network_params['router:external'] = True
        
        if 'provider_network_type' in data:
            network_params['provider:network_type'] = data['provider_network_type']
        
        if 'provider_physical_network' in data:
            network_params['provider:physical_network'] = data['provider_physical_network']
        
        if 'provider_segmentation_id' in data:
            network_params['provider:segmentation_id'] = data['provider_segmentation_id']
        
        if 'mtu' in data:
            network_params['mtu'] = data['mtu']
        
        # 创建网络
        logger.info(f"Creating network: {data['name']} on cluster {cluster.name}")
        network = neutron_client.create_network({'network': network_params})['network']
        
        # 创建子网（如果提供）
        created_subnets = []
        if 'subnets' in data and data['subnets']:
            for subnet_data in data['subnets']:
                try:
                    subnet_params = {
                        'network_id': network['id'],
                        'name': subnet_data.get('name', f"{data['name']}-subnet"),
                        'cidr': subnet_data['cidr'],
                        'ip_version': subnet_data.get('ip_version', 4),
                        'enable_dhcp': subnet_data.get('enable_dhcp', True)
                    }
                    
                    if 'gateway_ip' in subnet_data:
                        subnet_params['gateway_ip'] = subnet_data['gateway_ip']
                    
                    if 'allocation_pools' in subnet_data:
                        subnet_params['allocation_pools'] = subnet_data['allocation_pools']
                    
                    if 'dns_nameservers' in subnet_data:
                        subnet_params['dns_nameservers'] = subnet_data['dns_nameservers']
                    
                    subnet = neutron_client.create_subnet({'subnet': subnet_params})['subnet']
                    created_subnets.append(subnet)
                    
                except Exception as e:
                    logger.warning(f"Failed to create subnet for network {network['id']}: {e}")
                    continue
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='network_create',
            operation_object=f'network:{data["name"]}',
            result='success',
            details=f'创建网络: {data["name"]}, 子网数: {len(created_subnets)}'
        )
        
        return jsonify({
            'success': True,
            'message': f'网络 {data["name"]} 创建成功',
            'data': {
                'network_id': network['id'],
                'name': network['name'],
                'status': network['status'],
                'subnets': created_subnets
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create network: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type='network_create',
                operation_object=f'network:{data.get("name", "unknown")}',
                result='failed',
                details=f'创建网络失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/subnets', methods=['GET'])
@login_required
def list_subnets():
    """获取子网列表"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        network_id = request.args.get('network_id')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        clients = openstack_service.get_cluster_clients(cluster_id)
        neutron_client = clients['neutron']
        
        # 获取子网列表
        list_params = {}
        if network_id:
            list_params['network_id'] = network_id
        
        subnets = neutron_client.list_subnets(**list_params)['subnets']
        
        # 转换为详细格式
        subnets_data = []
        for subnet in subnets:
            # 获取网络信息
            try:
                network = neutron_client.show_network(subnet['network_id'])['network']
                network_name = network['name']
            except:
                network_name = 'Unknown'
            
            subnet_data = {
                'id': subnet['id'],
                'name': subnet['name'],
                'description': subnet.get('description', ''),
                'cidr': subnet['cidr'],
                'gateway_ip': subnet.get('gateway_ip'),
                'ip_version': subnet['ip_version'],
                'enable_dhcp': subnet.get('enable_dhcp', False),
                'network_id': subnet['network_id'],
                'network_name': network_name,
                'allocation_pools': subnet.get('allocation_pools', []),
                'dns_nameservers': subnet.get('dns_nameservers', []),
                'host_routes': subnet.get('host_routes', []),
                'tenant_id': subnet.get('tenant_id'),
                'project_id': subnet.get('project_id'),
                'created_at': subnet.get('created_at'),
                'updated_at': subnet.get('updated_at'),
                'cluster_id': cluster.id,
                'cluster_name': cluster.name
            }
            subnets_data.append(subnet_data)
        
        # 搜索过滤
        filtered_subnets = subnets_data
        if search:
            search_lower = search.lower()
            filtered_subnets = [
                subnet for subnet in filtered_subnets
                if search_lower in subnet['name'].lower() or 
                   search_lower in subnet['cidr'].lower() or
                   search_lower in subnet['id']
            ]
        
        # 分页
        total = len(filtered_subnets)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_subnets = filtered_subnets[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'data': paginated_subnets,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_subnets': len(subnets_data),
                'filtered_subnets': total,
                'cluster_name': cluster.name
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list subnets: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/subnets/<subnet_id>/action', methods=['POST'])
@login_required
def subnet_action(subnet_id):
    """执行子网操作"""
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
        
        # 获取子网信息用于日志记录
        subnet = neutron_client.show_subnet(subnet_id)['subnet']
        subnet_name = subnet['name']
        
        result_message = ""
        
        # 执行不同的操作
        if action == 'update_dhcp':
            enable_dhcp = data.get('enable_dhcp', True)
            neutron_client.update_subnet(subnet_id, {'subnet': {'enable_dhcp': enable_dhcp}})
            dhcp_text = "启用" if enable_dhcp else "禁用"
            result_message = f"子网 {subnet_name} DHCP已{dhcp_text}"
            
        elif action == 'update_gateway':
            gateway_ip = data.get('gateway_ip')
            update_data = {'gateway_ip': gateway_ip} if gateway_ip else {'gateway_ip': None}
            neutron_client.update_subnet(subnet_id, {'subnet': update_data})
            result_message = f"子网 {subnet_name} 网关已更新"
            
        elif action == 'update_dns':
            dns_nameservers = data.get('dns_nameservers', [])
            neutron_client.update_subnet(subnet_id, {'subnet': {'dns_nameservers': dns_nameservers}})
            result_message = f"子网 {subnet_name} DNS服务器已更新"
            
        elif action == 'delete':
            # 删除操作需要管理员权限
            if not current_user.has_role(['super_admin', 'admin']):
                return jsonify({'success': False, 'error': '删除子网需要管理员权限'}), 403
            neutron_client.delete_subnet(subnet_id)
            result_message = f"子网 {subnet_name} 删除命令已发送"
            
        else:
            return jsonify({'success': False, 'error': f'不支持的操作: {action}'}), 400
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'subnet_{action}',
            operation_object=f'subnet:{subnet_name}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'action': action,
            'subnet_id': subnet_id,
            'subnet_name': subnet_name
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to perform action {action} on subnet {subnet_id}: {error_msg}")
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/networks/batch-action', methods=['POST'])
@login_required
def batch_network_action():
    """批量网络操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        data = request.get_json()
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '缺少集群ID参数'}), 400
        
        if not data or not data.get('network_ids') or not data.get('action'):
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        network_ids = data['network_ids']
        action = data['action']
        
        # 验证操作类型
        if action not in ['delete', 'enable', 'disable']:
            return jsonify({'success': False, 'error': '不支持的操作类型'}), 400
        
        cluster = OpenstackCluster.query.get(cluster_id)
        if not cluster:
            return jsonify({'success': False, 'error': '集群不存在'}), 404
        
        results = []
        success_count = 0
        
        for network_id in network_ids:
            try:
                # 获取OpenStack服务
                openstack_service = get_openstack_service()
                
                # 获取网络信息
                network_info = openstack_service.get_network_detail(cluster_id, network_id)
                network_name = network_info.get('name', network_id) if network_info else network_id
                
                # 执行操作
                if action == 'delete':
                    success = openstack_service.delete_network(cluster_id, network_id)
                    message = '删除成功' if success else '删除失败'
                elif action in ['enable', 'disable']:
                    success = openstack_service.update_network_admin_state(cluster_id, network_id, action == 'enable')
                    message = f"{'启用' if action == 'enable' else '禁用'}成功" if success else f"{'启用' if action == 'enable' else '禁用'}失败"
                
                if success:
                    success_count += 1
                    # 记录成功日志
                    OperationLog.log_operation(
                        user_id=current_user.id,
                        cluster_id=cluster_id,
                        operation_type=f'network_batch_{action}',
                        operation_object=f'network:{network_id}',
                        result='success',
                        details=f'批量{message}网络: {network_name}'
                    )
                
                results.append({
                    'network_id': network_id,
                    'network_name': network_name,
                    'cluster_name': cluster.name,
                    'success': success,
                    'message': message if success else '操作失败',
                    'error': None if success else '操作执行失败'
                })
                
            except Exception as e:
                error_msg = str(e)
                results.append({
                    'network_id': network_id,
                    'network_name': network_id,  # 如果获取不到名称就用ID
                    'cluster_name': cluster.name,
                    'success': False,
                    'message': None,
                    'error': error_msg
                })
        
        return jsonify({
            'success': True,
            'message': f'批量{action}操作完成，成功: {success_count}/{len(network_ids)}',
            'data': {
                'total_count': len(network_ids),
                'success_count': success_count,
                'results': results
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Batch network action failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/networks/export', methods=['POST'])
@login_required
def export_networks():
    """导出网络数据到Excel"""
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
        network_ids = data.get('network_ids', [])
        filters = data.get('filters', {})
        
        # 获取OpenStack服务
        openstack_service = get_openstack_service()
        
        # 获取网络列表
        if export_all:
            # 导出所有网络（可能包含过滤条件）
            networks = openstack_service.list_networks(
                cluster_id,
                status=filters.get('status'),
                search=filters.get('search'), 
                network_type=filters.get('network_type')
            )
        else:
            # 导出选中的网络
            networks = []
            for network_id in network_ids:
                network = openstack_service.get_network_detail(cluster_id, network_id)
                if network:
                    networks.append(network)
        
        if not networks:
            return jsonify({'success': False, 'error': '没有找到要导出的网络'}), 400
        
        # 准备Excel数据
        excel_data = []
        for network in networks:
            # 处理子网信息
            subnets_info = ""
            if network.get('subnets'):
                subnets_info = "; ".join([
                    f"{subnet.get('name', 'N/A')}({subnet.get('cidr', 'N/A')})" 
                    for subnet in network['subnets']
                ])
            
            excel_data.append({
                '网络ID': network.get('id', ''),
                '网络名称': network.get('name', ''),
                '状态': network.get('status', ''),
                '管理状态': '启用' if network.get('admin_state_up') else '禁用',
                '共享': '是' if network.get('shared') else '否',
                '外部网络': '是' if network.get('external') else '否',
                '网络类型': network.get('provider_network_type', ''),
                '物理网络': network.get('provider_physical_network', ''),
                'VLAN ID': network.get('provider_segmentation_id', ''),
                'MTU': network.get('mtu', ''),
                '子网信息': subnets_info,
                '描述': network.get('description', ''),
                '创建时间': network.get('created_at', ''),
                '集群名称': cluster.name
            })
        
        # 创建DataFrame
        df = pd.DataFrame(excel_data)
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='网络列表', index=False)
            
            # 设置列宽
            worksheet = writer.sheets['网络列表']
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
        filename = f'networks_{cluster.name}_{timestamp}.xlsx'
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='network_export',
            operation_object=f'networks:export',
            result='success',
            details=f'导出网络数据: {len(excel_data)}个网络'
        )
        
        return send_file(
            BytesIO(output.getvalue()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Network export failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/networks/export-cross-cluster', methods=['POST'])
@login_required
def export_networks_cross_cluster():
    """跨集群导出网络数据到Excel"""
    try:
        import pandas as pd
        from io import BytesIO
        from datetime import datetime
        
        data = request.get_json()
        
        export_all = data.get('export_all', True)
        network_ids = data.get('network_ids', [])
        filters = data.get('filters', {})
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        if not clusters:
            return jsonify({'success': False, 'error': '没有可用的集群'}), 404
        
        all_networks = []
        
        # 获取OpenStack服务
        openstack_service = get_openstack_service()
        
        if export_all:
            # 导出所有集群的网络
            for cluster in clusters:
                try:
                    networks = openstack_service.list_networks(
                        cluster.id,
                        status=filters.get('status'),
                        search=filters.get('search'),
                        network_type=filters.get('network_type')
                    )
                    # 为每个网络添加集群信息
                    for network in networks:
                        network['cluster_name'] = cluster.name
                        network['cluster_id'] = cluster.id
                        all_networks.append(network)
                except Exception as e:
                    logger.warning(f"Failed to get networks from cluster {cluster.name}: {str(e)}")
                    continue
        else:
            # 导出选中的网络
            for network_id in network_ids:
                network_found = False
                for cluster in clusters:
                    try:
                        network = openstack_service.get_network_detail(cluster.id, network_id)
                        if network:
                            network['cluster_name'] = cluster.name
                            network['cluster_id'] = cluster.id
                            all_networks.append(network)
                            network_found = True
                            break
                    except Exception:
                        continue
                
                if not network_found:
                    logger.warning(f"Network {network_id} not found in any cluster")
        
        if not all_networks:
            return jsonify({'success': False, 'error': '没有找到要导出的网络'}), 400
        
        # 准备Excel数据
        excel_data = []
        for network in all_networks:
            # 处理子网信息
            subnets_info = ""
            if network.get('subnets'):
                subnets_info = "; ".join([
                    f"{subnet.get('name', 'N/A')}({subnet.get('cidr', 'N/A')})" 
                    for subnet in network['subnets']
                ])
            
            excel_data.append({
                '网络ID': network.get('id', ''),
                '网络名称': network.get('name', ''),
                '状态': network.get('status', ''),
                '管理状态': '启用' if network.get('admin_state_up') else '禁用',
                '共享': '是' if network.get('shared') else '否',
                '外部网络': '是' if network.get('external') else '否',
                '网络类型': network.get('provider_network_type', ''),
                '物理网络': network.get('provider_physical_network', ''),
                'VLAN ID': network.get('provider_segmentation_id', ''),
                'MTU': network.get('mtu', ''),
                '子网信息': subnets_info,
                '描述': network.get('description', ''),
                '创建时间': network.get('created_at', ''),
                '集群名称': network.get('cluster_name', '')
            })
        
        # 创建DataFrame
        df = pd.DataFrame(excel_data)
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='网络列表', index=False)
            
            # 设置列宽
            worksheet = writer.sheets['网络列表']
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
        filename = f'networks_all_clusters_{timestamp}.xlsx'
        
        # 记录操作日志（记录到第一个集群）
        if clusters:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=clusters[0].id,
                operation_type='network_export_cross',
                operation_object=f'networks:cross_cluster_export',
                result='success',
                details=f'跨集群导出网络数据: {len(excel_data)}个网络'
            )
        
        return send_file(
            BytesIO(output.getvalue()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Cross cluster network export failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500