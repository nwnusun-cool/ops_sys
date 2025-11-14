"""
修复用户表角色枚举约束问题
将role字段从ENUM改为VARCHAR，支持动态角色
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models.base import db
from app.models.user import User
from sqlalchemy import text

def fix_user_role_enum():
    """修复用户表角色枚举问题"""
    app = create_app()
    
    with app.app_context():
        print("正在修复用户表角色字段...")
        
        try:
            # 检查数据库类型
            db_url = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            is_sqlite = 'sqlite' in db_url.lower()
            
            if is_sqlite:
                print("检测到SQLite数据库，执行SQLite兼容的修复方案...")
                fix_sqlite_role_enum()
            else:
                print("检测到其他数据库，执行通用修复方案...")
                fix_generic_role_enum()
                
            print("[OK] 用户表角色字段修复完成")
            return True
            
        except Exception as e:
            print(f"[ERROR] 修复失败: {str(e)}")
            db.session.rollback()
            return False

def fix_sqlite_role_enum():
    """SQLite特定的修复方案"""
    # SQLite不支持ALTER COLUMN，需要重建表
    
    # 1. 创建新的用户表
    db.session.execute(text("""
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            email VARCHAR(120) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'viewer',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME,
            login_count INTEGER DEFAULT 0
        )
    """))
    
    # 2. 复制数据到新表
    db.session.execute(text("""
        INSERT INTO users_new (id, username, email, password_hash, role, is_active, created_at, updated_at, last_login, login_count)
        SELECT id, username, email, password_hash, role, is_active, created_at, updated_at, last_login, login_count
        FROM users
    """))
    
    # 3. 删除旧表
    db.session.execute(text("DROP TABLE users"))
    
    # 4. 重命名新表
    db.session.execute(text("ALTER TABLE users_new RENAME TO users"))
    
    # 5. 重建索引
    db.session.execute(text("CREATE UNIQUE INDEX ix_users_username ON users (username)"))
    db.session.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
    
    db.session.commit()

def fix_generic_role_enum():
    """通用数据库修复方案"""
    # 对于PostgreSQL, MySQL等数据库
    
    # 1. 删除枚举约束
    db.session.execute(text("ALTER TABLE users DROP CONSTRAINT IF EXISTS user_roles"))
    
    # 2. 修改字段类型
    db.session.execute(text("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(50)"))
    
    db.session.commit()

def check_and_fix_data():
    """检查并修复数据"""
    app = create_app()
    
    with app.app_context():
        print("检查用户数据...")
        
        try:
            users = User.query.all()
            print(f"找到 {len(users)} 个用户:")
            
            for user in users:
                print(f"  - {user.username}: {user.role}")
                
            # 检查是否有角色不在新角色系统中的用户
            from app.models.role import Role
            valid_roles = {role.code for role in Role.query.filter_by(is_active=True).all()}
            print(f"有效角色代码: {valid_roles}")
            
            invalid_users = []
            for user in users:
                if user.role not in valid_roles:
                    invalid_users.append(user)
            
            if invalid_users:
                print(f"发现 {len(invalid_users)} 个用户的角色不在新系统中:")
                for user in invalid_users:
                    print(f"  - {user.username}: {user.role} (无效)")
                    
                    # 选择处理方式
                    print(f"为用户 {user.username} 选择修复方式:")
                    print("1. 改为 viewer (只读用户)")
                    print("2. 创建对应的角色")
                    
                    # 自动修复：改为viewer
                    user.role = 'viewer'
                    print(f"  -> 已修复为 viewer")
                
                db.session.commit()
                print("[OK] 无效角色数据已修复")
            else:
                print("[OK] 所有用户角色都有效")
                
        except Exception as e:
            print(f"[ERROR] 检查数据失败: {str(e)}")
            db.session.rollback()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='修复用户表角色枚举问题')
    parser.add_argument('--fix-enum', action='store_true', help='修复角色字段枚举约束')
    parser.add_argument('--check-data', action='store_true', help='检查和修复数据')
    parser.add_argument('--all', action='store_true', help='执行所有修复')
    
    args = parser.parse_args()
    
    if args.all or args.fix_enum:
        print("=== 修复角色枚举约束 ===")
        if fix_user_role_enum():
            print("枚举约束修复成功")
        else:
            print("枚举约束修复失败")
            sys.exit(1)
    
    if args.all or args.check_data:
        print("\n=== 检查和修复数据 ===")
        check_and_fix_data()
    
    if not any([args.fix_enum, args.check_data, args.all]):
        parser.print_help()

if __name__ == '__main__':
    main()