"""
应用启动脚本
"""
import os
from app import create_app, db
from flask_migrate import upgrade

def deploy():
    """部署应用"""
    app = create_app(os.getenv('FLASK_ENV') or 'default')
    
    with app.app_context():
        # 创建数据库表
        db.create_all()
        
        # 运行数据库迁移
        try:
            upgrade()
        except Exception as e:
            print(f"Database migration failed: {e}")
        
        # 创建默认管理员用户
        create_admin_user()

def create_admin_user():
    """创建默认管理员用户"""
    from app.models.user import User
    
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            role='super_admin'
        )
        admin.set_password('admin123')  # 默认密码，首次登录后需要修改
        db.session.add(admin)
        db.session.commit()
        print("Default admin user created: admin/admin123")

if __name__ == '__main__':
    app = create_app()
    
    # 开发环境下自动创建表
    if app.config.get('DEBUG'):
        with app.app_context():
            db.create_all()
            create_admin_user()
    
    app.run(host='0.0.0.0', port=5001, debug=True)