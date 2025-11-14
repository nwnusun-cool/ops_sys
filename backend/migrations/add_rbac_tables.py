"""
RBAC系统数据表迁移脚本
创建角色、权限和用户角色关联表
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.base import db
from app.models import Role, Permission, UserRole
from app.utils.role_permissions import init_rbac_system

def create_rbac_tables():
    """创建RBAC相关表"""
    app = create_app()
    
    with app.app_context():
        print("正在创建RBAC系统数据表...")
        
        try:
            # 创建所有表
            db.create_all()
            print("[OK] 数据表创建完成")
            
            # 初始化权限和角色数据
            print("正在初始化RBAC系统数据...")
            success = init_rbac_system()
            
            if success:
                print("[OK] RBAC系统初始化成功")
                print("\n默认角色:")
                roles = Role.query.all()
                for role in roles:
                    print(f"  - {role.name} ({role.code}) - 等级: {role.level} - 权限数: {len(role.permissions)}")
                
                print(f"\n总共创建了 {Permission.query.count()} 个权限")
                print(f"总共创建了 {Role.query.count()} 个角色")
                
            else:
                print("[ERROR] RBAC系统初始化失败")
                return False
                
        except Exception as e:
            print(f"[ERROR] 创建表失败: {str(e)}")
            return False
    
    return True

def show_rbac_info():
    """显示RBAC系统信息"""
    app = create_app()
    
    with app.app_context():
        print("\n=== RBAC系统信息 ===")
        
        # 权限信息
        permissions = Permission.query.all()
        print(f"\n权限总数: {len(permissions)}")
        
        categories = {}
        for perm in permissions:
            if perm.category not in categories:
                categories[perm.category] = []
            categories[perm.category].append(perm)
        
        for category, perms in categories.items():
            print(f"  {category}: {len(perms)}个权限")
        
        # 角色信息
        roles = Role.query.all()
        print(f"\n角色总数: {len(roles)}")
        for role in roles:
            system_flag = "系统" if role.is_system else "自定义"
            status = "启用" if role.is_active else "禁用"
            print(f"  {role.name} ({role.code}) - {system_flag} - {status} - 等级{role.level} - {len(role.permissions)}个权限")
        
        # 用户角色分配信息
        user_roles = UserRole.query.all()
        print(f"\n用户角色分配: {len(user_roles)}条记录")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='RBAC系统数据库迁移工具')
    parser.add_argument('--create', action='store_true', help='创建RBAC表和初始化数据')
    parser.add_argument('--info', action='store_true', help='显示RBAC系统信息')
    parser.add_argument('--init-only', action='store_true', help='仅初始化数据（表已存在）')
    
    args = parser.parse_args()
    
    if args.create:
        if create_rbac_tables():
            print("\n[SUCCESS] RBAC系统部署成功!")
        else:
            print("\n[FAILED] RBAC系统部署失败!")
            sys.exit(1)
    
    elif args.init_only:
        app = create_app()
        with app.app_context():
            print("正在初始化RBAC系统数据...")
            if init_rbac_system():
                print("[OK] RBAC系统数据初始化成功")
            else:
                print("[ERROR] RBAC系统数据初始化失败")
    
    elif args.info:
        show_rbac_info()
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main()