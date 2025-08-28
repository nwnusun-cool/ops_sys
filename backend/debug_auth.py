#!/usr/bin/env python3
"""
调试OpenStack认证问题
"""
import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from keystoneauth1 import session
from keystoneauth1.identity import v3
from novaclient import client as nova_client

def debug_auth():
    print("OpenStack认证调试")
    print("=" * 50)
    
    # 你提供的认证信息
    auth_config = {
        'auth_url': 'http://192.168.2.202:5000/v3',
        'username': 'admin',
        'password': 'HbisDT@12345',
        'project_name': 'admin',
        'user_domain_name': 'Default',
        'project_domain_name': 'Default'
    }
    
    print("测试配置:")
    for key, value in auth_config.items():
        if key == 'password':
            print(f"  {key}: {'*' * len(value)}")
        else:
            print(f"  {key}: {value}")
    print()
    
    try:
        print("1. 创建认证对象...")
        auth = v3.Password(**auth_config)
        print("+ 认证对象创建成功")
        
        print("2. 创建会话...")
        sess = session.Session(auth=auth)
        print("+ 会话创建成功")
        
        print("3. 获取认证token...")
        token = sess.get_token()
        print(f"+ Token获取成功: {token[:20]}...")
        
        print("4. 测试Nova客户端...")
        nova = nova_client.Client(2, session=sess, region_name='RegionOne')
        services = nova.services.list()
        print(f"+ Nova服务列表获取成功，发现 {len(services)} 个服务")
        
        for service in services[:3]:  # 显示前3个服务
            print(f"  - {service.binary} on {service.host} ({service.state})")
        
        print("5. 测试获取实例列表...")
        servers = nova.servers.list()
        print(f"+ 实例列表获取成功，发现 {len(servers)} 个实例")
        
        print("\n" + "=" * 50)
        print("+ 认证测试完全成功！")
        return True
        
    except Exception as e:
        print(f"\nX 认证失败: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        # 详细错误分析
        error_str = str(e).lower()
        if 'unauthorized' in error_str or '401' in error_str:
            print("\n可能的原因:")
            print("1. 用户名或密码错误")
            print("2. 用户被禁用或过期")
            print("3. 项目名称错误或用户无权限访问该项目")
            print("4. 域名配置错误")
        elif 'connection' in error_str:
            print("\n可能的原因:")
            print("1. Keystone服务不可达")
            print("2. 网络连接问题")
            print("3. 端口被防火墙阻挡")
        elif 'timeout' in error_str:
            print("\n可能的原因:")
            print("1. 网络延迟过高")
            print("2. Keystone服务响应慢")
        
        return False

if __name__ == '__main__':
    debug_auth()