"""
SQLite版本启动脚本
确保使用SQLite数据库
"""
import os
from dotenv import load_dotenv

# 强制加载.env文件
load_dotenv(override=True)

# 强制设置SQLite数据库
os.environ['DATABASE_URL'] = 'sqlite:///ops_sys_dev.db'
os.environ['FLASK_ENV'] = 'development'
os.environ['FLASK_DEBUG'] = '1'

print(f"数据库配置: {os.environ.get('DATABASE_URL')}")

from app import create_app, db
from app.models import User, OpenstackCluster, OperationLog

def setup_application():
    """设置应用"""
    app = create_app('development')
    
    # 打印实际使用的数据库URL
    print(f"实际数据库URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    with app.app_context():
        try:
            # 删除所有表（重新开始）
            db.drop_all()
            print("清空现有数据库表")
            
            # 创建所有表
            db.create_all()
            print("数据库表创建成功")
            
            # 创建默认用户
            create_users()
            
            # 创建测试集群
            create_test_cluster()
            
            return app
            
        except Exception as e:
            print(f"数据库设置失败: {e}")
            import traceback
            traceback.print_exc()
            return None

def create_users():
    """创建测试用户"""
    users_data = [
        ('admin', 'admin@example.com', 'admin123', 'super_admin'),
        ('test', 'test@example.com', 'test123', 'operator'),
        ('viewer', 'viewer@example.com', 'viewer123', 'viewer')
    ]
    
    for username, email, password, role in users_data:
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        print(f"创建用户: {username} / {password} ({role})")
    
    db.session.commit()

def create_test_cluster():
    """创建测试集群"""
    cluster = OpenstackCluster(
        name='demo-cluster',
        description='演示集群',
        auth_url='http://demo.openstack.org:5000/v3',
        region_name='RegionOne'
    )
    
    # 设置测试凭据
    credentials = {
        'username': 'demo',
        'password': 'demo',
        'project_name': 'demo',
        'user_domain_name': 'Default',
        'project_domain_name': 'Default'
    }
    cluster.set_credentials(credentials)
    
    db.session.add(cluster)
    db.session.commit()
    print("创建测试集群: demo-cluster")

if __name__ == '__main__':
    print("启动SQLite版本...")
    
    app = setup_application()
    
    if app is None:
        print("应用启动失败")
        exit(1)
    
    print("\n" + "="*50)
    print("OpenStack运维管理平台")
    print("="*50)
    print("地址: http://localhost:5001")
    print("账户:")
    print("   admin / admin123 (超级管理员)")
    print("   test / test123 (操作员)")
    print("   viewer / viewer123 (查看者)")
    print("数据库: SQLite")
    print("="*50 + "\n")
    
    try:
        app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)
    except KeyboardInterrupt:
        print("\n服务器已停止")