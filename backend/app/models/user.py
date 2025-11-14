"""
用户模型
"""
from datetime import datetime
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .base import db

class User(UserMixin, db.Model):
    """用户模型"""
    
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='viewer', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)
    
    # 关联关系
    operation_logs = db.relationship('OperationLog', backref='user', lazy='dynamic')
    # 角色关系通过UserRole表
    role_assignments = db.relationship('UserRole', foreign_keys='UserRole.user_id', lazy='dynamic')
    
    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
    
    def set_password(self, password):
        """设置密码"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)
    
    def has_role(self, roles):
        """检查用户是否具有指定角色或更高权限"""
        role_hierarchy = {
            'viewer': 0,
            'operator': 1,
            'admin': 2,
            'super_admin': 3
        }
        user_level = role_hierarchy.get(self.role, 0)
        
        # 如果传入的是列表，检查是否包含任一角色
        if isinstance(roles, list):
            for role in roles:
                required_level = role_hierarchy.get(role, 0)
                if user_level >= required_level:
                    return True
            return False
        else:
            # 单个角色检查
            required_level = role_hierarchy.get(roles, 0)
            return user_level >= required_level
    
    def can_manage_users(self):
        """是否可以管理用户"""
        return self.role == 'super_admin'
    
    def can_manage_clusters(self):
        """是否可以管理集群"""
        return self.role in ['super_admin', 'admin']
    
    def can_operate_resources(self):
        """是否可以操作资源（实例、卷等）"""
        return self.role in ['super_admin', 'admin', 'operator']
    
    def can_view_resources(self):
        """是否可以查看资源"""
        return True  # 所有登录用户都可以查看
    
    def can_create_resources(self):
        """是否可以创建资源（实例、卷等）"""
        return self.role in ['super_admin', 'admin', 'operator']
    
    def can_delete_resources(self):
        """是否可以删除资源"""
        return self.role in ['super_admin', 'admin']
    
    def can_modify_resources(self):
        """是否可以修改资源（重启、调整大小等）"""
        return self.role in ['super_admin', 'admin', 'operator']
    
    def can_access_console(self):
        """是否可以访问控制台"""
        return self.role in ['super_admin', 'admin', 'operator']
    
    def can_manage_snapshots(self):
        """是否可以管理快照"""
        return self.role in ['super_admin', 'admin', 'operator']
    
    def can_manage_networks(self):
        """是否可以管理网络"""
        return self.role in ['super_admin', 'admin']
    
    def can_view_logs(self):
        """是否可以查看日志"""
        return self.role in ['super_admin', 'admin']
    
    def can_export_data(self):
        """是否可以导出数据"""
        return self.role in ['super_admin', 'admin', 'operator']
    
    def can_batch_operations(self):
        """是否可以执行批量操作"""
        return self.role in ['super_admin', 'admin']
    
    def can_view_all_users_resources(self):
        """是否可以查看所有用户的资源"""
        return self.role in ['super_admin', 'admin']
    
    def get_user_roles(self):
        """获取用户的所有角色对象"""
        user_role_assignments = self.role_assignments.all()
        return [ur.role for ur in user_role_assignments if not ur.is_expired()]
    
    def get_primary_role(self):
        """获取用户的主要角色"""
        primary_assignment = self.role_assignments.filter_by(is_primary=True).first()
        
        if primary_assignment and not primary_assignment.is_expired():
            return primary_assignment.role
        
        # 如果没有主要角色，返回等级最高的角色
        user_roles = self.get_user_roles()
        if user_roles:
            return max(user_roles, key=lambda r: r.level)
        
        return None
    
    def has_permission(self, permission_code):
        """检查用户是否具有指定权限"""
        # 如果是旧系统的超级管理员，直接允许
        if self.role == 'super_admin':
            return True
        
        # 检查新系统的权限
        user_roles = self.get_user_roles()
        for role in user_roles:
            if role.has_permission(permission_code):
                return True
        return False
    
    def has_any_permission(self, permission_codes):
        """检查用户是否具有任一权限"""
        if not isinstance(permission_codes, list):
            permission_codes = [permission_codes]
        
        return any(self.has_permission(code) for code in permission_codes)
    
    def get_all_permissions(self):
        """获取用户的所有权限代码"""
        # 如果是旧系统的超级管理员，返回所有权限
        if self.role == 'super_admin':
            from .role import Permission
            return [p.code for p in Permission.query.filter_by(is_active=True).all()]
        
        # 收集所有角色的权限
        permissions = set()
        user_roles = self.get_user_roles()
        for role in user_roles:
            permissions.update(role.get_permission_codes())
        
        return list(permissions)
    
    def get_permissions(self):
        """获取用户的所有权限（兼容旧接口）"""
        # 基于新权限系统的权限检查
        permissions = {
            'can_manage_users': self.has_permission('user.view') or self.role == 'super_admin',
            'can_manage_clusters': self.has_any_permission(['cluster.view', 'cluster.create']) or self.role in ['super_admin', 'admin'],
            'can_operate_resources': self.has_any_permission(['instance.create', 'volume.create']) or self.role in ['super_admin', 'admin', 'operator'],
            'can_view_resources': True,  # 所有用户都可以查看
            'can_create_resources': self.has_any_permission(['instance.create', 'volume.create']) or self.role in ['super_admin', 'admin', 'operator'],
            'can_delete_resources': self.has_any_permission(['instance.delete', 'volume.delete']) or self.role in ['super_admin', 'admin'],
            'can_modify_resources': self.has_any_permission(['instance.start', 'instance.stop']) or self.role in ['super_admin', 'admin', 'operator'],
            'can_access_console': self.has_permission('instance.console') or self.role in ['super_admin', 'admin', 'operator'],
            'can_manage_snapshots': self.has_permission('snapshot.create') or self.role in ['super_admin', 'admin', 'operator'],
            'can_manage_networks': self.has_permission('network.create') or self.role in ['super_admin', 'admin'],
            'can_view_logs': self.has_permission('system.view_logs') or self.role in ['super_admin', 'admin'],
            'can_export_data': self.has_permission('system.export_data') or self.role in ['super_admin', 'admin', 'operator'],
            'can_batch_operations': self.has_permission('instance.batch_operation') or self.role in ['super_admin', 'admin'],
            'can_view_all_users_resources': self.has_permission('user.view') or self.role in ['super_admin', 'admin']
        }
        
        # 添加新权限系统的详细权限
        all_permission_codes = self.get_all_permissions()
        for perm_code in all_permission_codes:
            permissions[f'has_{perm_code.replace(".", "_")}'] = True
        
        return permissions
    
    def get_role_description(self):
        """获取角色描述"""
        role_descriptions = {
            'super_admin': '超级管理员 - 拥有系统所有权限，包括用户管理',
            'admin': '管理员 - 可以管理集群、删除资源、执行批量操作',
            'operator': '操作员 - 可以创建、修改资源，访问控制台，管理快照',
            'viewer': '查看者 - 只能查看资源信息，无操作权限'
        }
        return role_descriptions.get(self.role, '未知角色')
    
    def update_last_login(self):
        """更新最后登录时间"""
        self.last_login = datetime.utcnow()
        self.login_count += 1
        db.session.commit()
    
    def to_dict(self, include_sensitive=False, include_roles=False):
        """转换为字典"""
        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,  # 保持兼容性
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'login_count': self.login_count
        }
        
        # 添加新角色系统信息
        primary_role = self.get_primary_role()
        if primary_role:
            data['primary_role'] = {
                'id': primary_role.id,
                'code': primary_role.code,
                'name': primary_role.name,
                'level': primary_role.level
            }
        else:
            data['primary_role'] = None
        
        if include_roles:
            user_roles = self.role_assignments.all()
            data['roles'] = [ur.to_dict() for ur in user_roles]
            data['permissions'] = self.get_all_permissions()
        
        if include_sensitive:
            data['password_hash'] = self.password_hash
        
        return data
    
    def __repr__(self):
        return f'<User {self.username}>'