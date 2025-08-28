#!/usr/bin/env python3
"""
测试集群连接
"""
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from app import create_app
from app.models.cluster import OpenstackCluster
from app.services.openstack_service import openstack_service

def test_cluster_connection():
    print("测试集群连接")
    print("=" * 50)
    
    # 创建应用上下文
    app = create_app()
    
    with app.app_context():
        # 获取集群2
        cluster = OpenstackCluster.query.get(2)
        if not cluster:
            print("X 集群2不存在")
            return
        
        print(f"测试集群: {cluster.name}")
        print(f"认证URL: {cluster.auth_url}")
        print(f"区域: {cluster.region_name}")
        
        # 获取凭据（调试）
        credentials = cluster.get_credentials()
        print(f"用户名: {credentials.get('username')}")
        print(f"项目名: {credentials.get('project_name')}")
        print(f"用户域: {credentials.get('user_domain_name')}")
        print(f"项目域: {credentials.get('project_domain_name')}")
        print()
        
        # 测试连接
        print("开始连接测试...")
        result = openstack_service.test_cluster_connection(2)
        
        if result['success']:
            print(f"+ 连接成功: {result['message']}")
        else:
            print(f"X 连接失败: {result['error']}")
            if 'technical_error' in result:
                print(f"技术错误: {result['technical_error']}")

if __name__ == '__main__':
    test_cluster_connection()