#!/usr/bin/env python3
"""
测试到期检查功能
"""
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from app import create_app
from app.models.cluster import OpenstackCluster
from app.services.openstack_service import openstack_service

def test_expire_check():
    """测试到期检查API"""
    print("测试到期检查功能")
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
            
            print("+ 成功获取Nova客户端")
            
            # 获取实例列表
            print("\n>> 检查实例销毁时间设置...")
            servers = nova_client.servers.list(detailed=True)
            
            print(f"+ 找到 {len(servers)} 个实例")
            
            current_time = datetime.utcnow()
            expired_count = 0
            warning_count = 0
            normal_count = 0
            
            for server in servers:
                metadata = getattr(server, 'metadata', {})
                if 'destroy_at' in metadata:
                    try:
                        destroy_time = datetime.fromisoformat(metadata['destroy_at'].replace('Z', '+00:00'))
                        if destroy_time.tzinfo:
                            destroy_time = destroy_time.replace(tzinfo=None)
                        
                        time_diff = destroy_time - current_time
                        
                        if current_time >= destroy_time:
                            expired_count += 1
                            print(f"[EXPIRED] 已到期: {server.name} - 到期时间: {destroy_time}")
                        elif time_diff.total_seconds() <= 86400:  # 24小时内
                            warning_count += 1
                            hours_left = int(time_diff.total_seconds() / 3600)
                            print(f"[WARNING] 即将到期: {server.name} - 剩余: {hours_left} 小时")
                        else:
                            normal_count += 1
                            days_left = int(time_diff.total_seconds() / 86400)
                            print(f"[NORMAL] 正常: {server.name} - 剩余: {days_left} 天")
                    except Exception as e:
                        print(f"[ERROR] 时间格式错误: {server.name} - {e}")
                else:
                    normal_count += 1
                    print(f"[NONE] 未设置: {server.name} - 无销毁时间")
            
            print(f"\n>> 统计结果:")
            print(f"   [EXPIRED] 已到期: {expired_count}")
            print(f"   [WARNING] 即将到期 (24h内): {warning_count}")
            print(f"   [NORMAL] 正常/未设置: {normal_count}")
            
            # 测试一个实例设置近期到期时间
            if servers:
                test_server = servers[0]
                print(f"\n>> 测试设置实例到期时间...")
                print(f"   实例: {test_server.name}")
                
                # 设置1小时后到期
                expire_time = current_time + timedelta(hours=1)
                metadata = getattr(test_server, 'metadata', {}) or {}
                metadata['destroy_at'] = expire_time.isoformat()
                metadata['destroy_set_by'] = 'test_script'
                metadata['destroy_set_at'] = current_time.isoformat()
                
                nova_client.servers.set_meta(test_server.id, metadata)
                print(f"+ 已设置实例 {test_server.name} 在 {expire_time} 到期")
                print("   请刷新前端页面查看警告效果")
            
            print(f"\n+ 到期检查测试完成")
            
        except Exception as e:
            print(f"X 测试失败: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    test_expire_check()