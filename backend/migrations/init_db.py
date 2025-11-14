"""
数据库初始化脚本
用于创建初始数据和迁移旧数据
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import User, OpenstackCluster, K8sCluster, OperationLog
from app.utils.config_manager import config_manager
import json

def init_database():
    """初始化数据库"""
    app = create_app('development')
    
    with app.app_context():
        # 创建所有表
        db.create_all()
        print("✓ Database tables created")
        
        # 创建默认用户
        create_default_users()
        
        # 迁移OpenStack配置
        migrate_openstack_config()
        
        print("✓ Database initialization completed")

def create_default_users():
    """创建默认用户"""
    # 创建超级管理员
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            role='super_admin'
        )
        admin.set_password('admin123')  # 生产环境需要修改
        db.session.add(admin)
        print("✓ Default admin user created (admin/admin123)")
    
    # 创建测试操作员
    operator = User.query.filter_by(username='operator').first()
    if not operator:
        operator = User(
            username='operator',
            email='operator@example.com',
            role='operator'
        )
        operator.set_password('operator123')
        db.session.add(operator)
        print("✓ Test operator user created (operator/operator123)")
    
    # 创建测试查看者
    viewer = User.query.filter_by(username='viewer').first()
    if not viewer:
        viewer = User(
            username='viewer',
            email='viewer@example.com',
            role='viewer'
        )
        viewer.set_password('viewer123')
        db.session.add(viewer)
        print("✓ Test viewer user created (viewer/viewer123)")
    
    db.session.commit()

def migrate_openstack_config():
    """迁移旧版OpenStack配置"""
    old_config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'app', 'config', 'config.json'
    )
    
    if not os.path.exists(old_config_path):
        print("ℹ No old config file found, skipping migration")
        return
    
    try:
        with open(old_config_path, 'r', encoding='utf-8') as f:
            old_config = json.load(f)
        
        # 迁移OpenStack环境
        if 'openstack_environments' in old_config:
            for name, env_config in old_config['openstack_environments'].items():
                existing_cluster = OpenstackCluster.query.filter_by(name=name).first()
                if existing_cluster:
                    print(f"ℹ Cluster {name} already exists, skipping")
                    continue
                
                cluster = OpenstackCluster(
                    name=name,
                    description=f'从旧版本迁移的集群 {name}',
                    auth_url=env_config.get('auth_url'),
                    region_name=env_config.get('region_name', 'RegionOne')
                )
                
                # 设置加密的凭据
                credentials = {
                    'username': env_config.get('username'),
                    'password': env_config.get('password'),
                    'project_name': env_config.get('project_name'),
                    'user_domain_name': env_config.get('user_domain_name', 'Default'),
                    'project_domain_name': env_config.get('project_domain_name', 'Default')
                }
                cluster.set_credentials(credentials)
                
                db.session.add(cluster)
                print(f"✓ Migrated cluster: {name}")
        
        db.session.commit()
        print("✓ OpenStack configuration migration completed")
        
    except Exception as e:
        print(f"✗ Migration failed: {str(e)}")
        db.session.rollback()

if __name__ == '__main__':
    init_database()