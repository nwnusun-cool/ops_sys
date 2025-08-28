"""
安全组管理API路由
提供OpenStack安全组的管理操作
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

@api.route('/security-groups', methods=['GET'])
@login_required
def list_security_groups():
    """获取安全组列表"""
    try:
        # 获取查询参数
        cluster_id = request.args.get('cluster_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
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
        
        # 获取所有安全组数据
        all_security_groups = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                neutron_client = clients['neutron']
                
                # 获取集群安全组
                logger.info(f"Getting security groups for cluster {cluster.name}")
                security_groups = neutron_client.list_security_groups()['security_groups']
                
                # 处理每个安全组
                for sg in security_groups:
                    sg_data = {
                        'id': sg['id'],
                        'name': sg['name'],
                        'description': sg.get('description', ''),
                        'rules': sg.get('security_group_rules', []),
                        'created_at': sg.get('created_at'),
                        'updated_at': sg.get('updated_at'),
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'tenant_id': sg.get('tenant_id'),
                        'project_id': sg.get('project_id'),
                        'rules_count': len(sg.get('security_group_rules', []))
                    }
                    all_security_groups.append(sg_data)
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get security groups from cluster {cluster.name}: {e}")
                continue
        
        # 应用过滤器
        filtered_security_groups = all_security_groups
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_security_groups = [
                sg for sg in filtered_security_groups
                if search_lower in sg['name'].lower() or search_lower in sg['id']
            ]
        
        # 分页
        total = len(filtered_security_groups)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_security_groups = filtered_security_groups[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'data': paginated_security_groups,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_security_groups': len(all_security_groups),
                'filtered_security_groups': total,
                'cluster_name': cluster_names[0] if len(cluster_names) == 1 else f"共 {len(cluster_names)} 个集群"
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list security groups: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/security-groups/all-clusters', methods=['GET'])
@login_required
def list_all_cluster_security_groups():
    """获取所有集群的安全组列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        
        # 获取所有活跃集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        openstack_service = get_openstack_service()
        
        # 获取所有安全组数据
        all_security_groups = []
        cluster_names = []
        
        for cluster in clusters:
            try:
                # 获取OpenStack客户端
                clients = openstack_service.get_cluster_clients(cluster.id)
                neutron_client = clients['neutron']
                
                # 获取集群安全组
                logger.info(f"Getting security groups for cluster {cluster.name}")
                security_groups = neutron_client.list_security_groups()['security_groups']
                
                # 处理每个安全组
                for sg in security_groups:
                    sg_data = {
                        'id': sg['id'],
                        'name': sg['name'],
                        'description': sg.get('description', ''),
                        'rules': sg.get('security_group_rules', []),
                        'created_at': sg.get('created_at'),
                        'updated_at': sg.get('updated_at'),
                        'cluster_id': cluster.id,
                        'cluster_name': cluster.name,
                        'tenant_id': sg.get('tenant_id'),
                        'project_id': sg.get('project_id'),
                        'rules_count': len(sg.get('security_group_rules', []))
                    }
                    all_security_groups.append(sg_data)
                
                cluster_names.append(cluster.name)
                
            except Exception as e:
                logger.warning(f"Failed to get security groups from cluster {cluster.name}: {e}")
                continue
        
        # 应用过滤器
        filtered_security_groups = all_security_groups
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_security_groups = [
                sg for sg in filtered_security_groups
                if search_lower in sg['name'].lower() or search_lower in sg['id']
            ]
        
        # 分页
        total = len(filtered_security_groups)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_security_groups = filtered_security_groups[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'data': paginated_security_groups,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page,
                'has_next': end_idx < total,
                'has_prev': page > 1
            },
            'statistics': {
                'total_security_groups': len(all_security_groups),
                'filtered_security_groups': total,
                'cluster_name': f'所有集群 ({", ".join(cluster_names)})'
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list all cluster security groups: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/security-groups/<sg_id>', methods=['GET'])
@login_required
def get_security_group_detail(sg_id):
    """获取安全组详细信息"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        if not cluster_id:
            return jsonify({'success': False, 'error': '必须指定集群ID'}), 400
        
        cluster = OpenstackCluster.query.get_or_404(cluster_id)
        openstack_service = get_openstack_service()
        clients = openstack_service.get_cluster_clients(cluster_id)
        neutron_client = clients['neutron']
        
        # 获取安全组详情
        security_group = neutron_client.show_security_group(sg_id)['security_group']
        
        # 格式化规则信息
        formatted_rules = []
        for rule in security_group.get('security_group_rules', []):
            formatted_rule = {
                'id': rule['id'],
                'direction': rule['direction'],
                'ethertype': rule.get('ethertype', 'IPv4'),
                'protocol': rule.get('protocol', 'any'),
                'port_range_min': rule.get('port_range_min'),
                'port_range_max': rule.get('port_range_max'),
                'remote_ip_prefix': rule.get('remote_ip_prefix'),
                'remote_group_id': rule.get('remote_group_id'),
                'description': rule.get('description', ''),
                'created_at': rule.get('created_at'),
                'updated_at': rule.get('updated_at')
            }
            
            # 格式化端口范围
            if rule.get('port_range_min') and rule.get('port_range_max'):
                if rule['port_range_min'] == rule['port_range_max']:
                    formatted_rule['port_range'] = str(rule['port_range_min'])
                else:
                    formatted_rule['port_range'] = f"{rule['port_range_min']}-{rule['port_range_max']}"
            else:
                formatted_rule['port_range'] = 'any'
            
            # 格式化源/目标
            if rule.get('remote_group_id'):
                formatted_rule['remote'] = f"安全组: {rule['remote_group_id']}"
            elif rule.get('remote_ip_prefix'):
                formatted_rule['remote'] = rule['remote_ip_prefix']
            else:
                formatted_rule['remote'] = '0.0.0.0/0' if rule.get('ethertype') == 'IPv4' else '::/0'
            
            formatted_rules.append(formatted_rule)
        
        sg_detail = {
            'id': security_group['id'],
            'name': security_group['name'],
            'description': security_group.get('description', ''),
            'rules': formatted_rules,
            'created_at': security_group.get('created_at'),
            'updated_at': security_group.get('updated_at'),
            'tenant_id': security_group.get('tenant_id'),
            'project_id': security_group.get('project_id'),
            'cluster_name': cluster.name
        }
        
        return jsonify({
            'success': True,
            'data': sg_detail
        })
        
    except Exception as e:
        logger.error(f"Failed to get security group detail {sg_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/security-groups/<sg_id>/action', methods=['POST'])
@login_required
def security_group_action(sg_id):
    """执行安全组操作"""
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
        
        # 获取安全组信息用于日志记录
        security_group = neutron_client.show_security_group(sg_id)['security_group']
        sg_name = security_group['name']
        
        result_message = ""
        
        # 执行不同的操作
        if action == 'update_name':
            new_name = data.get('name', '').strip()
            if not new_name:
                return jsonify({'success': False, 'error': '安全组名称不能为空'}), 400
            neutron_client.update_security_group(sg_id, {'security_group': {'name': new_name}})
            result_message = f"安全组已重命名为: {new_name}"
            
        elif action == 'update_description':
            description = data.get('description', '')
            neutron_client.update_security_group(sg_id, {'security_group': {'description': description}})
            result_message = f"安全组 {sg_name} 描述已更新"
            
        elif action == 'add_rule':
            rule_data = data.get('rule')
            if not rule_data:
                return jsonify({'success': False, 'error': '缺少规则数据'}), 400
            
            # 构建规则参数
            rule_params = {
                'security_group_id': sg_id,
                'direction': rule_data.get('direction', 'ingress'),
                'ethertype': rule_data.get('ethertype', 'IPv4')
            }
            
            # 协议
            if rule_data.get('protocol') and rule_data['protocol'] != 'any':
                rule_params['protocol'] = rule_data['protocol']
            
            # 端口范围
            if rule_data.get('port_range_min'):
                rule_params['port_range_min'] = int(rule_data['port_range_min'])
            if rule_data.get('port_range_max'):
                rule_params['port_range_max'] = int(rule_data['port_range_max'])
            
            # 源/目标
            if rule_data.get('remote_group_id'):
                rule_params['remote_group_id'] = rule_data['remote_group_id']
            elif rule_data.get('remote_ip_prefix'):
                rule_params['remote_ip_prefix'] = rule_data['remote_ip_prefix']
            
            # 描述
            if rule_data.get('description'):
                rule_params['description'] = rule_data['description']
            
            neutron_client.create_security_group_rule({'security_group_rule': rule_params})
            result_message = f"安全组 {sg_name} 规则已添加"
            
        elif action == 'delete_rule':
            rule_id = data.get('rule_id')
            if not rule_id:
                return jsonify({'success': False, 'error': '缺少规则ID'}), 400
            
            neutron_client.delete_security_group_rule(rule_id)
            result_message = f"安全组 {sg_name} 规则已删除"
            
        elif action == 'delete':
            # 删除操作需要管理员权限
            if not current_user.has_role(['super_admin', 'admin']):
                return jsonify({'success': False, 'error': '删除安全组需要管理员权限'}), 403
            
            # 检查是否为默认安全组
            if sg_name == 'default':
                return jsonify({'success': False, 'error': '不能删除默认安全组'}), 400
            
            neutron_client.delete_security_group(sg_id)
            result_message = f"安全组 {sg_name} 删除命令已发送"
            
        else:
            return jsonify({'success': False, 'error': f'不支持的操作: {action}'}), 400
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type=f'security_group_{action}',
            operation_object=f'security_group:{sg_name}',
            result='success',
            details=result_message
        )
        
        return jsonify({
            'success': True,
            'message': result_message,
            'action': action,
            'security_group_id': sg_id,
            'security_group_name': sg_name
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to perform action {action} on security group {sg_id}: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type=f'security_group_{action}',
                operation_object=f'security_group:{sg_id}',
                result='failed',
                details=f'操作失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/security-groups/create', methods=['POST'])
@login_required
def create_security_group():
    """创建安全组"""
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
        sg_params = {
            'name': data['name'],
            'description': data.get('description', '')
        }
        
        # 创建安全组
        logger.info(f"Creating security group: {data['name']} on cluster {cluster.name}")
        security_group = neutron_client.create_security_group({'security_group': sg_params})['security_group']
        
        # 如果提供了初始规则，添加规则
        if data.get('rules'):
            for rule_data in data['rules']:
                try:
                    rule_params = {
                        'security_group_id': security_group['id'],
                        'direction': rule_data.get('direction', 'ingress'),
                        'ethertype': rule_data.get('ethertype', 'IPv4')
                    }
                    
                    # 协议
                    if rule_data.get('protocol') and rule_data['protocol'] != 'any':
                        rule_params['protocol'] = rule_data['protocol']
                    
                    # 端口范围
                    if rule_data.get('port_range_min'):
                        rule_params['port_range_min'] = int(rule_data['port_range_min'])
                    if rule_data.get('port_range_max'):
                        rule_params['port_range_max'] = int(rule_data['port_range_max'])
                    
                    # 源/目标
                    if rule_data.get('remote_group_id'):
                        rule_params['remote_group_id'] = rule_data['remote_group_id']
                    elif rule_data.get('remote_ip_prefix'):
                        rule_params['remote_ip_prefix'] = rule_data['remote_ip_prefix']
                    
                    # 描述
                    if rule_data.get('description'):
                        rule_params['description'] = rule_data['description']
                    
                    neutron_client.create_security_group_rule({'security_group_rule': rule_params})
                    
                except Exception as rule_error:
                    logger.warning(f"Failed to create rule for security group {security_group['id']}: {rule_error}")
                    continue
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            cluster_id=cluster_id,
            operation_type='security_group_create',
            operation_object=f'security_group:{data["name"]}',
            result='success',
            details=f'创建安全组: {data["name"]}'
        )
        
        return jsonify({
            'success': True,
            'message': f'安全组 {data["name"]} 创建成功',
            'data': {
                'security_group_id': security_group['id'],
                'name': security_group['name'],
                'description': security_group['description']
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Failed to create security group: {error_msg}")
        
        # 记录失败日志
        try:
            OperationLog.log_operation(
                user_id=current_user.id,
                cluster_id=cluster_id,
                operation_type='security_group_create',
                operation_object=f'security_group:{data.get("name", "unknown")}',
                result='failed',
                details=f'创建安全组失败: {error_msg}'
            )
        except:
            pass
        
        return jsonify({'success': False, 'error': error_msg}), 500

@api.route('/security-groups/batch-action', methods=['POST'])
@login_required
def batch_security_group_action():
    """批量安全组操作"""
    try:
        cluster_id = request.args.get('cluster_id', type=int)
        data = request.get_json()
        
        if not cluster_id:
            return jsonify({'success': False, 'error': '缺少集群ID参数'}), 400
        
        if not data or not data.get('security_group_ids') or not data.get('action'):
            return jsonify({'success': False, 'error': '缺少必要参数'}), 400
        
        sg_ids = data['security_group_ids']
        action = data['action']
        
        # 验证操作类型
        if action not in ['delete']:
            return jsonify({'success': False, 'error': '不支持的操作类型'}), 400
        
        cluster = OpenstackCluster.query.get(cluster_id)
        if not cluster:
            return jsonify({'success': False, 'error': '集群不存在'}), 404
        
        openstack_service = get_openstack_service()
        clients = openstack_service.get_cluster_clients(cluster_id)
        neutron_client = clients['neutron']
        
        results = []
        success_count = 0
        
        for sg_id in sg_ids:
            try:
                # 获取安全组信息
                try:
                    security_group = neutron_client.show_security_group(sg_id)['security_group']
                    sg_name = security_group['name']
                except:
                    sg_name = sg_id
                
                success = True
                message = ""
                
                try:
                    if action == 'delete':
                        # 检查是否为默认安全组
                        if sg_name == 'default':
                            success = False
                            message = '不能删除默认安全组'
                        else:
                            neutron_client.delete_security_group(sg_id)
                            message = '删除成功'
                            success_count += 1
                            
                            # 记录成功日志
                            OperationLog.log_operation(
                                user_id=current_user.id,
                                cluster_id=cluster_id,
                                operation_type='security_group_batch_delete',
                                operation_object=f'security_group:{sg_id}',
                                result='success',
                                details=f'批量删除安全组: {sg_name}'
                            )
                    
                except Exception as op_error:
                    success = False
                    message = f'操作失败: {str(op_error)}'
                
                results.append({
                    'security_group_id': sg_id,
                    'security_group_name': sg_name,
                    'cluster_name': cluster.name,
                    'success': success,
                    'message': message if success else '操作失败',
                    'error': None if success else message
                })
                
            except Exception as e:
                error_msg = str(e)
                results.append({
                    'security_group_id': sg_id,
                    'security_group_name': sg_id,
                    'cluster_name': cluster.name,
                    'success': False,
                    'message': None,
                    'error': error_msg
                })
        
        return jsonify({
            'success': True,
            'message': f'批量{action}操作完成，成功: {success_count}/{len(sg_ids)}',
            'data': {
                'total_count': len(sg_ids),
                'success_count': success_count,
                'results': results
            }
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Batch security group action failed: {error_msg}")
        return jsonify({'success': False, 'error': error_msg}), 500