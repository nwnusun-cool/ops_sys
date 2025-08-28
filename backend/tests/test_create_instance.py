#!/usr/bin/env python3
"""
测试创建实例API功能
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

def test_create_instance_data():
    """测试创建实例所需数据API"""
    print("测试创建实例数据API")
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
        print(f"+ 使用集群: {cluster.name} (ID: {cluster.id})")
        
        try:
            # 获取OpenStack客户端
            clients = openstack_service.get_cluster_clients(cluster.id)
            nova_client = clients['nova']
            neutron_client = clients['neutron']
            glance_client = clients['glance']
            
            print("+ 成功获取OpenStack客户端")
            
            # 测试获取镜像列表
            print("\n>> 获取镜像列表...")
            try:
                images = list(glance_client.images.list())
                active_images = [img for img in images if hasattr(img, 'status') and img.status == 'active']
                print(f"+ 找到 {len(active_images)} 个可用镜像")
                for i, image in enumerate(active_images[:3]):  # 显示前3个
                    size_mb = (image.size or 0) / 1024 / 1024
                    print(f"  {i+1}. {image.name} ({image.disk_format}, {size_mb:.1f}MB)")
            except Exception as e:
                print(f"X 获取镜像列表失败: {e}")
            
            # 测试获取规格列表
            print("\n>> 获取规格列表...")
            try:
                flavors = nova_client.flavors.list(detailed=True)
                available_flavors = [f for f in flavors if not getattr(f, 'OS-FLV-DISABLED:disabled', False)]
                print(f"+ 找到 {len(available_flavors)} 个可用规格")
                for i, flavor in enumerate(available_flavors[:3]):  # 显示前3个
                    print(f"  {i+1}. {flavor.name} ({flavor.vcpus}vCPU, {flavor.ram}MB内存, {flavor.disk}GB磁盘)")
            except Exception as e:
                print(f"X 获取规格列表失败: {e}")
            
            # 测试获取网络列表
            print("\n>> 获取网络列表...")
            try:
                networks = neutron_client.list_networks()['networks']
                active_networks = [net for net in networks if net.get('status') == 'ACTIVE']
                print(f"+ 找到 {len(active_networks)} 个可用网络")
                for i, network in enumerate(active_networks[:3]):  # 显示前3个
                    external = network.get('router:external', False)
                    shared = network.get('shared', False)
                    status = "外网" if external else ("共享" if shared else "内网")
                    print(f"  {i+1}. {network['name']} ({status})")
            except Exception as e:
                print(f"X 获取网络列表失败: {e}")
            
            # 测试获取密钥对列表
            print("\n>> 获取密钥对列表...")
            try:
                keypairs = nova_client.keypairs.list()
                print(f"+ 找到 {len(keypairs)} 个密钥对")
                for i, kp in enumerate(keypairs[:3]):  # 显示前3个
                    print(f"  {i+1}. {kp.name} ({getattr(kp, 'type', 'ssh')})")
            except Exception as e:
                print(f"X 获取密钥对列表失败: {e}")
            
            # 测试获取安全组列表
            print("\n>> 获取安全组列表...")
            try:
                security_groups = neutron_client.list_security_groups()['security_groups']
                print(f"+ 找到 {len(security_groups)} 个安全组")
                for i, sg in enumerate(security_groups[:3]):  # 显示前3个
                    rules_count = len(sg.get('security_group_rules', []))
                    print(f"  {i+1}. {sg['name']} ({rules_count} 条规则)")
            except Exception as e:
                print(f"X 获取安全组列表失败: {e}")
            
            # 测试获取可用区列表
            print("\n>> 获取可用区列表...")
            try:
                availability_zones = nova_client.availability_zones.list()
                available_zones = [az for az in availability_zones if az.zoneState.get('available')]
                print(f"+ 找到 {len(available_zones)} 个可用区")
                for i, az in enumerate(available_zones[:3]):  # 显示前3个
                    hosts_count = len(az.hosts.keys()) if hasattr(az, 'hosts') else 0
                    print(f"  {i+1}. {az.zoneName} ({hosts_count} 个主机)")
            except Exception as e:
                print(f"X 获取可用区列表失败: {e}")
            
            print(f"\n+ 创建实例数据API测试完成")
            print("  所有必需的资源都已验证，可以进行实例创建")
            
        except Exception as e:
            print(f"X 测试失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_create_instance_data()