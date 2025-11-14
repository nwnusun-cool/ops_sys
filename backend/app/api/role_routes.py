"""
角色管理API路由
提供角色和权限的CRUD操作
"""
import logging
from datetime import datetime
from flask import request, jsonify
from flask_login import login_required, current_user
from . import api_bp as api
from app.models.base import db
from app.models.role import Role, Permission, UserRole
from app.models.user import User
from app.models.log import OperationLog
from app.utils.role_permissions import get_permission_tree, init_rbac_system

logger = logging.getLogger(__name__)

def check_role_permission(required_permissions):
    """检查角色权限装饰器"""
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 如果用户是super_admin，直接允许
            if current_user.role == 'super_admin':
                return f(*args, **kwargs)
            
            # 检查用户是否有所需权限
            user_roles = UserRole.query.filter_by(user_id=current_user.id).all()
            user_permissions = set()
            
            for user_role in user_roles:
                if not user_role.is_expired():
                    user_permissions.update(user_role.role.get_permission_codes())
            
            # 检查权限
            if isinstance(required_permissions, str):
                required_permissions_list = [required_permissions]
            else:
                required_permissions_list = required_permissions
            
            if not any(perm in user_permissions for perm in required_permissions_list):
                return jsonify({'success': False, 'error': '权限不足'}), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# 权限管理API
@api.route('/permissions', methods=['GET'])
@login_required
@check_role_permission(['role.view'])
def list_permissions():
    """获取权限列表"""
    try:
        # 获取查询参数
        category = request.args.get('category')
        search = request.args.get('search', '').strip()
        is_active = request.args.get('is_active')
        tree_format = request.args.get('tree', 'false').lower() == 'true'
        
        # 构建查询
        query = Permission.query
        
        if category:
            query = query.filter_by(category=category)
        
        if is_active is not None:
            active_filter = is_active.lower() in ['true', '1', 'yes']
            query = query.filter_by(is_active=active_filter)
        
        if search:
            query = query.filter(
                db.or_(
                    Permission.name.ilike(f'%{search}%'),
                    Permission.code.ilike(f'%{search}%'),
                    Permission.description.ilike(f'%{search}%')
                )
            )
        
        permissions = query.order_by(Permission.category, Permission.code).all()
        
        if tree_format:
            # 返回树形结构
            return jsonify({
                'success': True,
                'data': get_permission_tree()
            })
        else:
            # 返回平铺列表
            return jsonify({
                'success': True,
                'data': [perm.to_dict() for perm in permissions],
                'total': len(permissions)
            })
        
    except Exception as e:
        logger.error(f"Failed to list permissions: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 角色管理API
@api.route('/roles', methods=['GET'])
@login_required
@check_role_permission(['role.view'])
def list_roles():
    """获取角色列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '').strip()
        is_active = request.args.get('is_active')
        include_permissions = request.args.get('include_permissions', 'false').lower() == 'true'
        
        # 构建查询
        query = Role.query
        
        if is_active is not None:
            active_filter = is_active.lower() in ['true', '1', 'yes']
            query = query.filter_by(is_active=active_filter)
        
        if search:
            query = query.filter(
                db.or_(
                    Role.name.ilike(f'%{search}%'),
                    Role.code.ilike(f'%{search}%'),
                    Role.description.ilike(f'%{search}%')
                )
            )
        
        # 分页
        pagination = query.order_by(Role.level.desc(), Role.created_at).paginate(
            page=page,
            per_page=per_page,
            error_out=False
        )
        
        roles = pagination.items
        
        return jsonify({
            'success': True,
            'data': [role.to_dict(include_permissions=include_permissions) for role in roles],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to list roles: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/roles/<int:role_id>', methods=['GET'])
@login_required
@check_role_permission(['role.view'])
def get_role_detail(role_id):
    """获取角色详细信息"""
    try:
        role = Role.query.get_or_404(role_id)
        
        role_data = role.to_dict(include_permissions=True)
        
        # 获取使用此角色的用户
        user_assignments = UserRole.query.filter_by(role_id=role_id).all()
        role_data['users'] = [
            {
                'id': assignment.user.id,
                'username': assignment.user.username,
                'email': assignment.user.email,
                'is_primary': assignment.is_primary,
                'assigned_at': assignment.assigned_at.isoformat() if assignment.assigned_at else None,
                'expires_at': assignment.expires_at.isoformat() if assignment.expires_at else None,
                'is_expired': assignment.is_expired()
            }
            for assignment in user_assignments
        ]
        
        return jsonify({
            'success': True,
            'data': role_data
        })
        
    except Exception as e:
        logger.error(f"Failed to get role detail {role_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/roles', methods=['POST'])
@login_required
@check_role_permission(['role.create'])
def create_role():
    """创建角色"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        # 验证必填字段
        required_fields = ['name', 'code', 'description']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'缺少必填字段: {field}'}), 400
        
        # 检查角色代码是否存在
        if Role.query.filter_by(code=data['code']).first():
            return jsonify({'success': False, 'error': '角色代码已存在'}), 400
        
        # 检查角色名称是否存在
        if Role.query.filter_by(name=data['name']).first():
            return jsonify({'success': False, 'error': '角色名称已存在'}), 400
        
        # 创建角色
        role = Role(
            name=data['name'],
            code=data['code'],
            description=data['description'],
            level=data.get('level', 50),
            is_system=False,  # 用户创建的角色都不是系统角色
            is_active=data.get('is_active', True)
        )
        
        db.session.add(role)
        db.session.flush()  # 获取角色ID
        
        # 分配权限
        permission_codes = data.get('permission_codes', [])
        if permission_codes:
            permissions = Permission.query.filter(
                Permission.code.in_(permission_codes),
                Permission.is_active == True
            ).all()
            role.permissions = permissions
        
        db.session.commit()
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            operation_type='role_create',
            operation_object=f'role:{role.code}',
            result='success',
            details=f'创建角色: {role.name}, 权限数: {len(role.permissions)}'
        )
        
        logger.info(f"Role {role.name} created by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'角色 {role.name} 创建成功',
            'data': role.to_dict(include_permissions=True)
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create role: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/roles/<int:role_id>', methods=['PUT'])
@login_required
@check_role_permission(['role.update'])
def update_role(role_id):
    """更新角色信息"""
    try:
        role = Role.query.get_or_404(role_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': '缺少请求数据'}), 400
        
        # 系统角色的某些字段不能修改
        if role.is_system:
            protected_fields = ['code', 'level', 'is_system']
            for field in protected_fields:
                if field in data:
                    return jsonify({'success': False, 'error': f'系统角色不能修改字段: {field}'}), 400
        
        changes = []
        
        # 更新角色名称
        if 'name' in data and data['name'] != role.name:
            if Role.query.filter_by(name=data['name']).filter(Role.id != role_id).first():
                return jsonify({'success': False, 'error': '角色名称已存在'}), 400
            changes.append(f"名称: {role.name} -> {data['name']}")
            role.name = data['name']
        
        # 更新角色代码
        if 'code' in data and data['code'] != role.code and not role.is_system:
            if Role.query.filter_by(code=data['code']).filter(Role.id != role_id).first():
                return jsonify({'success': False, 'error': '角色代码已存在'}), 400
            changes.append(f"代码: {role.code} -> {data['code']}")
            role.code = data['code']
        
        # 更新描述
        if 'description' in data and data['description'] != role.description:
            changes.append(f"描述已更新")
            role.description = data['description']
        
        # 更新等级
        if 'level' in data and data['level'] != role.level and not role.is_system:
            changes.append(f"等级: {role.level} -> {data['level']}")
            role.level = data['level']
        
        # 更新状态
        if 'is_active' in data and data['is_active'] != role.is_active:
            changes.append(f"状态: {'启用' if role.is_active else '禁用'} -> {'启用' if data['is_active'] else '禁用'}")
            role.is_active = data['is_active']
        
        # 更新权限
        if 'permission_codes' in data:
            new_permission_codes = set(data['permission_codes'])
            current_permission_codes = set(role.get_permission_codes())
            
            if new_permission_codes != current_permission_codes:
                permissions = Permission.query.filter(
                    Permission.code.in_(data['permission_codes']),
                    Permission.is_active == True
                ).all()
                role.permissions = permissions
                changes.append(f"权限已更新: {len(permissions)}个权限")
        
        if changes:
            role.updated_at = datetime.utcnow()
            db.session.commit()
            
            # 记录操作日志
            OperationLog.log_operation(
                user_id=current_user.id,
                operation_type='role_update',
                operation_object=f'role:{role.code}',
                result='success',
                details=f'更新角色信息: {", ".join(changes)}'
            )
            
            logger.info(f"Role {role.name} updated by {current_user.username}: {changes}")
        
        return jsonify({
            'success': True,
            'message': f'角色 {role.name} 更新成功',
            'data': role.to_dict(include_permissions=True),
            'changes': changes
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update role {role_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/roles/<int:role_id>', methods=['DELETE'])
@login_required
@check_role_permission(['role.delete'])
def delete_role(role_id):
    """删除角色"""
    try:
        role = Role.query.get_or_404(role_id)
        
        # 系统角色不能删除
        if role.is_system:
            return jsonify({'success': False, 'error': '不能删除系统角色'}), 400
        
        # 检查是否有用户使用此角色
        user_count = UserRole.query.filter_by(role_id=role_id).count()
        if user_count > 0:
            return jsonify({'success': False, 'error': f'还有 {user_count} 个用户使用此角色，无法删除'}), 400
        
        role_name = role.name
        
        # 记录操作日志（在删除前记录）
        OperationLog.log_operation(
            user_id=current_user.id,
            operation_type='role_delete',
            operation_object=f'role:{role.code}',
            result='success',
            details=f'删除角色: {role_name}'
        )
        
        db.session.delete(role)
        db.session.commit()
        
        logger.info(f"Role {role_name} deleted by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'角色 {role_name} 删除成功'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete role {role_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 用户角色分配API
@api.route('/users/<int:user_id>/roles', methods=['GET'])
@login_required
@check_role_permission(['user.assign_role'])
def get_user_roles(user_id):
    """获取用户的角色列表"""
    try:
        user = User.query.get_or_404(user_id)
        
        user_roles = UserRole.query.filter_by(user_id=user_id).all()
        
        return jsonify({
            'success': True,
            'data': {
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                },
                'roles': [ur.to_dict() for ur in user_roles]
            }
        })
        
    except Exception as e:
        logger.error(f"Failed to get user roles {user_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/<int:user_id>/roles', methods=['POST'])
@login_required
@check_role_permission(['user.assign_role'])
def assign_role_to_user(user_id):
    """为用户分配角色"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.get_json()
        
        if not data or not data.get('role_id'):
            return jsonify({'success': False, 'error': '缺少角色ID'}), 400
        
        role_id = data['role_id']
        role = Role.query.get_or_404(role_id)
        
        # 检查是否已分配此角色
        existing_assignment = UserRole.query.filter_by(
            user_id=user_id,
            role_id=role_id
        ).first()
        
        if existing_assignment:
            return jsonify({'success': False, 'error': '用户已拥有此角色'}), 400
        
        # 创建角色分配
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            is_primary=data.get('is_primary', False),
            assigned_by=current_user.id,
            expires_at=datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None
        )
        
        # 如果设置为主要角色，取消其他主要角色
        if user_role.is_primary:
            UserRole.query.filter_by(user_id=user_id, is_primary=True).update({'is_primary': False})
        
        db.session.add(user_role)
        db.session.commit()
        
        # 记录操作日志
        OperationLog.log_operation(
            user_id=current_user.id,
            operation_type='role_assign',
            operation_object=f'user:{user.username}',
            result='success',
            details=f'为用户 {user.username} 分配角色 {role.name}'
        )
        
        logger.info(f"Role {role.name} assigned to user {user.username} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'成功为用户 {user.username} 分配角色 {role.name}',
            'data': user_role.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to assign role to user {user_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/users/<int:user_id>/roles/<int:role_id>', methods=['DELETE'])
@login_required
@check_role_permission(['user.assign_role'])
def remove_role_from_user(user_id, role_id):
    """移除用户的角色"""
    try:
        user = User.query.get_or_404(user_id)
        role = Role.query.get_or_404(role_id)
        
        user_role = UserRole.query.filter_by(
            user_id=user_id,
            role_id=role_id
        ).first()
        
        if not user_role:
            return jsonify({'success': False, 'error': '用户未拥有此角色'}), 400
        
        # 记录操作日志（在删除前记录）
        OperationLog.log_operation(
            user_id=current_user.id,
            operation_type='role_remove',
            operation_object=f'user:{user.username}',
            result='success',
            details=f'移除用户 {user.username} 的角色 {role.name}'
        )
        
        db.session.delete(user_role)
        db.session.commit()
        
        logger.info(f"Role {role.name} removed from user {user.username} by {current_user.username}")
        
        return jsonify({
            'success': True,
            'message': f'成功移除用户 {user.username} 的角色 {role.name}'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to remove role from user {user_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 系统初始化API
@api.route('/rbac/init', methods=['POST'])
@login_required
@check_role_permission(['system.settings'])
def init_rbac():
    """初始化RBAC系统"""
    try:
        success = init_rbac_system()
        
        if success:
            # 记录操作日志
            OperationLog.log_operation(
                user_id=current_user.id,
                operation_type='system_init_rbac',
                operation_object='system:rbac',
                result='success',
                details='初始化RBAC系统成功'
            )
            
            return jsonify({
                'success': True,
                'message': 'RBAC系统初始化成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'RBAC系统初始化失败'
            }), 500
            
    except Exception as e:
        logger.error(f"Failed to init RBAC: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500