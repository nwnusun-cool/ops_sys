"""
添加K8s集群表的数据库迁移脚本
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import K8sCluster

def add_k8s_tables():
    """添加K8s相关表"""
    app = create_app('development')
    
    with app.app_context():
        # 创建K8s表
        print("Creating K8s tables...")
        
        # 确保所有模型被导入
        from app.models.k8s_cluster import K8sCluster
        
        # 创建表
        db.create_all()
        print("✓ K8s tables created successfully")

if __name__ == '__main__':
    add_k8s_tables()