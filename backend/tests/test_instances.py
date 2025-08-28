#!/usr/bin/env python3
"""
测试实例管理功能
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

def test_instances_api():
    print("测试实例管理API")
    print("=" * 50)
    
    # 创建应用上下文
    app = create_app()
    
    with app.app_context():
        # 获取集群
        clusters = OpenstackCluster.query.filter_by(is_active=True).all()
        
        if not clusters:
            print("X 没有找到活跃的集群")
            return
        
        cluster = clusters[0]  # 使用第一个集群
        print(f"使用集群: {cluster.name} (ID: {cluster.id})")
        
        try:
            # 获取OpenStack客户端
            clients = openstack_service.get_cluster_clients(cluster.id)
            nova_client = clients['nova']
            
            print(f"+ 成功获取Nova客户端")
            
            # 获取实例列表
            print("获取实例列表...")
            servers = nova_client.servers.list(detailed=True)
            print(f"+ 找到 {len(servers)} 个实例")
            
            # 显示前5个实例
            for i, server in enumerate(servers[:5]):
                print(f"  {i+1}. {server.name} - {server.status} ({server.id})")
            
            if servers:
                # 测试获取第一个实例的详细信息
                first_server = servers[0]
                print(f"\n测试获取实例详情: {first_server.name}")
                
                server_detail = nova_client.servers.get(first_server.id)
                print(f"+ 实例详情获取成功")
                print(f"  - 名称: {server_detail.name}")
                print(f"  - 状态: {server_detail.status}")
                print(f"  - 规格: {server_detail.flavor['id']}")
                print(f"  - 镜像: {server_detail.image['id'] if server_detail.image else 'Boot from volume'}")
                print(f"  - 创建时间: {server_detail.created}")
                
                # 测试获取控制台日志
                try:
                    console_log = nova_client.servers.get_console_output(first_server.id, length=5)
                    print(f"+ 控制台日志获取成功 ({len(console_log.split(chr(10)))} 行)")
                except Exception as e:
                    print(f"- 控制台日志获取失败: {e}")
            
            print("\n+ 实例管理API测试完成")
            
        except Exception as e:
            print(f"X API测试失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_instances_api()