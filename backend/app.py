#!/usr/bin/env python3
"""
OpenStack运维管理平台 - 统一启动入口
"""
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def create_default_admin():
    """创建默认管理员账号"""
    from app.models.user import User
    from app.models.base import db
    
    # 检查是否已存在管理员
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@ops.local',
            role='super_admin'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("+ 默认管理员账号已创建: admin/admin123")
        print("! 首次登录后请及时修改密码")

def initialize_app():
    """初始化应用"""
    from app import create_app, db
    
    # 设置环境变量
    env = os.getenv('FLASK_ENV', 'development')
    
    # 创建应用实例
    app = create_app(env)
    
    with app.app_context():
        try:
            # 创建数据库表
            db.create_all()
            print("+ 数据库表已初始化")
            
            # 创建默认管理员
            create_default_admin()
            
        except Exception as e:
            print(f"X 初始化失败: {e}")
            return None
    
    return app

def main():
    """主函数"""
    print("=" * 50)
    print("OpenStack运维管理平台 v2.0")
    print("=" * 50)
    
    # 初始化应用
    app = initialize_app()
    if not app:
        print("X 应用初始化失败")
        sys.exit(1)
    
    # 获取配置
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5001))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    print(f"+ 服务启动配置:")
    print(f"  - 环境: {os.getenv('FLASK_ENV', 'development')}")
    print(f"  - 地址: http://{host}:{port}")
    print(f"  - 调试: {'开启' if debug else '关闭'}")
    print(f"  - 数据库: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print("=" * 50)
    
    # 启动服务
    try:
        app.run(
            host=host,
            port=port,
            debug=debug,
            use_reloader=debug
        )
    except KeyboardInterrupt:
        print("\n+ 服务已安全停止")
    except Exception as e:
        print(f"X 服务启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()