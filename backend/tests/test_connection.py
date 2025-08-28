#!/usr/bin/env python3
"""
OpenStack连接详细测试脚本
"""
import os
import sys
from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneauth1 import exceptions as keystone_exceptions
from novaclient import client as nova_client
from cinderclient import client as cinder_client
import requests
from urllib.parse import urlparse

def test_network_connectivity(auth_url):
    """测试网络连通性"""
    print("🌐 测试网络连通性...")
    
    parsed = urlparse(auth_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    
    try:
        # 测试基本HTTP连接
        response = requests.get(base_url, timeout=10)
        print(f"✅ HTTP连接成功 - 状态码: {response.status_code}")
        return True
    except requests.exceptions.ConnectTimeout:
        print("❌ 连接超时 - 检查网络连通性")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ 连接错误 - 服务器可能不可达")
        return False
    except Exception as e:
        print(f"❌ 网络测试失败: {e}")
        return False

def test_keystone_endpoint(auth_url):
    """测试Keystone端点"""
    print("🔑 测试Keystone端点...")
    
    try:
        response = requests.get(auth_url, timeout=10)
        print(f"✅ Keystone端点响应 - 状态码: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if 'version' in data or 'versions' in data:
                    print("✅ Keystone版本信息获取成功")
                    return True
            except:
                pass
        
        return response.status_code < 400
        
    except Exception as e:
        print(f"❌ Keystone端点测试失败: {e}")
        return False

def test_authentication(auth_url, username, password, project_name, 
                       user_domain_name='Default', project_domain_name='Default'):
    """测试认证"""
    print("🔐 测试认证...")
    
    try:
        auth = v3.Password(
            auth_url=auth_url,
            username=username,
            password=password,
            project_name=project_name,
            user_domain_name=user_domain_name,
            project_domain_name=project_domain_name
        )
        
        sess = session.Session(auth=auth)
        
        # 尝试获取token
        token = sess.get_token()
        print(f"✅ 认证成功 - Token: {token[:20]}...")
        
        # 获取用户信息
        user_id = sess.get_user_id()
        project_id = sess.get_project_id()
        print(f"✅ 用户ID: {user_id}")
        print(f"✅ 项目ID: {project_id}")
        
        return sess
        
    except keystone_exceptions.Unauthorized:
        print("❌ 认证失败 - 用户名或密码错误")
        return None
    except keystone_exceptions.NotFound:
        print("❌ 认证失败 - 项目不存在或用户无权限")
        return None
    except Exception as e:
        print(f"❌ 认证过程出错: {e}")
        print(f"错误类型: {type(e).__name__}")
        return None

def test_service_endpoints(sess):
    """测试服务端点"""
    print("🔧 测试服务端点...")
    
    try:
        # 测试Nova服务
        nova = nova_client.Client(2, session=sess)
        print("✅ Nova客户端创建成功")
        
        # 尝试获取服务列表
        services = nova.services.list()
        print(f"✅ Nova服务列表获取成功 - 服务数量: {len(services)}")
        
        # 测试Cinder服务
        cinder = cinder_client.Client(3, session=sess)
        print("✅ Cinder客户端创建成功")
        
        return {'nova': nova, 'cinder': cinder}
        
    except Exception as e:
        print(f"❌ 服务端点测试失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        return None

def main():
    """主测试函数"""
    print("🧪 OpenStack详细连接诊断")
    print("=" * 50)
    
    # 你的配置 - 请根据实际情况修改
    config = {
        'auth_url': 'http://192.168.2.205:5000/v3',
        'username': input("请输入用户名: ").strip(),
        'password': input("请输入密码: ").strip(),
        'project_name': input("请输入项目名: ").strip(),
        'user_domain_name': input("用户域 (默认Default): ").strip() or 'Default',
        'project_domain_name': input("项目域 (默认Default): ").strip() or 'Default'
    }
    
    print(f"\n📋 测试配置:")
    print(f"认证URL: {config['auth_url']}")
    print(f"用户名: {config['username']}")
    print(f"项目名: {config['project_name']}")
    print(f"用户域: {config['user_domain_name']}")
    print(f"项目域: {config['project_domain_name']}")
    print("-" * 50)
    
    # 步骤1：测试网络连通性
    if not test_network_connectivity(config['auth_url']):
        print("\n❌ 网络连通性测试失败，请检查:")
        print("1. URL是否正确")
        print("2. 服务器是否运行")
        print("3. 防火墙设置")
        return False
    
    # 步骤2：测试Keystone端点
    if not test_keystone_endpoint(config['auth_url']):
        print("\n❌ Keystone端点测试失败，请检查:")
        print("1. URL路径是否正确 (应该以/v3结尾)")
        print("2. Keystone服务是否正常运行")
        return False
    
    # 步骤3：测试认证
    sess = test_authentication(**config)
    if not sess:
        print("\n❌ 认证测试失败，请检查:")
        print("1. 用户名和密码是否正确")
        print("2. 项目名是否存在且用户有权限")
        print("3. 用户域和项目域设置")
        return False
    
    # 步骤4：测试服务端点
    clients = test_service_endpoints(sess)
    if not clients:
        print("\n❌ 服务端点测试失败，请检查:")
        print("1. Nova/Cinder服务是否正常")
        print("2. 用户是否有相应的服务权限")
        return False
    
    print("\n🎉 所有测试通过！")
    print("✅ 该配置可以在Web界面中正常使用")
    
    # 额外测试：尝试获取资源
    print("\n📊 资源获取测试:")
    try:
        instances = clients['nova'].servers.list()
        volumes = clients['cinder'].volumes.list()
        print(f"✅ 实例数量: {len(instances)}")
        print(f"✅ 卷数量: {len(volumes)}")
        
        if len(instances) == 0 and len(volumes) == 0:
            print("📝 注意: 集群中没有资源，这可能是正常的")
    except Exception as e:
        print(f"⚠️ 资源获取异常: {e}")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n💡 建议: 现在可以在Web界面添加此集群")
        else:
            print("\n💡 建议: 请根据上述提示解决问题后重试")
    except KeyboardInterrupt:
        print("\n\n👋 测试中断")
    except Exception as e:
        print(f"\n❌ 测试脚本执行出错: {e}")