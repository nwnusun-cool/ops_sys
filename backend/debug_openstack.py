#!/usr/bin/env python3
"""
OpenStack连接诊断工具
用于测试OpenStack集群连接和资源获取
"""
import sys
from keystoneauth1.identity import v3
from keystoneauth1 import session
from novaclient import client as nova_client
from cinderclient import client as cinder_client

def test_openstack_connection(auth_url, username, password, project_name, 
                             user_domain_name='Default', project_domain_name='Default',
                             region_name='RegionOne'):
    """测试OpenStack连接"""
    
    print(f"🔗 测试连接到: {auth_url}")
    print(f"👤 用户: {username}")
    print(f"📁 项目: {project_name}")
    print(f"🌍 区域: {region_name}")
    print("-" * 50)
    
    try:
        # 创建认证对象
        auth = v3.Password(
            auth_url=auth_url,
            username=username,
            password=password,
            project_name=project_name,
            user_domain_name=user_domain_name,
            project_domain_name=project_domain_name
        )
        
        # 创建会话
        sess = session.Session(auth=auth)
        
        print("✅ 认证会话创建成功")
        
        # 获取token验证连接
        token = sess.get_token()
        print(f"✅ Token获取成功: {token[:20]}...")
        
        # 创建Nova客户端
        nova = nova_client.Client(2, session=sess)
        print("✅ Nova客户端创建成功")
        
        # 创建Cinder客户端  
        cinder = cinder_client.Client(3, session=sess)
        print("✅ Cinder客户端创建成功")
        
        # 测试服务列表
        print("\n📊 服务状态:")
        try:
            services = nova.services.list()
            print(f"✅ Nova服务数量: {len(services)}")
        except Exception as e:
            print(f"❌ Nova服务获取失败: {e}")
        
        # 测试实例列表
        print("\n🖥️  实例统计:")
        try:
            instances = nova.servers.list(detailed=True)
            print(f"✅ 实例总数: {len(instances)}")
            
            if instances:
                status_count = {}
                for instance in instances:
                    status = instance.status
                    status_count[status] = status_count.get(status, 0) + 1
                
                for status, count in status_count.items():
                    print(f"   - {status}: {count} 个")
            else:
                print("   📝 没有找到实例")
                
        except Exception as e:
            print(f"❌ 实例列表获取失败: {e}")
        
        # 测试卷列表
        print("\n💿 存储统计:")
        try:
            volumes = cinder.volumes.list(detailed=True)
            print(f"✅ 卷总数: {len(volumes)}")
            
            if volumes:
                status_count = {}
                total_size = 0
                for volume in volumes:
                    status = volume.status
                    status_count[status] = status_count.get(status, 0) + 1
                    total_size += volume.size
                
                for status, count in status_count.items():
                    print(f"   - {status}: {count} 个")
                print(f"   💾 总容量: {total_size} GB")
            else:
                print("   📝 没有找到卷")
                
        except Exception as e:
            print(f"❌ 卷列表获取失败: {e}")
        
        # 测试配额
        print("\n📈 配额信息:")
        try:
            quotas = nova.quotas.get(project_name, detail=True)
            print(f"✅ 实例配额: {quotas.instances}")
            print(f"✅ CPU配额: {quotas.cores}")
            print(f"✅ 内存配额: {quotas.ram} MB")
        except Exception as e:
            print(f"❌ 配额获取失败: {e}")
            
        print("\n🎉 连接测试完成！")
        return True
        
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        return False

def main():
    """主函数"""
    print("🧪 OpenStack连接诊断工具")
    print("=" * 50)
    
    # 示例配置 - 请替换为你的实际配置
    config = {
        'auth_url': 'http://192.168.2.205:5000/v3',
        'username': input("请输入用户名: "),
        'password': input("请输入密码: "),
        'project_name': input("请输入项目名: "),
        'user_domain_name': input("请输入用户域 (默认Default): ") or 'Default',
        'project_domain_name': input("请输入项目域 (默认Default): ") or 'Default',
        'region_name': input("请输入区域名 (默认RegionOne): ") or 'RegionOne'
    }
    
    success = test_openstack_connection(**config)
    
    if success:
        print("\n✅ 诊断结果: 连接正常，可以在Web界面添加此集群")
    else:
        print("\n❌ 诊断结果: 连接失败，请检查网络和认证信息")
        
    print("\n💡 提示:")
    print("1. 如果连接成功但没有资源，说明集群确实为空")
    print("2. 如果认证失败，请检查用户名、密码和项目配置")
    print("3. 如果网络错误，请检查URL和网络连通性")

if __name__ == "__main__":
    main()