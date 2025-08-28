"""
完整的Flask应用启动脚本
包含数据库和用户认证功能
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置环境
os.environ['FLASK_ENV'] = 'development'

from app import create_app, db
from app.models import User, OpenstackCluster, OperationLog

def init_database(app):
    """初始化数据库"""
    with app.app_context():
        # 创建所有数据表
        db.create_all()
        print("✅ 数据库表创建成功")
        
        # 检查是否已有管理员用户
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            # 创建默认管理员
            admin = User(
                username='admin',
                email='admin@example.com',
                role='super_admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            
            # 创建测试用户
            test_user = User(
                username='test',
                email='test@example.com', 
                role='operator'
            )
            test_user.set_password('test123')
            db.session.add(test_user)
            
            db.session.commit()
            print("✅ 默认用户创建成功:")
            print("   - admin / admin123 (超级管理员)")
            print("   - test / test123 (操作员)")

def create_test_data(app):
    """创建测试数据"""
    with app.app_context():
        # 检查是否已有测试集群
        cluster = OpenstackCluster.query.filter_by(name='test-cluster').first()
        if not cluster:
            cluster = OpenstackCluster(
                name='test-cluster',
                description='测试OpenStack集群',
                auth_url='http://192.168.1.100:5000/v3',
                region_name='RegionOne'
            )
            
            # 设置测试凭据
            test_credentials = {
                'username': 'admin',
                'password': 'password',
                'project_name': 'admin',
                'user_domain_name': 'Default',
                'project_domain_name': 'Default'
            }
            cluster.set_credentials(test_credentials)
            
            db.session.add(cluster)
            db.session.commit()
            print("✅ 测试集群创建成功")

if __name__ == '__main__':
    # 创建Flask应用
    app = create_app('development')
    
    # 初始化数据库
    init_database(app)
    
    # 创建测试数据
    create_test_data(app)
    
    print("\n🚀 启动开发服务器...")
    print("📍 访问地址: http://localhost:5001")
    print("🔐 登录测试:")
    print("   管理员: admin / admin123")
    print("   操作员: test / test123")
    print("🔧 调试模式: ON")
    
    # 启动应用
    app.run(
        host='0.0.0.0',
        port=5001,
        debug=True,
        use_reloader=False  # 避免重复初始化数据库
    )