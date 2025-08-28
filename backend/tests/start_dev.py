"""
开发环境启动脚本
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

def create_dev_data():
    """创建开发环境测试数据"""
    # 检查是否已有数据
    if User.query.count() > 0:
        return
    
    print("Creating development test data...")
    
    # 创建测试用户
    admin = User(
        username='admin',
        email='admin@test.com',
        role='super_admin'
    )
    admin.set_password('admin')
    
    operator = User(
        username='test',
        email='test@test.com', 
        role='operator'
    )
    operator.set_password('test')
    
    db.session.add_all([admin, operator])
    db.session.commit()
    
    print("✓ Test users created")
    print("  - admin/admin (super_admin)")
    print("  - test/test (operator)")

if __name__ == '__main__':
    app = create_app('development')
    
    with app.app_context():
        # 创建数据库表
        db.create_all()
        
        # 创建开发数据
        create_dev_data()
        
        print(" Starting development server...")
        print("URL: http://localhost:5001")
        print("Debug mode: ON")
        
    # 启动开发服务器
    app.run(
        host='0.0.0.0',
        port=5001,
        debug=True,
        use_reloader=True
    )