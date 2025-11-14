"""
角色和权限模型
提供灵活的基于角色的访问控制(RBAC)系统
"""
from datetime import datetime
from .base import db

# 角色权限关联表
role_permissions = db.Table('role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True)
)

class Permission(db.Model):
    """权限模型"""
    
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    code = db.Column(db.String(100), unique=True, nullable=False, index=True)  # 权限代码，如 'user.create'
    description = db.Column(db.String(255))
    category = db.Column(db.String(50), nullable=False, index=True)  # 权限分类，如 'user', 'cluster', 'instance'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'category': self.category,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f'<Permission {self.code}>'

class Role(db.Model):
    """角色模型"""
    
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # 角色代码，如 'admin'
    description = db.Column(db.String(255))
    level = db.Column(db.Integer, default=0, nullable=False)  # 角色等级，数字越大权限越高
    is_system = db.Column(db.Boolean, default=False, nullable=False)  # 是否为系统角色，系统角色不能删除
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    permissions = db.relationship('Permission', secondary=role_permissions, lazy='subquery',
                                backref=db.backref('roles', lazy=True))
    # 通过UserRole表关联用户
    user_assignments = db.relationship('UserRole', back_populates='role', lazy='dynamic')
    
    def has_permission(self, permission_code):
        """检查角色是否具有指定权限"""
        return any(p.code == permission_code and p.is_active for p in self.permissions)
    
    def has_any_permission(self, permission_codes):
        """检查角色是否具有任一权限"""
        if not isinstance(permission_codes, list):
            permission_codes = [permission_codes]
        
        active_permission_codes = {p.code for p in self.permissions if p.is_active}
        return bool(active_permission_codes.intersection(permission_codes))
    
    def has_all_permissions(self, permission_codes):
        """检查角色是否具有所有权限"""
        if not isinstance(permission_codes, list):
            permission_codes = [permission_codes]
        
        active_permission_codes = {p.code for p in self.permissions if p.is_active}
        return set(permission_codes).issubset(active_permission_codes)
    
    def add_permission(self, permission):
        """添加权限到角色"""
        if permission not in self.permissions:
            self.permissions.append(permission)
    
    def remove_permission(self, permission):
        """从角色移除权限"""
        if permission in self.permissions:
            self.permissions.remove(permission)
    
    def get_permission_codes(self):
        """获取角色的所有权限代码列表"""
        return [p.code for p in self.permissions if p.is_active]
    
    def get_permissions_by_category(self, category):
        """获取指定分类的权限"""
        return [p for p in self.permissions if p.category == category and p.is_active]
    
    def to_dict(self, include_permissions=False):
        """转换为字典"""
        data = {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'level': self.level,
            'is_system': self.is_system,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'user_count': self.user_assignments.count()
        }
        
        if include_permissions:
            data['permissions'] = [p.to_dict() for p in self.permissions]
            data['permission_codes'] = self.get_permission_codes()
        
        return data
    
    def __repr__(self):
        return f'<Role {self.code}>'

class UserRole(db.Model):
    """用户角色关联模型 - 支持用户多角色"""
    
    __tablename__ = 'user_roles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)  # 是否为主要角色
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # 分配者
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime)  # 角色过期时间，可选
    
    # 关联关系
    user = db.relationship('User', foreign_keys=[user_id], overlaps='role_assignments')
    role = db.relationship('Role', back_populates='user_assignments')
    assigned_by_user = db.relationship('User', foreign_keys=[assigned_by])
    
    # 唯一约束
    __table_args__ = (db.UniqueConstraint('user_id', 'role_id', name='uk_user_role'),)
    
    def is_expired(self):
        """检查角色是否过期"""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'role_id': self.role_id,
            'role_name': self.role.name,
            'role_code': self.role.code,
            'is_primary': self.is_primary,
            'assigned_by': self.assigned_by,
            'assigned_by_username': self.assigned_by_user.username if self.assigned_by_user else None,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_expired': self.is_expired()
        }
    
    def __repr__(self):
        return f'<UserRole user_id={self.user_id} role_id={self.role_id}>'