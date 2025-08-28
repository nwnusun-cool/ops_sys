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

# 全局服务实例（延迟初始化）
openstack_service = None

def get_openstack_service():
    """获取OpenStack服务实例"""
    global openstack_service
    if openstack_service is None:
        openstack_service = OpenstackService()
        openstack_service.initialize_config()
    return openstack_service