"""
OpenStack服务层
重构后的OpenStack管理服务，修复原有代码问题
"""
import logging
from datetime import datetime, timedelta
import pytz
import re
import pandas as pd
import io
import os
import tempfile
from typing import Dict, List, Any, Optional
from keystoneauth1.identity import v3
from keystoneauth1 import session
from novaclient import client as nova_client
from cinderclient import client as cinder_client
from neutronclient.v2_0 import client as neutron_client
from glanceclient import Client as glance_client
from openstack import exceptions as openstack_exceptions
from flask import current_app
from app.models.cluster import OpenstackCluster

logger = logging.getLogger(__name__)

class CustomBytesIO:
    """
    修复后的CustomBytesIO类，移除重复的__init__方法
    """
    def __init__(self, bytes_io):
        self.bytes_io = bytes_io

    def __getattr__(self, attr):
        return getattr(self.bytes_io, attr)

    def truncate(self, size=None):
        return self.bytes_io.truncate(size=size)

    def seek(self, *args, **kwargs):
        return self.bytes_io.seek(*args, **kwargs)

    def write(self, *args, **kwargs):
        return self.bytes_io.write(*args, **kwargs)

    def close(self):
        return self.bytes_io.close()

    def tell(self):
        return self.bytes_io.tell()

    def flush(self):
        if hasattr(self.bytes_io, 'flush'):
            return self.bytes_io.flush()

    @property
    def mode(self):
        return getattr(self.bytes_io, 'mode', 'wb')

    def seekable(self):
        return True

class OpenstackService:
    """
    重构后的OpenStack服务类
    """
    
    def __init__(self):
        self.sessions = {}
        self.nova_clients = {}
        self.cinder_clients = {}
        self.neutron_clients = {}
        self.glance_clients = {}
        self.instance_cache = {}
        self.volume_cache = {}
        self.cache_timeout = timedelta(seconds=300)  # 默认5分钟
        self.last_cache_update = {}
        
    def initialize_config(self):
        """在应用上下文中初始化配置"""
        if current_app:
            self.cache_timeout = timedelta(seconds=current_app.config.get('CACHE_TIMEOUT', 300))
    
    def get_cluster_clients(self, cluster_id: int):
        """获取指定集群的客户端"""
        cluster = OpenstackCluster.query.get(cluster_id)
        if not cluster or not cluster.is_active:
            raise ValueError(f"Cluster {cluster_id} not found or inactive")
        
        cluster_key = f"cluster_{cluster_id}"
        
        # 如果客户端不存在，创建新的
        if cluster_key not in self.sessions:
            self._create_cluster_clients(cluster, cluster_key)
        
        return {
            'nova': self.nova_clients.get(cluster_key),
            'cinder': self.cinder_clients.get(cluster_key),
            'neutron': self.neutron_clients.get(cluster_key),
            'glance': self.glance_clients.get(cluster_key),
            'session': self.sessions.get(cluster_key)
        }
    
    def _create_cluster_clients(self, cluster: OpenstackCluster, cluster_key: str):
        """为指定集群创建OpenStack客户端"""
        try:
            auth_config = cluster.get_auth_config()
            
            # 调试：记录认证配置（隐藏密码）
            debug_config = auth_config.copy()
            if 'password' in debug_config:
                debug_config['password'] = '*' * len(debug_config['password'])
            logger.info(f"Creating auth for cluster {cluster.name} with config: {debug_config}")
            
            auth = v3.Password(**auth_config)
            
            self.sessions[cluster_key] = session.Session(auth=auth)
            self.nova_clients[cluster_key] = nova_client.Client(
                2, session=self.sessions[cluster_key], region_name=cluster.region_name
            )
            self.cinder_clients[cluster_key] = cinder_client.Client(
                3, session=self.sessions[cluster_key], region_name=cluster.region_name
            )
            self.neutron_clients[cluster_key] = neutron_client.Client(
                session=self.sessions[cluster_key], region_name=cluster.region_name
            )
            self.glance_clients[cluster_key] = glance_client(
                2, session=self.sessions[cluster_key], region_name=cluster.region_name
            )
            
            logger.info(f"✓ Cluster {cluster.name} clients created successfully")
            
        except Exception as e:
            error_msg = f"✗ Failed to create clients for cluster {cluster.name}: {str(e)}"
            logger.error(error_msg)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Auth URL: {cluster.auth_url}")
            raise Exception(f"Failed to connect to OpenStack cluster: {str(e)}")
    
    def test_cluster_connection(self, cluster_id: int) -> Dict[str, Any]:
        """测试集群连接"""
        try:
            logger.info(f"Testing connection for cluster {cluster_id}")
            
            # 清除缓存，强制重新创建客户端
            self.clear_cache(cluster_id)
            
            clients = self.get_cluster_clients(cluster_id)
            nova_client = clients['nova']
            
            # 简单测试：获取服务列表
            logger.info(f"Attempting to get services list for cluster {cluster_id}")
            services = nova_client.services.list()
            
            logger.info(f"Connection test successful for cluster {cluster_id}, found {len(services)} services")
            return {
                'success': True,
                'message': f'Connection successful, found {len(services)} services',
                'services_count': len(services)
            }
            
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(f"Connection test failed for cluster {cluster_id}: {error_msg}")
            logger.error(f"Error type: {error_type}")
            
            # 提供更友好的错误信息
            friendly_error = self._get_friendly_error_message(e)
            
            return {
                'success': False,
                'error': friendly_error,
                'technical_error': error_msg,
                'error_type': error_type
            }
    
    def _get_friendly_error_message(self, exception) -> str:
        """将技术错误转换为用户友好的错误信息"""
        error_str = str(exception).lower()
        error_type = type(exception).__name__
        
        if 'unauthorized' in error_str or '401' in error_str:
            return "认证失败：用户名或密码错误"
        elif 'not found' in error_str or '404' in error_str:
            return "服务端点不存在：请检查URL和服务配置"
        elif 'connection' in error_str or 'network' in error_str:
            return "网络连接失败：请检查网络连通性和防火墙设置"
        elif 'timeout' in error_str:
            return "连接超时：请检查网络状况和服务器响应"
        elif 'forbidden' in error_str or '403' in error_str:
            return "权限不足：用户没有足够的权限访问服务"
        elif 'service unavailable' in error_str or '503' in error_str:
            return "服务不可用：OpenStack服务可能暂时不可用"
        else:
            return f"连接失败：{str(exception)}"
    
    def _get_cached_instances(self, cluster_id: int) -> List[Dict]:
        """获取缓存的实例数据"""
        cache_key = f"instances_{cluster_id}"
        current_time = datetime.now()
        
        if (cache_key not in self.instance_cache or 
            current_time - self.last_cache_update.get(cache_key, datetime.min) > self.cache_timeout):
            
            self.instance_cache[cache_key] = self._fetch_instances(cluster_id)
            self.last_cache_update[cache_key] = current_time
        
        return self.instance_cache[cache_key]
    
    def _fetch_instances(self, cluster_id: int) -> List[Dict]:
        """从OpenStack获取实例数据"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            nova_client = clients['nova']
            
            instances = nova_client.servers.list(detailed=True)
            return [self._format_instance_data(instance, cluster_id) for instance in instances]
            
        except Exception as e:
            logger.error(f"Failed to fetch instances for cluster {cluster_id}: {str(e)}")
            return []
    
    def _format_instance_data(self, instance, cluster_id: int) -> Dict:
        """格式化实例数据"""
        cluster = OpenstackCluster.query.get(cluster_id)
        
        # 处理网络信息
        networks = instance.addresses
        ip_addresses = []
        for network_name, addresses in networks.items():
            for addr in addresses:
                ip_type = "float" if addr.get("OS-EXT-IPS:type") == "floating" else "fixed"
                ip_addresses.append(f"{addr['addr']}({ip_type})")
        
        # 获取规格信息
        flavor = self._get_flavor_info(instance, cluster_id)
        
        return {
            "cluster_id": cluster_id,
            "cluster_name": cluster.name if cluster else "Unknown",
            "name": self.clean_string(instance.name),
            "id": instance.id,
            "status": instance.status,
            "ip_addresses": ", ".join(ip_addresses) if ip_addresses else "N/A",
            "flavor": self.clean_string(flavor),
            "created": self._format_datetime(instance.created),
            "updated": self._format_datetime(instance.updated),
            "metadata": instance.metadata,
            "security_groups": [sg["name"] for sg in instance.security_groups],
            "power_state": self._get_power_state(instance),
        }
    
    def _get_flavor_info(self, instance, cluster_id: int) -> str:
        """获取实例规格信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            nova_client = clients['nova']
            
            flavor_id = instance.flavor["id"]
            flavor = nova_client.flavors.get(flavor_id)
            return f"{flavor.name} ({flavor.vcpus}vCPU, {flavor.ram}MB RAM, {flavor.disk}GB Disk)"
            
        except Exception as e:
            logger.warning(f"Failed to get flavor info: {str(e)}")
            return "Unknown"
    
    def _format_datetime(self, dt_str: str) -> str:
        """格式化日期时间为本地时间"""
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M:%SZ")
            local_tz = pytz.timezone("Asia/Shanghai")
            dt = pytz.utc.localize(dt).astimezone(local_tz)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return dt_str
    
    def _get_power_state(self, instance) -> str:
        """获取实例电源状态"""
        power_states = {
            0: "NOSTATE",
            1: "RUNNING",
            3: "PAUSED", 
            4: "SHUTDOWN",
            6: "CRASHED",
            7: "SUSPENDED",
        }
        return power_states.get(
            getattr(instance, "OS-EXT-STS:power_state", 0), "UNKNOWN"
        )
    
    def clean_string(self, value) -> str:
        """清理字符串，确保中文字符正确显示"""
        if isinstance(value, str):
            ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
            value = ansi_escape.sub("", value)
            try:
                value = value.encode("latin1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return value
    
    def search_instances(self, cluster_id: int, filters: Optional[Dict] = None) -> Dict:
        """搜索实例"""
        try:
            instances = self._get_cached_instances(cluster_id)
            filtered_instances = self._apply_filters(instances, filters)
            
            # 排序
            if filters and "sort_by" in filters:
                reverse = filters.get("sort_order", "desc").lower() == "desc"
                filtered_instances.sort(
                    key=lambda x: str(x.get(filters["sort_by"], "")), reverse=reverse
                )
            
            # 分页
            page = int(filters.get("page", 1)) if filters else 1
            per_page = int(filters.get("per_page", 10)) if filters else 10
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                "total": len(filtered_instances),
                "page": page,
                "per_page": per_page,
                "total_pages": (len(filtered_instances) + per_page - 1) // per_page,
                "data": filtered_instances[start_idx:end_idx],
            }
            
        except Exception as e:
            logger.error(f"Failed to search instances: {str(e)}")
            raise
    
    def _apply_filters(self, instances: List[Dict], filters: Optional[Dict]) -> List[Dict]:
        """应用过滤条件"""
        if not filters:
            return instances
        
        filtered = instances
        
        # 状态过滤
        if "status" in filters and filters["status"]:
            filtered = [i for i in filtered 
                       if i["status"] and i["status"].upper() == filters["status"].upper()]
        
        # 实例类型过滤
        if "instance_type" in filters and filters["instance_type"]:
            filtered = [i for i in filtered 
                       if i["flavor"] and filters["instance_type"].lower() in i["flavor"].lower()]
        
        # IP地址过滤
        if "ip" in filters and filters["ip"]:
            filtered = [i for i in filtered 
                       if i["ip_addresses"] and filters["ip"] in i["ip_addresses"]]
        
        # 名称搜索
        if "name" in filters and filters["name"]:
            filtered = [i for i in filtered 
                       if i["name"] and filters["name"].lower() in i["name"].lower()]
        
        return filtered
    
    def perform_instance_action(self, cluster_id: int, instance_id: str, action: str) -> str:
        """执行实例操作"""
        actions = {
            "start": ("启动", lambda i: i.start()),
            "stop": ("停止", lambda i: i.stop()),
            "reboot": ("重启", lambda i: i.reboot(reboot_type="SOFT")),
            "hard_reboot": ("强制重启", lambda i: i.reboot(reboot_type="HARD")),
            "pause": ("暂停", lambda i: i.pause()),
            "unpause": ("恢复", lambda i: i.unpause()),
            "delete": ("删除", lambda i: i.delete()),
        }
        
        if action not in actions:
            raise ValueError(f"Unsupported action: {action}")
        
        try:
            clients = self.get_cluster_clients(cluster_id)
            nova_client = clients['nova']
            
            instance = nova_client.servers.get(instance_id)
            action_name, action_func = actions[action]
            
            logger.info(f"Performing {action_name} on instance {instance.name}")
            action_func(instance)
            
            # 清除缓存
            cache_key = f"instances_{cluster_id}"
            if cache_key in self.instance_cache:
                del self.instance_cache[cache_key]
            
            return f"实例{action_name}操作已执行"
            
        except Exception as e:
            logger.error(f"Failed to perform action: {str(e)}")
            raise
    
    def clear_cache(self, cluster_id: Optional[int] = None):
        """清除缓存"""
        if cluster_id:
            cache_keys = [k for k in self.instance_cache.keys() if k.endswith(f"_{cluster_id}")]
            for key in cache_keys:
                if key in self.instance_cache:
                    del self.instance_cache[key]
                if key in self.last_cache_update:
                    del self.last_cache_update[key]
        else:
            self.instance_cache.clear()
            self.volume_cache.clear()
            self.last_cache_update.clear()
    
    def list_volumes(self, cluster_id: int, status: str = None, search: str = None, volume_type: str = None) -> List[Dict]:
        """获取卷列表"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            
            # 获取卷列表
            volumes = cinder_client.volumes.list(detailed=True)
            
            # 转换为字典格式
            volumes_data = []
            for volume in volumes:
                # 获取挂载信息
                attachments = []
                for attachment in getattr(volume, 'attachments', []):
                    attachments.append({
                        'server_id': attachment.get('server_id'),
                        'device': attachment.get('device'),
                        'attached_at': attachment.get('attached_at')
                    })
                
                volume_data = {
                    'id': volume.id,
                    'name': volume.name or volume.id,
                    'description': getattr(volume, 'description', ''),
                    'status': volume.status,
                    'size': volume.size,
                    'volume_type': getattr(volume, 'volume_type', 'Unknown'),
                    'created_at': volume.created_at,
                    'updated_at': getattr(volume, 'updated_at', None),
                    'availability_zone': getattr(volume, 'availability_zone', None),
                    'bootable': getattr(volume, 'bootable', False),
                    'encrypted': getattr(volume, 'encrypted', False),
                    'attachments': attachments,
                    'metadata': getattr(volume, 'metadata', {}),
                    'snapshot_id': getattr(volume, 'snapshot_id', None),
                    'source_volid': getattr(volume, 'source_volid', None)
                }
                
                # 应用过滤器
                if status and volume_data['status'].lower() != status.lower():
                    continue
                if search and search.lower() not in volume_data['name'].lower() and search.lower() not in volume_data['id']:
                    continue
                if volume_type and volume_type.lower() not in volume_data['volume_type'].lower():
                    continue
                
                volumes_data.append(volume_data)
            
            return volumes_data
            
        except Exception as e:
            logger.error(f"Failed to list volumes for cluster {cluster_id}: {str(e)}")
            return []
    
    def get_volume_detail(self, cluster_id: int, volume_id: str) -> Optional[Dict]:
        """获取卷详细信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            
            volume = cinder_client.volumes.get(volume_id)
            
            # 获取挂载信息
            attachments = []
            for attachment in getattr(volume, 'attachments', []):
                attachments.append({
                    'server_id': attachment.get('server_id'),
                    'device': attachment.get('device'),
                    'attached_at': attachment.get('attached_at')
                })
            
            return {
                'id': volume.id,
                'name': volume.name or volume.id,
                'description': getattr(volume, 'description', ''),
                'status': volume.status,
                'size': volume.size,
                'volume_type': getattr(volume, 'volume_type', 'Unknown'),
                'created_at': volume.created_at,
                'updated_at': getattr(volume, 'updated_at', None),
                'availability_zone': getattr(volume, 'availability_zone', None),
                'bootable': getattr(volume, 'bootable', False),
                'encrypted': getattr(volume, 'encrypted', False),
                'attachments': attachments,
                'metadata': getattr(volume, 'metadata', {}),
                'snapshot_id': getattr(volume, 'snapshot_id', None),
                'source_volid': getattr(volume, 'source_volid', None)
            }
            
        except Exception as e:
            logger.error(f"Failed to get volume detail {volume_id} for cluster {cluster_id}: {str(e)}")
            return None
    
    def delete_volume(self, cluster_id: int, volume_id: str) -> bool:
        """删除卷"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            
            cinder_client.volumes.delete(volume_id)
            logger.info(f"Successfully initiated delete for volume {volume_id} in cluster {cluster_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete volume {volume_id} in cluster {cluster_id}: {str(e)}")
            return False
    
    def detach_all_volume(self, cluster_id: int, volume_id: str) -> bool:
        """卸载卷的所有挂载"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            nova_client = clients['nova']
            
            # 获取卷信息
            volume = cinder_client.volumes.get(volume_id)
            
            # 卸载所有挂载点
            success = True
            for attachment in getattr(volume, 'attachments', []):
                try:
                    instance_id = attachment.get('server_id')
                    if instance_id:
                        nova_client.volumes.delete_server_volume(instance_id, volume_id)
                        logger.info(f"Successfully initiated detach for volume {volume_id} from instance {instance_id}")
                except Exception as e:
                    logger.error(f"Failed to detach volume {volume_id} from instance {instance_id}: {str(e)}")
                    success = False
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to detach volume {volume_id} in cluster {cluster_id}: {str(e)}")
            return False
    
    def list_networks(self, cluster_id: int, status: str = None, search: str = None, network_type: str = None) -> List[Dict]:
        """获取网络列表"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            neutron_client = clients['neutron']
            
            # 获取网络列表
            networks = neutron_client.list_networks()['networks']
            
            # 转换为字典格式
            networks_data = []
            for network in networks:
                # 获取子网信息
                subnets = []
                for subnet_id in network.get('subnets', []):
                    try:
                        subnet = neutron_client.show_subnet(subnet_id)['subnet']
                        subnets.append({
                            'id': subnet['id'],
                            'name': subnet['name'],
                            'cidr': subnet['cidr'],
                            'gateway_ip': subnet.get('gateway_ip'),
                            'ip_version': subnet['ip_version'],
                            'enable_dhcp': subnet.get('enable_dhcp', False)
                        })
                    except Exception as e:
                        logger.warning(f"Failed to get subnet {subnet_id}: {e}")
                        continue
                
                network_data = {
                    'id': network['id'],
                    'name': network['name'],
                    'description': network.get('description', ''),
                    'status': network['status'],
                    'admin_state_up': network.get('admin_state_up', True),
                    'shared': network.get('shared', False),
                    'external': network.get('router:external', False),
                    'provider_network_type': network.get('provider:network_type'),
                    'provider_physical_network': network.get('provider:physical_network'),
                    'provider_segmentation_id': network.get('provider:segmentation_id'),
                    'mtu': network.get('mtu', 1500),
                    'port_security_enabled': network.get('port_security_enabled', True),
                    'tenant_id': network.get('tenant_id'),
                    'project_id': network.get('project_id'),
                    'created_at': network.get('created_at'),
                    'updated_at': network.get('updated_at'),
                    'subnets': subnets,
                    'subnets_count': len(subnets)
                }
                
                # 应用过滤器
                if status and network_data['status'].lower() != status.lower():
                    continue
                if search and search.lower() not in network_data['name'].lower() and search.lower() not in network_data['id']:
                    continue
                if network_type:
                    if network_type == 'external' and not network_data['external']:
                        continue
                    elif network_type == 'internal' and network_data['external']:
                        continue
                
                networks_data.append(network_data)
            
            return networks_data
            
        except Exception as e:
            logger.error(f"Failed to list networks for cluster {cluster_id}: {str(e)}")
            return []
    
    def get_network_detail(self, cluster_id: int, network_id: str) -> Optional[Dict]:
        """获取网络详细信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            neutron_client = clients['neutron']
            
            network = neutron_client.show_network(network_id)['network']
            
            # 获取子网详情
            subnets = []
            for subnet_id in network.get('subnets', []):
                try:
                    subnet = neutron_client.show_subnet(subnet_id)['subnet']
                    subnets.append({
                        'id': subnet['id'],
                        'name': subnet['name'],
                        'cidr': subnet['cidr'],
                        'gateway_ip': subnet.get('gateway_ip'),
                        'ip_version': subnet['ip_version'],
                        'enable_dhcp': subnet.get('enable_dhcp', False),
                        'allocation_pools': subnet.get('allocation_pools', []),
                        'dns_nameservers': subnet.get('dns_nameservers', []),
                        'host_routes': subnet.get('host_routes', []),
                        'created_at': subnet.get('created_at'),
                        'updated_at': subnet.get('updated_at')
                    })
                except Exception as e:
                    logger.warning(f"Failed to get subnet {subnet_id}: {e}")
                    continue
            
            # 获取端口信息
            try:
                ports = neutron_client.list_ports(network_id=network_id)['ports']
                port_count = len(ports)
            except Exception as e:
                logger.warning(f"Failed to get ports for network {network_id}: {e}")
                port_count = 0
            
            return {
                'id': network['id'],
                'name': network['name'],
                'description': network.get('description', ''),
                'status': network['status'],
                'admin_state_up': network.get('admin_state_up', True),
                'shared': network.get('shared', False),
                'external': network.get('router:external', False),
                'provider_network_type': network.get('provider:network_type'),
                'provider_physical_network': network.get('provider:physical_network'),
                'provider_segmentation_id': network.get('provider:segmentation_id'),
                'mtu': network.get('mtu', 1500),
                'port_security_enabled': network.get('port_security_enabled', True),
                'tenant_id': network.get('tenant_id'),
                'project_id': network.get('project_id'),
                'created_at': network.get('created_at'),
                'updated_at': network.get('updated_at'),
                'availability_zones': network.get('availability_zones', []),
                'availability_zone_hints': network.get('availability_zone_hints', []),
                'subnets': subnets,
                'port_count': port_count
            }
            
        except Exception as e:
            logger.error(f"Failed to get network detail {network_id} for cluster {cluster_id}: {str(e)}")
            return None
    
    def delete_network(self, cluster_id: int, network_id: str) -> bool:
        """删除网络"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            neutron_client = clients['neutron']
            
            neutron_client.delete_network(network_id)
            logger.info(f"Successfully initiated delete for network {network_id} in cluster {cluster_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete network {network_id} in cluster {cluster_id}: {str(e)}")
            return False
    
    def update_network_admin_state(self, cluster_id: int, network_id: str, admin_state_up: bool) -> bool:
        """更新网络管理状态"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            neutron_client = clients['neutron']
            
            neutron_client.update_network(network_id, {'network': {'admin_state_up': admin_state_up}})
            logger.info(f"Successfully updated admin state for network {network_id} in cluster {cluster_id} to {admin_state_up}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update network admin state {network_id} in cluster {cluster_id}: {str(e)}")
            return False
    
    def get_network_topology(self, cluster_id: int) -> Dict[str, Any]:
        """获取网络拓扑数据"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            neutron_client = clients['neutron']
            nova_client = clients['nova']
            
            # 获取网络数据
            networks = neutron_client.list_networks()['networks']
            routers = neutron_client.list_routers()['routers']
            ports = neutron_client.list_ports()['ports']
            subnets = neutron_client.list_subnets()['subnets']
            
            # 获取实例数据
            instances = nova_client.servers.list(detailed=True)
            
            # 构建拓扑数据结构
            topology = {
                'nodes': [],
                'edges': [],
                'statistics': {
                    'networks_count': len(networks),
                    'routers_count': len(routers),
                    'instances_count': len(instances),
                    'subnets_count': len(subnets)
                }
            }
            
            # 添加网络节点
            for network in networks:
                topology['nodes'].append({
                    'id': f"network_{network['id']}",
                    'type': 'network',
                    'name': network['name'],
                    'data': {
                        'id': network['id'],
                        'status': network['status'],
                        'admin_state_up': network.get('admin_state_up', True),
                        'shared': network.get('shared', False),
                        'external': network.get('router:external', False),
                        'subnets': network.get('subnets', [])
                    }
                })
            
            # 添加路由节点
            for router in routers:
                topology['nodes'].append({
                    'id': f"router_{router['id']}",
                    'type': 'router',
                    'name': router['name'],
                    'data': {
                        'id': router['id'],
                        'status': router['status'],
                        'admin_state_up': router.get('admin_state_up', True),
                        'external_gateway_info': router.get('external_gateway_info')
                    }
                })
            
            # 添加实例节点
            for instance in instances:
                topology['nodes'].append({
                    'id': f"instance_{instance.id}",
                    'type': 'instance',
                    'name': instance.name,
                    'data': {
                        'id': instance.id,
                        'status': instance.status,
                        'addresses': instance.addresses
                    }
                })
            
            # 建立连接关系
            # 路由器到网络的连接
            for port in ports:
                device_owner = port.get('device_owner', '')
                device_id = port.get('device_id', '')
                network_id = port.get('network_id', '')
                
                if device_owner == 'network:router_interface' and device_id and network_id:
                    topology['edges'].append({
                        'source': f"router_{device_id}",
                        'target': f"network_{network_id}",
                        'type': 'router_interface',
                        'data': {
                            'port_id': port['id'],
                            'ip_address': port.get('fixed_ips', [{}])[0].get('ip_address') if port.get('fixed_ips') else None
                        }
                    })
                elif device_owner == 'compute:nova' and device_id and network_id:
                    # 实例到网络的连接
                    topology['edges'].append({
                        'source': f"instance_{device_id}",
                        'target': f"network_{network_id}",
                        'type': 'instance_interface',
                        'data': {
                            'port_id': port['id'],
                            'ip_address': port.get('fixed_ips', [{}])[0].get('ip_address') if port.get('fixed_ips') else None
                        }
                    })
            
            return topology
            
        except Exception as e:
            logger.error(f"Failed to get network topology for cluster {cluster_id}: {str(e)}")
            return {
                'nodes': [],
                'edges': [],
                'statistics': {
                    'networks_count': 0,
                    'routers_count': 0,
                    'instances_count': 0,
                    'subnets_count': 0
                }
            }
    
    def get_router_detail(self, cluster_id: int, router_id: str) -> Optional[Dict]:
        """获取路由器详细信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            neutron_client = clients['neutron']
            
            router = neutron_client.show_router(router_id)['router']
            
            # 获取路由器端口
            ports = neutron_client.list_ports(device_id=router_id)['ports']
            
            return {
                'id': router['id'],
                'name': router['name'],
                'description': router.get('description', ''),
                'status': router['status'],
                'admin_state_up': router.get('admin_state_up', True),
                'external_gateway_info': router.get('external_gateway_info'),
                'routes': router.get('routes', []),
                'ports': ports,
                'created_at': router.get('created_at'),
                'updated_at': router.get('updated_at'),
                'tenant_id': router.get('tenant_id'),
                'project_id': router.get('project_id')
            }
            
        except Exception as e:
            logger.error(f"Failed to get router detail {router_id} for cluster {cluster_id}: {str(e)}")
            return None
    
    def get_instance_detail(self, cluster_id: int, instance_id: str) -> Optional[Dict]:
        """获取实例详细信息（用于拓扑）"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            nova_client = clients['nova']
            
            instance = nova_client.servers.get(instance_id)
            
            return {
                'id': instance.id,
                'name': instance.name,
                'status': instance.status,
                'addresses': instance.addresses,
                'flavor': instance.flavor,
                'image': getattr(instance, 'image', {}),
                'created': instance.created,
                'updated': instance.updated,
                'power_state': getattr(instance, 'OS-EXT-STS:power_state', 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get instance detail {instance_id} for cluster {cluster_id}: {str(e)}")
            return None
    
    # 镜像管理方法
    def list_images(self, cluster_id: int, filters: Optional[Dict] = None) -> Dict:
        """获取镜像列表"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            # 获取镜像列表
            images_generator = glance_client.images.list()
            images_data = []
            
            for image in images_generator:
                # 转换为字典格式并应用过滤器
                image_data = self._format_image_data(image, cluster_id)
                
                # 应用过滤器
                if self._apply_image_filters(image_data, filters):
                    images_data.append(image_data)
            
            # 排序
            if filters and filters.get('sort_by'):
                reverse = filters.get('sort_order', 'desc').lower() == 'desc'
                sort_key = filters['sort_by']
                images_data.sort(
                    key=lambda x: str(x.get(sort_key, '')), reverse=reverse
                )
            
            # 分页
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'total': len(images_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(images_data) + per_page - 1) // per_page,
                'data': images_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list images for cluster {cluster_id}: {str(e)}")
            return {
                'total': 0,
                'page': 1,
                'per_page': 20,
                'total_pages': 0,
                'data': []
            }
    
    def _format_image_data(self, image, cluster_id: int) -> Dict:
        """格式化镜像数据"""
        cluster = OpenstackCluster.query.get(cluster_id)
        
        # 计算镜像大小（转换为可读格式）
        size_bytes = getattr(image, 'size', 0) or 0
        size_readable = self._format_bytes(size_bytes)
        
        # 格式化创建和更新时间
        created_at = self._format_datetime(getattr(image, 'created_at', ''))
        updated_at = self._format_datetime(getattr(image, 'updated_at', ''))
        
        # 获取镜像属性
        properties = getattr(image, 'properties', {}) or {}
        
        return {
            'cluster_id': cluster_id,
            'cluster_name': cluster.name if cluster else 'Unknown',
            'id': image.id,
            'name': getattr(image, 'name', '') or image.id,
            'description': properties.get('description', ''),
            'status': getattr(image, 'status', 'unknown'),
            'visibility': getattr(image, 'visibility', 'private'),
            'protected': getattr(image, 'protected', False),
            'disk_format': getattr(image, 'disk_format', 'unknown'),
            'container_format': getattr(image, 'container_format', 'bare'),
            'size': size_bytes,
            'size_readable': size_readable,
            'min_disk': getattr(image, 'min_disk', 0),
            'min_ram': getattr(image, 'min_ram', 0),
            'created_at': created_at,
            'updated_at': updated_at,
            'owner': getattr(image, 'owner', ''),
            'checksum': getattr(image, 'checksum', ''),
            'tags': list(getattr(image, 'tags', [])),
            'properties': properties,
            'virtual_size': getattr(image, 'virtual_size', 0),
            'is_public': getattr(image, 'visibility', 'private') == 'public'
        }
    
    def _format_bytes(self, bytes_value: int) -> str:
        """格式化字节数为可读格式"""
        if bytes_value == 0:
            return "0 B"
        
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        size = float(bytes_value)
        unit_index = 0
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        else:
            return f"{size:.2f} {units[unit_index]}"
    
    def _apply_image_filters(self, image_data: Dict, filters: Optional[Dict]) -> bool:
        """应用镜像过滤条件"""
        if not filters:
            return True
        
        # 状态过滤
        if filters.get('status') and image_data['status'].lower() != filters['status'].lower():
            return False
        
        # 可见性过滤
        if filters.get('visibility') and image_data['visibility'].lower() != filters['visibility'].lower():
            return False
        
        # 公开性过滤
        if filters.get('is_public'):
            is_public_filter = filters['is_public'].lower() == 'true'
            if image_data['is_public'] != is_public_filter:
                return False
        
        # 磁盘格式过滤
        if filters.get('container_format') and image_data['container_format'].lower() != filters['container_format'].lower():
            return False
        
        # 容器格式过滤
        if filters.get('disk_format') and image_data['disk_format'].lower() != filters['disk_format'].lower():
            return False
        
        # 最小磁盘过滤
        if filters.get('min_disk') is not None and image_data['min_disk'] < filters['min_disk']:
            return False
        
        # 最小内存过滤
        if filters.get('min_ram') is not None and image_data['min_ram'] < filters['min_ram']:
            return False
        
        # 名称搜索
        if filters.get('name'):
            search_term = filters['name'].lower()
            if (search_term not in image_data['name'].lower() and 
                search_term not in image_data['id'].lower() and
                search_term not in image_data.get('description', '').lower()):
                return False
        
        return True
    
    def get_image_detail(self, cluster_id: int, image_id: str) -> Optional[Dict]:
        """获取镜像详细信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            image = glance_client.images.get(image_id)
            
            return self._format_image_data(image, cluster_id)
            
        except Exception as e:
            logger.error(f"Failed to get image detail {image_id} for cluster {cluster_id}: {str(e)}")
            return None
    
    def create_image_from_url(self, cluster_id: int, image_data: Dict, image_url: str) -> Dict:
        """从URL创建镜像"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            # 创建镜像对象
            image = glance_client.images.create(
                name=image_data['name'],
                disk_format=image_data['disk_format'],
                container_format=image_data['container_format'],
                visibility=image_data['visibility'],
                min_disk=image_data['min_disk'],
                min_ram=image_data['min_ram'],
                protected=image_data['protected']
            )
            
            # 设置描述和标签
            if image_data.get('description'):
                glance_client.images.update(image.id, description=image_data['description'])
            
            if image_data.get('tags'):
                for tag in image_data['tags']:
                    if tag.strip():
                        glance_client.images.add_tag(image.id, tag.strip())
            
            # 从URL上传数据
            import requests
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            
            glance_client.images.upload(image.id, response.raw)
            
            logger.info(f"Successfully created image {image.id} from URL for cluster {cluster_id}")
            
            return {
                'success': True,
                'data': self._format_image_data(image, cluster_id)
            }
            
        except Exception as e:
            logger.error(f"Failed to create image from URL for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_image_from_file(self, cluster_id: int, image_data: Dict, file_path: str) -> Dict:
        """从文件创建镜像"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            # 创建镜像对象
            image = glance_client.images.create(
                name=image_data['name'],
                disk_format=image_data['disk_format'],
                container_format=image_data['container_format'],
                visibility=image_data['visibility'],
                min_disk=image_data['min_disk'],
                min_ram=image_data['min_ram'],
                protected=image_data['protected']
            )
            
            # 设置描述和标签
            if image_data.get('description'):
                glance_client.images.update(image.id, description=image_data['description'])
            
            if image_data.get('tags'):
                for tag in image_data['tags']:
                    if tag.strip():
                        glance_client.images.add_tag(image.id, tag.strip())
            
            # 从文件上传数据
            with open(file_path, 'rb') as f:
                glance_client.images.upload(image.id, f)
            
            logger.info(f"Successfully created image {image.id} from file for cluster {cluster_id}")
            
            return {
                'success': True,
                'data': self._format_image_data(image, cluster_id)
            }
            
        except Exception as e:
            logger.error(f"Failed to create image from file for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_image(self, cluster_id: int, image_id: str, update_data: Dict) -> bool:
        """更新镜像属性"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            # 准备更新数据
            update_fields = {}
            for field in ['name', 'description', 'visibility', 'min_disk', 'min_ram', 'protected']:
                if field in update_data:
                    update_fields[field] = update_data[field]
            
            # 更新镜像属性
            if update_fields:
                glance_client.images.update(image_id, **update_fields)
            
            # 处理标签
            if 'tags' in update_data:
                # 获取当前标签
                image = glance_client.images.get(image_id)
                current_tags = set(image.tags)
                new_tags = set(tag.strip() for tag in update_data['tags'] if tag.strip())
                
                # 删除不需要的标签
                for tag in current_tags - new_tags:
                    glance_client.images.remove_tag(image_id, tag)
                
                # 添加新标签
                for tag in new_tags - current_tags:
                    glance_client.images.add_tag(image_id, tag)
            
            logger.info(f"Successfully updated image {image_id} for cluster {cluster_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update image {image_id} for cluster {cluster_id}: {str(e)}")
            return False
    
    def delete_image(self, cluster_id: int, image_id: str) -> bool:
        """删除镜像"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            glance_client.images.delete(image_id)
            
            logger.info(f"Successfully deleted image {image_id} for cluster {cluster_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete image {image_id} for cluster {cluster_id}: {str(e)}")
            return False
    
    def download_image(self, cluster_id: int, image_id: str) -> Dict:
        """下载镜像文件"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            # 获取镜像信息
            image = glance_client.images.get(image_id)
            
            # 创建临时文件
            temp_dir = tempfile.gettempdir()
            filename = f"{image.name or image_id}.{image.disk_format}"
            file_path = os.path.join(temp_dir, filename)
            
            # 下载镜像数据
            with open(file_path, 'wb') as f:
                for chunk in glance_client.images.data(image_id):
                    f.write(chunk)
            
            logger.info(f"Successfully prepared download for image {image_id}")
            
            return {
                'success': True,
                'file_path': file_path,
                'filename': filename
            }
            
        except Exception as e:
            logger.error(f"Failed to download image {image_id} for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_image_statistics(self, cluster_id: int) -> Dict:
        """获取镜像统计信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            glance_client = clients['glance']
            
            # 获取所有镜像
            images = list(glance_client.images.list())
            
            # 统计数据
            total_count = len(images)
            total_size = sum(getattr(image, 'size', 0) or 0 for image in images)
            
            # 按状态分组
            status_counts = {}
            visibility_counts = {}
            format_counts = {}
            
            for image in images:
                status = getattr(image, 'status', 'unknown')
                visibility = getattr(image, 'visibility', 'private')
                disk_format = getattr(image, 'disk_format', 'unknown')
                
                status_counts[status] = status_counts.get(status, 0) + 1
                visibility_counts[visibility] = visibility_counts.get(visibility, 0) + 1
                format_counts[disk_format] = format_counts.get(disk_format, 0) + 1
            
            return {
                'total_count': total_count,
                'total_size': total_size,
                'total_size_readable': self._format_bytes(total_size),
                'active_count': status_counts.get('active', 0),
                'public_count': visibility_counts.get('public', 0),
                'private_count': visibility_counts.get('private', 0),
                'status_distribution': status_counts,
                'visibility_distribution': visibility_counts,
                'format_distribution': format_counts
            }
            
        except Exception as e:
            logger.error(f"Failed to get image statistics for cluster {cluster_id}: {str(e)}")
            return {
                'total_count': 0,
                'total_size': 0,
                'total_size_readable': '0 B',
                'active_count': 0,
                'public_count': 0,
                'private_count': 0,
                'status_distribution': {},
                'visibility_distribution': {},
                'format_distribution': {}
            }
    
    # ============== 快照管理方法 ==============
    
    def list_snapshots(self, cluster_id: int, filters: Optional[Dict] = None) -> Dict:
        """获取快照列表（包括卷快照和实例快照）"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            nova_client = clients['nova']
            glance_client = clients['glance']
            
            snapshots_data = []
            snapshot_type = filters.get('type') if filters else None
            
            # 获取卷快照
            if not snapshot_type or snapshot_type == 'volume':
                try:
                    volume_snapshots = cinder_client.volume_snapshots.list(detailed=True)
                    for snapshot in volume_snapshots:
                        snapshot_data = self._format_volume_snapshot_data(snapshot, cluster_id)
                        if self._apply_snapshot_filters(snapshot_data, filters):
                            snapshots_data.append(snapshot_data)
                except Exception as e:
                    logger.warning(f"Failed to get volume snapshots: {e}")
            
            # 获取实例快照（从镜像中筛选）
            if not snapshot_type or snapshot_type == 'instance':
                try:
                    images = list(glance_client.images.list())
                    for image in images:
                        # 判断是否为实例快照
                        if (hasattr(image, 'instance_uuid') or 
                            getattr(image, 'image_type', None) == 'snapshot' or
                            'snapshot' in getattr(image, 'name', '').lower()):
                            snapshot_data = self._format_instance_snapshot_data(image, cluster_id)
                            if self._apply_snapshot_filters(snapshot_data, filters):
                                snapshots_data.append(snapshot_data)
                except Exception as e:
                    logger.warning(f"Failed to get instance snapshots: {e}")
            
            # 排序
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'desc').lower() == 'desc'
                sort_key = filters['sort_by']
                snapshots_data.sort(
                    key=lambda x: str(x.get(sort_key, '')), reverse=reverse
                )
            
            # 分页
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'total': len(snapshots_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(snapshots_data) + per_page - 1) // per_page,
                'data': snapshots_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list snapshots for cluster {cluster_id}: {str(e)}")
            return {
                'total': 0,
                'page': 1,
                'per_page': 20,
                'total_pages': 0,
                'data': []
            }
    
    def _format_volume_snapshot_data(self, snapshot, cluster_id: int) -> Dict:
        """格式化卷快照数据"""
        cluster = OpenstackCluster.query.get(cluster_id)
        
        # 获取源卷信息
        volume_name = 'Unknown'
        if hasattr(snapshot, 'volume_id') and snapshot.volume_id:
            try:
                clients = self.get_cluster_clients(cluster_id)
                cinder_client = clients['cinder']
                volume = cinder_client.volumes.get(snapshot.volume_id)
                volume_name = volume.name or volume.id
            except:
                volume_name = snapshot.volume_id[:8] + '...'
        
        return {
            'cluster_id': cluster_id,
            'cluster_name': cluster.name if cluster else 'Unknown',
            'id': snapshot.id,
            'name': snapshot.name or snapshot.id,
            'description': getattr(snapshot, 'description', ''),
            'status': snapshot.status,
            'size': snapshot.size,
            'size_readable': self._format_bytes(snapshot.size * 1024 * 1024 * 1024),  # 转换GB到bytes
            'volume_id': getattr(snapshot, 'volume_id', None),
            'volume_name': volume_name,
            'created_at': self._format_datetime(snapshot.created_at),
            'updated_at': self._format_datetime(getattr(snapshot, 'updated_at', None)),
            'progress': getattr(snapshot, 'os-extended-snapshot-attributes:progress', '100%'),
            'project_id': getattr(snapshot, 'os-extended-snapshot-attributes:project_id', None),
            'metadata': getattr(snapshot, 'metadata', {}),
            'type': 'volume'
        }
    
    def _format_instance_snapshot_data(self, image, cluster_id: int) -> Dict:
        """格式化实例快照数据"""
        cluster = OpenstackCluster.query.get(cluster_id)
        
        # 获取实例信息
        instance_name = 'Unknown'
        instance_uuid = getattr(image, 'instance_uuid', None)
        if instance_uuid:
            try:
                clients = self.get_cluster_clients(cluster_id)
                nova_client = clients['nova']
                instance = nova_client.servers.get(instance_uuid)
                instance_name = instance.name
            except:
                instance_name = instance_uuid[:8] + '...'
        
        size_bytes = getattr(image, 'size', 0) or 0
        
        return {
            'cluster_id': cluster_id,
            'cluster_name': cluster.name if cluster else 'Unknown',
            'id': image.id,
            'name': getattr(image, 'name', '') or image.id,
            'description': getattr(image, 'description', ''),
            'status': image.status,
            'size': size_bytes // (1024 * 1024 * 1024) if size_bytes > 0 else 0,  # 转换为GB
            'size_readable': self._format_bytes(size_bytes),
            'instance_id': instance_uuid,
            'instance_name': instance_name,
            'created_at': self._format_datetime(image.created_at),
            'updated_at': self._format_datetime(image.updated_at),
            'disk_format': getattr(image, 'disk_format', 'unknown'),
            'container_format': getattr(image, 'container_format', 'unknown'),
            'visibility': getattr(image, 'visibility', 'private'),
            'min_disk': getattr(image, 'min_disk', 0),
            'min_ram': getattr(image, 'min_ram', 0),
            'checksum': getattr(image, 'checksum', None),
            'type': 'instance'
        }
    
    def _apply_snapshot_filters(self, snapshot_data: Dict, filters: Optional[Dict]) -> bool:
        """应用快照过滤条件"""
        if not filters:
            return True
        
        # 状态过滤
        if 'status' in filters and filters['status']:
            if snapshot_data['status'].lower() != filters['status'].lower():
                return False
        
        # 类型过滤
        if 'type' in filters and filters['type']:
            if snapshot_data['type'] != filters['type']:
                return False
        
        # 搜索过滤
        if 'search' in filters and filters['search']:
            search_term = filters['search'].lower()
            if (search_term not in snapshot_data['name'].lower() and 
                search_term not in snapshot_data['id'].lower()):
                return False
        
        return True
    
    def get_snapshot_detail(self, cluster_id: int, snapshot_id: str, snapshot_type: str = 'volume') -> Optional[Dict]:
        """获取快照详细信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            
            if snapshot_type == 'volume':
                cinder_client = clients['cinder']
                snapshot = cinder_client.volume_snapshots.get(snapshot_id)
                return self._format_volume_snapshot_data(snapshot, cluster_id)
            else:
                glance_client = clients['glance']
                image = glance_client.images.get(snapshot_id)
                return self._format_instance_snapshot_data(image, cluster_id)
                
        except Exception as e:
            logger.error(f"Failed to get snapshot detail {snapshot_id}: {str(e)}")
            return None
    
    def create_volume_snapshot(self, cluster_id: int, volume_id: str, name: str, description: str = '', force: bool = False) -> Dict:
        """创建卷快照"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            
            # 验证卷是否存在
            try:
                volume = cinder_client.volumes.get(volume_id)
            except Exception:
                return {'success': False, 'error': '指定的卷不存在'}
            
            # 创建快照
            snapshot_params = {
                'volume_id': volume_id,
                'name': name,
                'force': force
            }
            
            if description:
                snapshot_params['description'] = description
            
            snapshot = cinder_client.volume_snapshots.create(**snapshot_params)
            
            logger.info(f"Successfully created volume snapshot {name} from volume {volume_id}")
            
            return {
                'success': True,
                'data': {
                    'snapshot_id': snapshot.id,
                    'name': name,
                    'volume_id': volume_id,
                    'type': 'volume'
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to create volume snapshot: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def create_instance_snapshot(self, cluster_id: int, instance_id: str, name: str, metadata: Dict = None) -> Dict:
        """创建实例快照"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            nova_client = clients['nova']
            
            # 验证实例是否存在
            try:
                instance = nova_client.servers.get(instance_id)
            except Exception:
                return {'success': False, 'error': '指定的实例不存在'}
            
            # 创建快照
            image_id = nova_client.servers.create_image(
                instance_id, 
                name, 
                metadata=metadata or {}
            )
            
            logger.info(f"Successfully created instance snapshot {name} from instance {instance_id}")
            
            return {
                'success': True,
                'data': {
                    'snapshot_id': image_id,
                    'name': name,
                    'instance_id': instance_id,
                    'type': 'instance'
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to create instance snapshot: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def delete_snapshot(self, cluster_id: int, snapshot_id: str, snapshot_type: str = 'volume') -> bool:
        """删除快照"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            
            if snapshot_type == 'volume':
                cinder_client = clients['cinder']
                cinder_client.volume_snapshots.delete(snapshot_id)
                logger.info(f"Successfully deleted volume snapshot {snapshot_id}")
            else:
                glance_client = clients['glance']
                glance_client.images.delete(snapshot_id)
                logger.info(f"Successfully deleted instance snapshot {snapshot_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {str(e)}")
            return False
    
    def create_volume_from_snapshot(self, cluster_id: int, snapshot_id: str, volume_name: str, volume_size: int = None, description: str = '', volume_type: str = None) -> Dict:
        """从快照创建卷"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            
            # 获取快照信息
            try:
                snapshot = cinder_client.volume_snapshots.get(snapshot_id)
            except Exception:
                return {'success': False, 'error': '指定的快照不存在'}
            
            # 构建创建卷的参数
            volume_params = {
                'size': volume_size or snapshot.size,
                'name': volume_name,
                'snapshot_id': snapshot_id
            }
            
            if description:
                volume_params['description'] = description
            if volume_type:
                volume_params['volume_type'] = volume_type
            
            volume = cinder_client.volumes.create(**volume_params)
            
            logger.info(f"Successfully created volume {volume_name} from snapshot {snapshot_id}")
            
            return {
                'success': True,
                'data': {
                    'volume_id': volume.id,
                    'name': volume_name,
                    'snapshot_id': snapshot_id
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to create volume from snapshot {snapshot_id}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def get_snapshot_statistics(self, cluster_id: int) -> Dict:
        """获取快照统计信息"""
        try:
            clients = self.get_cluster_clients(cluster_id)
            cinder_client = clients['cinder']
            glance_client = clients['glance']
            
            # 获取卷快照统计
            volume_snapshots = cinder_client.volume_snapshots.list()
            volume_snapshot_count = len(volume_snapshots)
            volume_total_size = sum(getattr(s, 'size', 0) for s in volume_snapshots)
            
            # 获取实例快照统计
            images = list(glance_client.images.list())
            instance_snapshots = [
                img for img in images 
                if (hasattr(img, 'instance_uuid') or 
                    getattr(img, 'image_type', None) == 'snapshot' or
                    'snapshot' in getattr(img, 'name', '').lower())
            ]
            instance_snapshot_count = len(instance_snapshots)
            instance_total_size = sum(getattr(s, 'size', 0) or 0 for s in instance_snapshots)
            
            # 统计状态分布
            status_counts = {}
            for snapshot in volume_snapshots:
                status = snapshot.status
                status_counts[status] = status_counts.get(status, 0) + 1
            
            for snapshot in instance_snapshots:
                status = snapshot.status
                status_counts[status] = status_counts.get(status, 0) + 1
            
            total_count = volume_snapshot_count + instance_snapshot_count
            total_size = volume_total_size * 1024 * 1024 * 1024 + instance_total_size  # 卷快照单位是GB
            
            return {
                'total_count': total_count,
                'volume_snapshot_count': volume_snapshot_count,
                'instance_snapshot_count': instance_snapshot_count,
                'total_size': total_size,
                'total_size_readable': self._format_bytes(total_size),
                'volume_total_size_gb': volume_total_size,
                'instance_total_size': instance_total_size,
                'status_distribution': status_counts,
                'type_distribution': {
                    'volume': volume_snapshot_count,
                    'instance': instance_snapshot_count
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get snapshot statistics for cluster {cluster_id}: {str(e)}")
            return {
                'total_count': 0,
                'volume_snapshot_count': 0,
                'instance_snapshot_count': 0,
                'total_size': 0,
                'total_size_readable': '0 B',
                'volume_total_size_gb': 0,
                'instance_total_size': 0,
                'status_distribution': {},
                'type_distribution': {'volume': 0, 'instance': 0}
            }

# 全局服务实例（延迟初始化）
openstack_service = None

def get_openstack_service():
    """获取OpenStack服务实例"""
    global openstack_service
    if openstack_service is None:
        openstack_service = OpenstackService()
        openstack_service.initialize_config()
    return openstack_service