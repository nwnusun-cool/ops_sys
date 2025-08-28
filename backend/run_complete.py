"""
完整功能测试启动脚本
包含用户认证、数据库、前端界面的完整应用
"""
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 设置环境
os.environ['FLASK_ENV'] = 'development'
os.environ['FLASK_DEBUG'] = '1'

from app import create_app, db
from app.models import User, OpenstackCluster, OperationLog

def setup_application():
    """设置应用"""
    app = create_app('development')
    
    with app.app_context():
        # 创建数据库表
        try:
            db.create_all()
            print("✅ 数据库表创建成功")
        except Exception as e:
            print(f"❌ 数据库表创建失败: {e}")
            return None, None
        
        # 创建默认用户
        create_default_users()
        
        # 创建测试集群
        create_test_cluster()
        
        return app, db

def create_default_users():
    """创建默认用户"""
    try:
        # 检查管理员是否存在
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                role='super_admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            print("✅ 管理员用户创建: admin / admin123")
        
        # 检查测试操作员是否存在
        operator = User.query.filter_by(username='test').first()
        if not operator:
            operator = User(
                username='test',
                email='test@example.com',
                role='operator'
            )
            operator.set_password('test123')
            db.session.add(operator)
            print("✅ 操作员用户创建: test / test123")
        
        # 检查查看者是否存在
        viewer = User.query.filter_by(username='viewer').first()
        if not viewer:
            viewer = User(
                username='viewer',
                email='viewer@example.com',
                role='viewer'
            )
            viewer.set_password('viewer123')
            db.session.add(viewer)
            print("✅ 查看者用户创建: viewer / viewer123")
        
        db.session.commit()
        
    except Exception as e:
        print(f"❌ 用户创建失败: {e}")
        db.session.rollback()

def create_test_cluster():
    """创建测试集群"""
    try:
        cluster = OpenstackCluster.query.filter_by(name='demo-cluster').first()
        if not cluster:
            cluster = OpenstackCluster(
                name='demo-cluster',
                description='演示集群 - 用于测试功能',
                auth_url='http://demo.openstack.org:5000/v3',
                region_name='RegionOne'
            )
            
            # 设置演示凭据
            demo_credentials = {
                'username': 'demo',
                'password': 'demo',
                'project_name': 'demo',
                'user_domain_name': 'Default',
                'project_domain_name': 'Default'
            }
            cluster.set_credentials(demo_credentials)
            
            db.session.add(cluster)
            db.session.commit()
            print("✅ 演示集群创建成功")
    
    except Exception as e:
        print(f"❌ 集群创建失败: {e}")
        db.session.rollback()

def print_startup_info():
    """打印启动信息"""
    print("\n" + "="*60)
    print("🎉 OpenStack运维管理平台 v2.0")
    print("="*60)
    print("📍 访问地址: http://localhost:5001")
    print("🔐 测试账户:")
    print("   👑 超级管理员: admin / admin123")
    print("   🔧 操作员: test / test123")
    print("   👀 查看者: viewer / viewer123")
    print("\n📋 功能测试:")
    print("   ✅ 用户登录/退出")
    print("   ✅ 权限控制")
    print("   ✅ 仪表盘展示") 
    print("   ✅ 集群管理")
    print("   ✅ 用户管理")
    print("   ⏳ 实例管理 (下个版本)")
    print("   ⏳ 卷管理 (下个版本)")
    print("\n🔧 调试模式: ON")
    print("📝 日志级别: INFO")
    print("="*60 + "\n")

if __name__ == '__main__':
    print("🚀 启动OpenStack运维管理平台...")
    
    # 设置应用
    app, database = setup_application()
    
    if app is None:
        print("❌ 应用启动失败")
        exit(1)
    
    # 打印启动信息
    print_startup_info()
    
    # 启动开发服务器
    try:
        app.run(
            host='0.0.0.0',
            port=5001,
            debug=True,
            use_reloader=False  # 避免重复初始化
        )
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}")