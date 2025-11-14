"""
角色权限初始化和管理工具
定义系统的所有权限和默认角色
"""
from app.models.role import Role, Permission, UserRole
from app.models.base import db

# 系统权限定义
SYSTEM_PERMISSIONS = {
    # 用户管理权限
    'user_management': [
        {'code': 'user.view', 'name': '查看用户', 'description': '查看用户列表和详细信息'},
        {'code': 'user.create', 'name': '创建用户', 'description': '创建新用户账户'},
        {'code': 'user.update', 'name': '修改用户', 'description': '修改用户信息'},
        {'code': 'user.delete', 'name': '删除用户', 'description': '删除用户账户'},
        {'code': 'user.assign_role', 'name': '分配角色', 'description': '为用户分配角色'},
        {'code': 'user.batch_operation', 'name': '用户批量操作', 'description': '批量操作用户'},
        {'code': 'user.export', 'name': '导出用户', 'description': '导出用户数据'},
    ],
    
    # 角色管理权限
    'role_management': [
        {'code': 'role.view', 'name': '查看角色', 'description': '查看角色列表和详细信息'},
        {'code': 'role.create', 'name': '创建角色', 'description': '创建新角色'},
        {'code': 'role.update', 'name': '修改角色', 'description': '修改角色信息和权限'},
        {'code': 'role.delete', 'name': '删除角色', 'description': '删除非系统角色'},
        {'code': 'role.assign_permission', 'name': '分配权限', 'description': '为角色分配权限'},
    ],
    
    # 集群管理权限
    'cluster_management': [
        {'code': 'cluster.view', 'name': '查看集群', 'description': '查看OpenStack和K8s集群信息'},
        {'code': 'cluster.create', 'name': '创建集群', 'description': '添加新的集群配置'},
        {'code': 'cluster.update', 'name': '修改集群', 'description': '修改集群配置'},
        {'code': 'cluster.delete', 'name': '删除集群', 'description': '删除集群配置'},
        {'code': 'cluster.test_connection', 'name': '测试连接', 'description': '测试集群连接状态'},
    ],
    
    # 实例管理权限
    'instance_management': [
        {'code': 'instance.view', 'name': '查看实例', 'description': '查看虚拟机实例'},
        {'code': 'instance.create', 'name': '创建实例', 'description': '创建新的虚拟机实例'},
        {'code': 'instance.start', 'name': '启动实例', 'description': '启动虚拟机实例'},
        {'code': 'instance.stop', 'name': '停止实例', 'description': '停止虚拟机实例'},
        {'code': 'instance.restart', 'name': '重启实例', 'description': '重启虚拟机实例'},
        {'code': 'instance.delete', 'name': '删除实例', 'description': '删除虚拟机实例'},
        {'code': 'instance.resize', 'name': '调整实例', 'description': '调整实例规格'},
        {'code': 'instance.console', 'name': '访问控制台', 'description': '访问虚拟机控制台'},
        {'code': 'instance.snapshot', 'name': '创建快照', 'description': '创建实例快照'},
        {'code': 'instance.batch_operation', 'name': '批量操作', 'description': '批量操作实例'},
    ],
    
    # 存储管理权限
    'volume_management': [
        {'code': 'volume.view', 'name': '查看卷', 'description': '查看存储卷'},
        {'code': 'volume.create', 'name': '创建卷', 'description': '创建新的存储卷'},
        {'code': 'volume.attach', 'name': '挂载卷', 'description': '挂载存储卷到实例'},
        {'code': 'volume.detach', 'name': '卸载卷', 'description': '从实例卸载存储卷'},
        {'code': 'volume.extend', 'name': '扩展卷', 'description': '扩展存储卷大小'},
        {'code': 'volume.delete', 'name': '删除卷', 'description': '删除存储卷'},
        {'code': 'volume.snapshot', 'name': '创建卷快照', 'description': '创建存储卷快照'},
    ],
    
    # 网络管理权限
    'network_management': [
        {'code': 'network.view', 'name': '查看网络', 'description': '查看网络配置'},
        {'code': 'network.create', 'name': '创建网络', 'description': '创建新的网络'},
        {'code': 'network.update', 'name': '修改网络', 'description': '修改网络配置'},
        {'code': 'network.delete', 'name': '删除网络', 'description': '删除网络'},
        {'code': 'network.topology', 'name': '网络拓扑', 'description': '查看网络拓扑图'},
        {'code': 'router.manage', 'name': '路由管理', 'description': '管理网络路由'},
        {'code': 'security_group.manage', 'name': '安全组管理', 'description': '管理安全组规则'},
    ],
    
    # Kubernetes管理权限
    'k8s_management': [
        {'code': 'k8s.view', 'name': '查看K8s资源', 'description': '查看Kubernetes资源'},
        {'code': 'k8s.namespace.manage', 'name': '命名空间管理', 'description': '管理K8s命名空间'},
        {'code': 'k8s.pod.view', 'name': '查看Pod', 'description': '查看Pod信息'},
        {'code': 'k8s.pod.manage', 'name': '管理Pod', 'description': '创建、删除、重启Pod'},
        {'code': 'k8s.pod.logs', 'name': '查看日志', 'description': '查看Pod日志'},
        {'code': 'k8s.pod.exec', 'name': '执行命令', 'description': '在Pod中执行命令'},
        {'code': 'k8s.workload.manage', 'name': '工作负载管理', 'description': '管理Deployment、Service等'},
        {'code': 'k8s.node.view', 'name': '查看节点', 'description': '查看集群节点信息'},
    ],
    
    # 镜像管理权限
    'image_management': [
        {'code': 'image.view', 'name': '查看镜像', 'description': '查看系统镜像'},
        {'code': 'image.upload', 'name': '上传镜像', 'description': '上传新的镜像'},
        {'code': 'image.delete', 'name': '删除镜像', 'description': '删除镜像'},
        {'code': 'image.share', 'name': '共享镜像', 'description': '设置镜像共享权限'},
    ],
    
    # 快照管理权限
    'snapshot_management': [
        {'code': 'snapshot.view', 'name': '查看快照', 'description': '查看快照列表'},
        {'code': 'snapshot.create', 'name': '创建快照备份', 'description': '创建实例或卷快照'},
        {'code': 'snapshot.delete', 'name': '删除快照', 'description': '删除快照'},
        {'code': 'snapshot.restore', 'name': '恢复快照', 'description': '从快照恢复资源'},
    ],
    
    # 系统管理权限
    'system_management': [
        {'code': 'system.view_logs', 'name': '查看系统日志', 'description': '查看操作日志和系统日志'},
        {'code': 'system.export_data', 'name': '数据导出', 'description': '导出系统数据'},
        {'code': 'system.monitor', 'name': '系统监控', 'description': '查看系统监控信息'},
        {'code': 'system.settings', 'name': '系统设置', 'description': '修改系统设置'},
    ]
}

# 默认角色定义
DEFAULT_ROLES = [
    {
        'code': 'super_admin',
        'name': '超级管理员',
        'description': '系统超级管理员，拥有所有权限',
        'level': 100,
        'is_system': True,
        'permissions': 'ALL'  # 拥有所有权限
    },
    {
        'code': 'admin',
        'name': '系统管理员',
        'description': '系统管理员，可以管理集群和资源，但不能管理用户',
        'level': 80,
        'is_system': True,
        'permissions': [
            # 集群管理
            'cluster.view', 'cluster.create', 'cluster.update', 'cluster.delete', 'cluster.test_connection',
            # 实例管理
            'instance.view', 'instance.create', 'instance.start', 'instance.stop', 'instance.restart',
            'instance.delete', 'instance.resize', 'instance.console', 'instance.snapshot', 'instance.batch_operation',
            # 存储管理
            'volume.view', 'volume.create', 'volume.attach', 'volume.detach', 'volume.extend', 'volume.delete', 'volume.snapshot',
            # 网络管理
            'network.view', 'network.create', 'network.update', 'network.delete', 'network.topology',
            'router.manage', 'security_group.manage',
            # K8s管理
            'k8s.view', 'k8s.namespace.manage', 'k8s.pod.view', 'k8s.pod.manage', 'k8s.pod.logs',
            'k8s.pod.exec', 'k8s.workload.manage', 'k8s.node.view',
            # 镜像管理
            'image.view', 'image.upload', 'image.delete', 'image.share',
            # 快照管理
            'snapshot.view', 'snapshot.create', 'snapshot.delete', 'snapshot.restore',
            # 系统管理
            'system.view_logs', 'system.export_data', 'system.monitor'
        ]
    },
    {
        'code': 'operator',
        'name': '运维操作员',
        'description': '运维操作员，可以执行大部分资源操作，但不能删除关键资源',
        'level': 60,
        'is_system': True,
        'permissions': [
            # 集群查看
            'cluster.view', 'cluster.test_connection',
            # 实例管理（不能删除）
            'instance.view', 'instance.create', 'instance.start', 'instance.stop', 'instance.restart',
            'instance.resize', 'instance.console', 'instance.snapshot',
            # 存储管理（不能删除）
            'volume.view', 'volume.create', 'volume.attach', 'volume.detach', 'volume.extend', 'volume.snapshot',
            # 网络查看
            'network.view', 'network.topology',
            # K8s管理（基础操作）
            'k8s.view', 'k8s.pod.view', 'k8s.pod.manage', 'k8s.pod.logs', 'k8s.workload.manage', 'k8s.node.view',
            # 镜像查看
            'image.view',
            # 快照管理
            'snapshot.view', 'snapshot.create', 'snapshot.restore',
            # 系统监控
            'system.export_data', 'system.monitor'
        ]
    },
    {
        'code': 'viewer',
        'name': '只读用户',
        'description': '只读用户，只能查看资源信息，无任何操作权限',
        'level': 20,
        'is_system': True,
        'permissions': [
            # 只能查看
            'cluster.view', 'instance.view', 'volume.view', 'network.view', 'network.topology',
            'k8s.view', 'k8s.pod.view', 'k8s.node.view', 'image.view', 'snapshot.view',
            'system.monitor'
        ]
    }
]

def init_permissions():
    """初始化系统权限"""
    print("正在初始化系统权限...")
    
    for category, permissions in SYSTEM_PERMISSIONS.items():
        print(f"  处理权限分类: {category}")
        
        for perm_data in permissions:
            # 检查权限是否已存在
            permission = Permission.query.filter_by(code=perm_data['code']).first()
            
            if not permission:
                # 创建新权限
                permission = Permission(
                    code=perm_data['code'],
                    name=perm_data['name'],
                    description=perm_data['description'],
                    category=category.replace('_', '.')
                )
                db.session.add(permission)
                print(f"    创建权限: {perm_data['code']}")
            else:
                # 更新现有权限
                permission.name = perm_data['name']
                permission.description = perm_data['description']
                permission.category = category.replace('_', '.')
                print(f"    更新权限: {perm_data['code']}")
    
    db.session.commit()
    print("权限初始化完成")

def init_roles():
    """初始化默认角色"""
    print("正在初始化默认角色...")
    
    for role_data in DEFAULT_ROLES:
        # 检查角色是否已存在
        role = Role.query.filter_by(code=role_data['code']).first()
        
        if not role:
            # 创建新角色
            role = Role(
                code=role_data['code'],
                name=role_data['name'],
                description=role_data['description'],
                level=role_data['level'],
                is_system=role_data['is_system']
            )
            db.session.add(role)
            print(f"  创建角色: {role_data['name']}")
        else:
            # 更新现有角色
            role.name = role_data['name']
            role.description = role_data['description']
            role.level = role_data['level']
            role.is_system = role_data['is_system']
            print(f"  更新角色: {role_data['name']}")
        
        # 分配权限
        if role_data['permissions'] == 'ALL':
            # 超级管理员拥有所有权限
            all_permissions = Permission.query.filter_by(is_active=True).all()
            role.permissions = all_permissions
            print(f"    为角色 {role.name} 分配所有权限")
        else:
            # 根据权限码分配权限
            permissions = Permission.query.filter(
                Permission.code.in_(role_data['permissions']),
                Permission.is_active == True
            ).all()
            role.permissions = permissions
            print(f"    为角色 {role.name} 分配 {len(permissions)} 个权限")
    
    db.session.commit()
    print("角色初始化完成")

def migrate_existing_users():
    """迁移现有用户到新的角色系统"""
    from app.models.user import User
    
    print("正在迁移现有用户...")
    
    users = User.query.all()
    for user in users:
        if hasattr(user, 'role') and user.role:
            # 查找对应的角色对象
            role = Role.query.filter_by(code=user.role).first()
            if role:
                # 检查是否已有角色分配记录
                existing_assignment = UserRole.query.filter_by(
                    user_id=user.id,
                    role_id=role.id
                ).first()
                
                if not existing_assignment:
                    # 创建用户角色分配记录
                    user_role = UserRole(
                        user_id=user.id,
                        role_id=role.id,
                        is_primary=True,
                        assigned_by=user.id  # 自己分配给自己
                    )
                    db.session.add(user_role)
                    print(f"  为用户 {user.username} 分配角色 {role.name}")
    
    db.session.commit()
    print("用户迁移完成")

def init_rbac_system():
    """完整初始化RBAC系统"""
    print("开始初始化RBAC系统...")
    
    try:
        # 1. 初始化权限
        init_permissions()
        
        # 2. 初始化角色
        init_roles()
        
        # 3. 迁移现有用户
        migrate_existing_users()
        
        print("RBAC系统初始化成功!")
        return True
        
    except Exception as e:
        print(f"RBAC系统初始化失败: {str(e)}")
        db.session.rollback()
        return False

def get_permission_tree():
    """获取权限树结构，用于前端展示"""
    permissions = Permission.query.filter_by(is_active=True).all()
    
    tree = {}
    for permission in permissions:
        category = permission.category
        if category not in tree:
            tree[category] = {
                'name': category.replace('_', ' ').title(),
                'permissions': []
            }
        tree[category]['permissions'].append(permission.to_dict())
    
    return tree

if __name__ == '__main__':
    # 可以直接运行此脚本进行初始化
    from app import create_app
    
    app = create_app()
    with app.app_context():
        init_rbac_system()