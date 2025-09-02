"""
Kubernetes服务层
提供与K8s集群交互的核心功能
"""
import logging
import yaml
import tempfile
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from flask import current_app
from app.models.k8s_cluster import K8sCluster

logger = logging.getLogger(__name__)

class K8sService:
    """
    Kubernetes服务类
    """
    
    def __init__(self):
        try:
            # 尝试加载集群内配置
            config.load_incluster_config()
        except:
            try:
                # 尝试加载kubeconfig文件
                config.load_kube_config()
            except Exception as e:
                logger.error(f"无法加载Kubernetes配置: {e}")
                raise

        self.v1 = client.CoreV1Api()
        self.clients = {}  # 缓存客户端连接
        self.cache_timeout = timedelta(seconds=300)  # 5分钟缓存
        self.resource_cache = {}
        self.last_cache_update = {}
    
    def get_cluster_client(self, cluster_id: int) -> Dict[str, Any]:
        """获取指定集群的K8s客户端"""
        cluster = K8sCluster.query.get(cluster_id)
        if not cluster or not cluster.is_active:
            raise ValueError(f"Cluster {cluster_id} not found or inactive")
        
        cluster_key = f"k8s_cluster_{cluster_id}"
        
        # 如果客户端不存在，创建新的
        if cluster_key not in self.clients:
            self._create_cluster_client(cluster, cluster_key)
        
        return self.clients[cluster_key]
    
    def _create_cluster_client(self, cluster: K8sCluster, cluster_key: str):
        """为指定集群创建K8s客户端"""
        try:
            kubeconfig_content = cluster.get_kubeconfig()
            if not kubeconfig_content:
                raise Exception("No kubeconfig found for cluster")
            
            # 创建临时kubeconfig文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(kubeconfig_content)
                kubeconfig_path = f.name
            
            try:
                # 加载kubeconfig
                config.load_kube_config(config_file=kubeconfig_path)
                
                # 创建各种API客户端
                self.clients[cluster_key] = {
                    'core_v1': client.CoreV1Api(),
                    'apps_v1': client.AppsV1Api(),
                    'networking_v1': client.NetworkingV1Api(),
                    'storage_v1': client.StorageV1Api(),
                    'rbac_v1': client.RbacAuthorizationV1Api(),
                    'batch_v1': client.BatchV1Api(),
                    'custom_objects': client.CustomObjectsApi(),
                    'version': client.VersionApi(),
                    'autoscaling_v1': client.AutoscalingV1Api()
                }
                
                logger.info(f"✓ K8s clients created successfully for cluster {cluster.name}")
                
            finally:
                # 删除临时文件
                if os.path.exists(kubeconfig_path):
                    os.unlink(kubeconfig_path)
            
        except Exception as e:
            error_msg = f"✗ Failed to create K8s client for cluster {cluster.name}: {str(e)}"
            logger.error(error_msg)
            raise Exception(f"Failed to connect to Kubernetes cluster: {str(e)}")
    
    def test_cluster_connection(self, cluster_id: int) -> Dict[str, Any]:
        """测试集群连接"""
        try:
            logger.info(f"Testing K8s connection for cluster {cluster_id}")
            
            # 清除缓存，强制重新创建客户端
            self.clear_cache(cluster_id)
            
            clients = self.get_cluster_client(cluster_id)
            version_api = clients['version']
            
            # 获取集群版本信息
            version_info = version_api.get_code()
            
            logger.info(f"K8s connection test successful for cluster {cluster_id}, version: {version_info.git_version}")
            
            return {
                'success': True,
                'message': f'Connection successful',
                'version': version_info.git_version,
                'build_date': version_info.build_date,
                'platform': version_info.platform
            }
            
        except Exception as e:
            error_msg = str(e)
            error_type = type(e).__name__
            logger.error(f"K8s connection test failed for cluster {cluster_id}: {error_msg}")
            
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
            return "认证失败：请检查kubeconfig中的认证信息"
        elif 'forbidden' in error_str or '403' in error_str:
            return "权限不足：当前用户没有足够的权限访问集群"
        elif 'connection' in error_str or 'network' in error_str:
            return "网络连接失败：请检查API Server地址和网络连通性"
        elif 'timeout' in error_str:
            return "连接超时：请检查网络状况和API Server响应"
        elif 'certificate' in error_str or 'tls' in error_str:
            return "证书验证失败：请检查集群证书配置"
        elif 'not found' in error_str or '404' in error_str:
            return "API端点不存在：请检查API Server地址"
        else:
            return f"连接失败：{str(exception)}"
    
    def get_cluster_overview(self, cluster_id: int) -> Dict[str, Any]:
        """获取集群概览信息"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            apps_v1 = clients['apps_v1']
            
            # 获取节点列表
            nodes = core_v1.list_node()
            
            # 获取命名空间列表
            namespaces = core_v1.list_namespace()
            
            # 获取所有Pod
            pods = core_v1.list_pod_for_all_namespaces()
            
            # 获取所有Service
            services = core_v1.list_service_for_all_namespaces()
            
            # 获取所有Deployment
            deployments = apps_v1.list_deployment_for_all_namespaces()
            
            # 统计信息
            overview = {
                'nodes': {
                    'total': len(nodes.items),
                    'ready': sum(1 for node in nodes.items if self._is_node_ready(node)),
                    'not_ready': sum(1 for node in nodes.items if not self._is_node_ready(node))
                },
                'namespaces': {
                    'total': len(namespaces.items),
                    'active': sum(1 for ns in namespaces.items if ns.status.phase == 'Active')
                },
                'pods': {
                    'total': len(pods.items),
                    'running': sum(1 for pod in pods.items if pod.status.phase == 'Running'),
                    'pending': sum(1 for pod in pods.items if pod.status.phase == 'Pending'),
                    'failed': sum(1 for pod in pods.items if pod.status.phase == 'Failed'),
                    'succeeded': sum(1 for pod in pods.items if pod.status.phase == 'Succeeded')
                },
                'services': {
                    'total': len(services.items),
                    'cluster_ip': sum(1 for svc in services.items if svc.spec.type == 'ClusterIP'),
                    'node_port': sum(1 for svc in services.items if svc.spec.type == 'NodePort'),
                    'load_balancer': sum(1 for svc in services.items if svc.spec.type == 'LoadBalancer')
                },
                'deployments': {
                    'total': len(deployments.items),
                    'ready': sum(1 for dep in deployments.items if dep.status.ready_replicas == dep.status.replicas),
                    'updating': sum(1 for dep in deployments.items if dep.status.updated_replicas != dep.status.replicas)
                }
            }
            
            return {
                'success': True,
                'data': overview
            }
            
        except Exception as e:
            logger.error(f"Failed to get cluster overview for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _is_node_ready(self, node) -> bool:
        """检查节点是否就绪"""
        if not node.status or not node.status.conditions:
            return False
        
        for condition in node.status.conditions:
            if condition.type == 'Ready':
                return condition.status == 'True'
        
        return False
    
    def list_nodes(self, cluster_id: int, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取节点列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            nodes = core_v1.list_node()
            # 获取所有Pod信息，用于统计每个节点的Pod数量和资源使用情况
            all_pods = core_v1.list_pod_for_all_namespaces()
            
            # 按节点统计Pod数量和资源使用
            node_stats = {}
            for pod in all_pods.items:
                if pod.spec.node_name:
                    if pod.spec.node_name not in node_stats:
                        node_stats[pod.spec.node_name] = {
                            'pod_count': 0,
                            'running_pods': 0,
                            'pending_pods': 0,
                            'failed_pods': 0,
                            'cpu_requests': 0,
                            'memory_requests': 0
                        }
                    
                    stats = node_stats[pod.spec.node_name]
                    stats['pod_count'] += 1
                    
                    # 统计不同状态的Pod
                    if pod.status and pod.status.phase:
                        phase = pod.status.phase.lower()
                        if phase == 'running':
                            stats['running_pods'] += 1
                        elif phase == 'pending':
                            stats['pending_pods'] += 1
                        elif phase == 'failed':
                            stats['failed_pods'] += 1
                    
                    # 统计资源请求
                    if pod.spec.containers:
                        for container in pod.spec.containers:
                            if container.resources and container.resources.requests:
                                # 解析CPU请求
                                if 'cpu' in container.resources.requests:
                                    cpu_str = container.resources.requests['cpu']
                                    stats['cpu_requests'] += self._parse_cpu_value(cpu_str)
                                
                                # 解析内存请求
                                if 'memory' in container.resources.requests:
                                    memory_str = container.resources.requests['memory']
                                    stats['memory_requests'] += self._parse_memory_value(memory_str)
            
            nodes_data = []
            
            for node in nodes.items:
                node_info = self._format_node_data(node)
                node_name = node.metadata.name
                
                # 添加Pod和资源使用统计信息
                stats = node_stats.get(node_name, {
                    'pod_count': 0,
                    'running_pods': 0,
                    'pending_pods': 0,
                    'failed_pods': 0,
                    'cpu_requests': 0,
                    'memory_requests': 0
                })
                
                node_info.update(stats)
                
                # 计算资源使用和格式化显示
                allocatable_cpu = self._parse_cpu_value(node_info['allocatable']['cpu'])
                allocatable_memory = self._parse_memory_value(node_info['allocatable']['memory'])
                
                # 添加格式化的资源使用显示
                node_info['cpu_used'] = f"{stats['cpu_requests']}m"
                node_info['memory_used'] = f"{stats['memory_requests']}Mi"
                
                # 计算使用百分比
                node_info['resource_usage'] = {
                    'cpu_usage_percent': round((stats['cpu_requests'] / allocatable_cpu * 100) if allocatable_cpu > 0 else 0, 1),
                    'memory_usage_percent': round((stats['memory_requests'] / allocatable_memory * 100) if allocatable_memory > 0 else 0, 1),
                    'pod_usage_percent': round((stats['pod_count'] / int(node_info['capacity']['pods']) * 100) if node_info['capacity']['pods'] != '0' else 0, 1)
                }
                
                # 应用过滤器
                if self._apply_node_filters(node_info, filters):
                    nodes_data.append(node_info)
            
            # 排序
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                nodes_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            # 分页
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(nodes_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(nodes_data) + per_page - 1) // per_page,
                'data': nodes_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list nodes for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_node_data(self, node) -> Dict[str, Any]:
        """格式化节点数据"""
        # 获取节点状态
        ready_status = 'Unknown'
        for condition in node.status.conditions or []:
            if condition.type == 'Ready':
                ready_status = 'Ready' if condition.status == 'True' else 'NotReady'
                break
        
        # 获取节点角色
        roles = []
        if node.metadata.labels:
            for label_key in node.metadata.labels:
                if label_key.startswith('node-role.kubernetes.io/'):
                    role = label_key.split('/')[-1]
                    if role:
                        roles.append(role)
        
        if not roles:
            roles = ['<none>']
        
        # 获取节点资源信息
        capacity = node.status.capacity or {}
        allocatable = node.status.allocatable or {}
        
        return {
            'name': node.metadata.name,
            'status': ready_status,
            'roles': roles,
            'age': self._calculate_age(node.metadata.creation_timestamp),
            'version': node.status.node_info.kubelet_version if node.status.node_info else 'Unknown',
            'internal_ip': self._get_node_internal_ip(node),
            'external_ip': self._get_node_external_ip(node),
            'os_image': node.status.node_info.os_image if node.status.node_info else 'Unknown',
            'kernel_version': node.status.node_info.kernel_version if node.status.node_info else 'Unknown',
            'container_runtime': node.status.node_info.container_runtime_version if node.status.node_info else 'Unknown',
            'capacity': {
                'cpu': capacity.get('cpu', '0'),
                'memory': capacity.get('memory', '0'),
                'pods': capacity.get('pods', '0'),
                'storage': capacity.get('ephemeral-storage', '0')
            },
            'allocatable': {
                'cpu': allocatable.get('cpu', '0'),
                'memory': allocatable.get('memory', '0'),
                'pods': allocatable.get('pods', '0'),
                'storage': allocatable.get('ephemeral-storage', '0')
            },
            'labels': node.metadata.labels or {},
            'annotations': node.metadata.annotations or {}
        }
    
    def _get_node_internal_ip(self, node) -> str:
        """获取节点内部IP"""
        if not node.status or not node.status.addresses:
            return 'Unknown'
        
        for addr in node.status.addresses:
            if addr.type == 'InternalIP':
                return addr.address
        
        return 'Unknown'
    
    def _get_node_external_ip(self, node) -> str:
        """获取节点外部IP"""
        if not node.status or not node.status.addresses:
            return '<none>'
        
        for addr in node.status.addresses:
            if addr.type == 'ExternalIP':
                return addr.address
        
        return '<none>'
    
    def _calculate_age(self, creation_timestamp) -> str:
        """计算资源年龄"""
        if not creation_timestamp:
            return 'Unknown'
        
        now = datetime.utcnow().replace(tzinfo=None)
        created = creation_timestamp.replace(tzinfo=None)
        age_delta = now - created
        
        days = age_delta.days
        hours, remainder = divmod(age_delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d{hours}h"
        elif hours > 0:
            return f"{hours}h{minutes}m"
        else:
            return f"{minutes}m"
    
    def _apply_node_filters(self, node_data: Dict, filters: Optional[Dict]) -> bool:
        """应用节点过滤条件"""
        if not filters:
            return True
        
        # 状态过滤
        if 'status' in filters and filters['status']:
            if node_data['status'].lower() != filters['status'].lower():
                return False
        
        # 角色过滤
        if 'role' in filters and filters['role']:
            node_roles = [role.lower() for role in node_data['roles']]
            if filters['role'].lower() not in node_roles:
                return False
        
        # 名称搜索
        if 'search' in filters and filters['search']:
            search_term = filters['search'].lower()
            if (search_term not in node_data['name'].lower() and
                search_term not in node_data['internal_ip'].lower()):
                return False
        
        return True
    
    def get_node_detail(self, cluster_id: int, node_name: str) -> Dict[str, Any]:
        """获取节点详细信息"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 获取节点信息
            node = core_v1.read_node(name=node_name)
            
            # 获取节点上的Pod列表
            pods = core_v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
            
            # 格式化节点详细信息
            node_detail = self._format_node_data(node)
            
            # 添加Pod信息
            node_detail['pods'] = []
            total_cpu_requests = 0
            total_memory_requests = 0
            total_cpu_limits = 0
            total_memory_limits = 0
            
            for pod in pods.items:
                cpu_request = self._get_pod_cpu_request(pod)
                memory_request = self._get_pod_memory_request(pod)
                cpu_limit = self._get_pod_cpu_limit(pod)
                memory_limit = self._get_pod_memory_limit(pod)
                
                pod_info = {
                    'name': pod.metadata.name,
                    'namespace': pod.metadata.namespace,
                    'status': pod.status.phase,
                    'created_at': self._calculate_age(pod.metadata.creation_timestamp),
                    'restart_count': sum([
                        container.restart_count for container in (pod.status.container_statuses or [])
                    ]),
                    'cpu_request': cpu_request,
                    'memory_request': memory_request,
                    'cpu_limit': cpu_limit,
                    'memory_limit': memory_limit
                }
                node_detail['pods'].append(pod_info)
                
                # 累计资源请求和限制
                total_cpu_requests += self._parse_cpu_value(cpu_request)
                total_memory_requests += self._parse_memory_value(memory_request)
                total_cpu_limits += self._parse_cpu_value(cpu_limit)
                total_memory_limits += self._parse_memory_value(memory_limit)
            
            # 统计节点资源使用情况
            node_detail['pod_count'] = len(pods.items)
            node_detail['running_pods'] = sum(1 for pod in pods.items if pod.status.phase == 'Running')
            node_detail['pending_pods'] = sum(1 for pod in pods.items if pod.status.phase == 'Pending')
            node_detail['failed_pods'] = sum(1 for pod in pods.items if pod.status.phase == 'Failed')
            
            # 计算资源使用百分比
            node_capacity = node_detail.get('capacity', {})
            node_allocatable = node_detail.get('allocatable', {})
            
            allocatable_cpu = self._parse_cpu_value(node_allocatable.get('cpu', '0'))
            allocatable_memory = self._parse_memory_value(node_allocatable.get('memory', '0'))
            
            # 添加格式化的资源使用显示
            node_detail['cpu_used'] = f"{total_cpu_requests}m"
            node_detail['memory_used'] = f"{total_memory_requests}Mi"
            
            node_detail['resource_usage'] = {
                'cpu_requests': f"{total_cpu_requests}m",
                'memory_requests': f"{total_memory_requests}Mi",
                'cpu_limits': f"{total_cpu_limits}m",
                'memory_limits': f"{total_memory_limits}Mi",
                'cpu_request_percentage': round((total_cpu_requests / allocatable_cpu * 100) if allocatable_cpu > 0 else 0, 2),
                'memory_request_percentage': round((total_memory_requests / allocatable_memory * 100) if allocatable_memory > 0 else 0, 2),
                'cpu_limit_percentage': round((total_cpu_limits / allocatable_cpu * 100) if allocatable_cpu > 0 else 0, 2),
                'memory_limit_percentage': round((total_memory_limits / allocatable_memory * 100) if allocatable_memory > 0 else 0, 2),
                'pod_capacity_percentage': round((len(pods.items) / int(node_capacity.get('pods', '1')) * 100), 2),
                'cpu_usage_percent': round((total_cpu_requests / allocatable_cpu * 100) if allocatable_cpu > 0 else 0, 1),
                'memory_usage_percent': round((total_memory_requests / allocatable_memory * 100) if allocatable_memory > 0 else 0, 1),
                'pod_usage_percent': round((len(pods.items) / int(node_capacity.get('pods', '1')) * 100) if node_capacity.get('pods', '1') != '0' else 0, 1)
            }
            
            # 节点健康状态
            node_detail['health_status'] = self._get_node_health_status(node)
            
            return {
                'success': True,
                'data': node_detail
            }
            
        except Exception as e:
            logger.error(f"Failed to get node detail {node_name} for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_pod_cpu_request(self, pod) -> str:
        """获取Pod CPU请求量"""
        total_cpu = 0
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources and container.resources.requests and 'cpu' in container.resources.requests:
                    cpu_str = container.resources.requests['cpu']
                    # 简单解析CPU值
                    if cpu_str.endswith('m'):
                        total_cpu += int(cpu_str[:-1])
                    else:
                        total_cpu += int(float(cpu_str) * 1000)
        
        return f"{total_cpu}m" if total_cpu > 0 else "0"
    
    def _get_pod_memory_request(self, pod) -> str:
        """获取Pod内存请求量"""
        total_memory = 0
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources and container.resources.requests and 'memory' in container.resources.requests:
                    memory_str = container.resources.requests['memory']
                    # 简单解析内存值
                    if memory_str.endswith('Mi'):
                        total_memory += int(memory_str[:-2])
                    elif memory_str.endswith('Gi'):
                        total_memory += int(memory_str[:-2]) * 1024
                    elif memory_str.endswith('Ki'):
                        total_memory += int(memory_str[:-2]) // 1024
        
        return f"{total_memory}Mi" if total_memory > 0 else "0"
    
    def _get_pod_cpu_limit(self, pod) -> str:
        """获取Pod CPU限制量"""
        total_cpu = 0
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources and container.resources.limits and 'cpu' in container.resources.limits:
                    cpu_str = container.resources.limits['cpu']
                    # 简单解析CPU值
                    if cpu_str.endswith('m'):
                        total_cpu += int(cpu_str[:-1])
                    else:
                        total_cpu += int(float(cpu_str) * 1000)
        
        return f"{total_cpu}m" if total_cpu > 0 else "0"
    
    def _get_pod_memory_limit(self, pod) -> str:
        """获取Pod内存限制量"""
        total_memory = 0
        if pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources and container.resources.limits and 'memory' in container.resources.limits:
                    memory_str = container.resources.limits['memory']
                    # 简单解析内存值
                    if memory_str.endswith('Mi'):
                        total_memory += int(memory_str[:-2])
                    elif memory_str.endswith('Gi'):
                        total_memory += int(memory_str[:-2]) * 1024
                    elif memory_str.endswith('Ki'):
                        total_memory += int(memory_str[:-2]) // 1024
        
        return f"{total_memory}Mi" if total_memory > 0 else "0"
    
    def _parse_cpu_value(self, cpu_str: str) -> int:
        """解析CPU值为毫核心"""
        if not cpu_str or cpu_str == "0":
            return 0
        
        try:
            if cpu_str.endswith('m'):
                return int(cpu_str[:-1])
            else:
                return int(float(cpu_str) * 1000)
        except (ValueError, AttributeError):
            return 0
    
    def _parse_memory_value(self, memory_str: str) -> int:
        """解析内存值为Mi"""
        if not memory_str or memory_str == "0":
            return 0
        
        try:
            if memory_str.endswith('Mi'):
                return int(memory_str[:-2])
            elif memory_str.endswith('Gi'):
                return int(memory_str[:-2]) * 1024
            elif memory_str.endswith('Ki'):
                return int(memory_str[:-2]) // 1024
            elif memory_str.endswith('Ti'):
                return int(memory_str[:-2]) * 1024 * 1024
            else:
                # 假设是字节，转换为Mi
                return int(int(memory_str) / (1024 * 1024))
        except (ValueError, AttributeError):
            return 0
    
    def _get_node_health_status(self, node) -> Dict[str, Any]:
        """获取节点健康状态"""
        health_status = {
            'overall': 'Unknown',
            'conditions': [],
            'issues': []
        }
        
        if not node.status or not node.status.conditions:
            return health_status
        
        ready = False
        for condition in node.status.conditions:
            condition_info = {
                'type': condition.type,
                'status': condition.status,
                'reason': condition.reason or '',
                'message': condition.message or '',
                'last_transition': condition.last_transition_time.isoformat() if condition.last_transition_time else None
            }
            health_status['conditions'].append(condition_info)
            
            # 检查关键状态
            if condition.type == 'Ready':
                ready = (condition.status == 'True')
            elif condition.status == 'True' and condition.type in ['MemoryPressure', 'DiskPressure', 'PIDPressure', 'NetworkUnavailable']:
                health_status['issues'].append({
                    'type': condition.type,
                    'message': condition.message or f'{condition.type} detected'
                })
        
        # 确定整体健康状态
        if ready:
            if health_status['issues']:
                health_status['overall'] = 'Warning'
            else:
                health_status['overall'] = 'Healthy'
        else:
            health_status['overall'] = 'Unhealthy'
        
        return health_status
    
    def cordon_node(self, cluster_id: int, node_name: str) -> Dict[str, Any]:
        """封锁节点（设置不可调度）"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 获取节点
            node = core_v1.read_node(name=node_name)
            
            # 设置不可调度
            node.spec.unschedulable = True
            
            # 更新节点
            core_v1.patch_node(name=node_name, body=node)
            
            logger.info(f"Successfully cordoned node {node_name} in cluster {cluster_id}")
            
            return {
                'success': True,
                'message': f'节点 {node_name} 已设置为不可调度'
            }
            
        except Exception as e:
            logger.error(f"Failed to cordon node {node_name} in cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def uncordon_node(self, cluster_id: int, node_name: str) -> Dict[str, Any]:
        """解除封锁节点（设置可调度）"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 获取节点
            node = core_v1.read_node(name=node_name)
            
            # 设置可调度
            node.spec.unschedulable = False
            
            # 更新节点
            core_v1.patch_node(name=node_name, body=node)
            
            logger.info(f"Successfully uncordoned node {node_name} in cluster {cluster_id}")
            
            return {
                'success': True,
                'message': f'节点 {node_name} 已设置为可调度'
            }
            
        except Exception as e:
            logger.error(f"Failed to uncordon node {node_name} in cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def drain_node(self, cluster_id: int, node_name: str, force: bool = False) -> Dict[str, Any]:
        """驱逐节点上的Pod"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 首先封锁节点
            cordon_result = self.cordon_node(cluster_id, node_name)
            if not cordon_result['success']:
                return cordon_result
            
            # 获取节点上的Pod
            pods = core_v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}")
            
            drained_pods = []
            failed_pods = []
            
            for pod in pods.items:
                # 跳过DaemonSet管理的Pod（除非强制）
                if not force and self._is_daemonset_pod(pod):
                    continue
                
                # 跳过系统Pod（kube-system命名空间）
                if not force and pod.metadata.namespace == 'kube-system':
                    continue
                
                try:
                    # 创建驱逐对象
                    from kubernetes.client import V1Eviction, V1ObjectMeta
                    
                    eviction = V1Eviction(
                        api_version="policy/v1beta1",
                        kind="Eviction",
                        metadata=V1ObjectMeta(
                            name=pod.metadata.name,
                            namespace=pod.metadata.namespace
                        )
                    )
                    
                    # 执行驱逐
                    core_v1.create_namespaced_pod_eviction(
                        name=pod.metadata.name,
                        namespace=pod.metadata.namespace,
                        body=eviction
                    )
                    
                    drained_pods.append(f"{pod.metadata.namespace}/{pod.metadata.name}")
                    
                except Exception as e:
                    failed_pods.append(f"{pod.metadata.namespace}/{pod.metadata.name}: {str(e)}")
            
            logger.info(f"Drained {len(drained_pods)} pods from node {node_name} in cluster {cluster_id}")
            
            message = f"节点 {node_name} 驱逐完成"
            if drained_pods:
                message += f"，成功驱逐 {len(drained_pods)} 个Pod"
            if failed_pods:
                message += f"，{len(failed_pods)} 个Pod驱逐失败"
            
            return {
                'success': True,
                'message': message,
                'drained_pods': drained_pods,
                'failed_pods': failed_pods
            }
            
        except Exception as e:
            logger.error(f"Failed to drain node {node_name} in cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _is_daemonset_pod(self, pod) -> bool:
        """检查Pod是否由DaemonSet管理"""
        if pod.metadata.owner_references:
            for owner in pod.metadata.owner_references:
                if owner.kind == 'DaemonSet':
                    return True
        return False
    
    def _is_pod_managed_by_controller(self, pod) -> bool:
        """检查Pod是否由控制器管理"""
        if not pod.metadata or not pod.metadata.owner_references:
            return False
        
        # 检查是否由控制器管理（Deployment, ReplicaSet, DaemonSet, StatefulSet, Job等）
        controller_kinds = ['Deployment', 'ReplicaSet', 'DaemonSet', 'StatefulSet', 'Job', 'CronJob']
        
        for owner in pod.metadata.owner_references:
            if owner.kind in controller_kinds:
                return True
        return False
    
    # ====== 命名空间管理 ======
    
    def list_namespaces(self, cluster_id: int, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取命名空间列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            namespaces = core_v1.list_namespace()
            namespaces_data = []
            
            for ns in namespaces.items:
                ns_info = self._format_namespace_data(ns)
                
                # 应用过滤器
                if self._apply_namespace_filters(ns_info, filters):
                    namespaces_data.append(ns_info)
            
            # 排序
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                namespaces_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            # 分页
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(namespaces_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(namespaces_data) + per_page - 1) // per_page,
                'data': namespaces_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list namespaces for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_namespace_details(self, cluster_id: int, namespace: str) -> Dict[str, Any]:
        """获取命名空间详情"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 获取命名空间基本信息
            ns = core_v1.read_namespace(name=namespace)
            ns_info = self._format_namespace_data(ns)
            
            # 获取命名空间资源统计
            resource_stats = self._get_namespace_resource_stats(core_v1, namespace)
            ns_info['resource_stats'] = resource_stats
            
            # 获取资源配额
            try:
                quotas = core_v1.list_namespaced_resource_quota(namespace=namespace)
                ns_info['quotas'] = [self._format_quota_data(quota) for quota in quotas.items]
            except Exception:
                ns_info['quotas'] = []
            
            # 获取限制范围
            try:
                limits = core_v1.list_namespaced_limit_range(namespace=namespace)
                ns_info['limit_ranges'] = [self._format_limit_range_data(limit) for limit in limits.items]
            except Exception:
                ns_info['limit_ranges'] = []
            
            return {
                'success': True,
                'data': ns_info
            }
            
        except Exception as e:
            logger.error(f"Failed to get namespace details for {namespace} in cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_namespace(self, cluster_id: int, namespace_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建命名空间"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 构建命名空间对象
            ns_body = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=namespace_data['name'],
                    labels=namespace_data.get('labels', {}),
                    annotations=namespace_data.get('annotations', {})
                )
            )
            
            # 创建命名空间
            result = core_v1.create_namespace(body=ns_body)
            
            return {
                'success': True,
                'data': self._format_namespace_data(result)
            }
            
        except Exception as e:
            logger.error(f"Failed to create namespace in cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_namespace(self, cluster_id: int, namespace: str) -> Dict[str, Any]:
        """删除命名空间"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 删除命名空间
            core_v1.delete_namespace(name=namespace)
            
            return {
                'success': True,
                'message': f'Namespace {namespace} deletion initiated'
            }
            
        except Exception as e:
            logger.error(f"Failed to delete namespace {namespace} in cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_namespace_data(self, ns) -> Dict[str, Any]:
        """格式化命名空间数据"""
        return {
            'name': ns.metadata.name,
            'status': ns.status.phase if ns.status else 'Unknown',
            'age': self._calculate_age(ns.metadata.creation_timestamp),
            'labels': ns.metadata.labels or {},
            'annotations': ns.metadata.annotations or {},
            'created_at': ns.metadata.creation_timestamp.isoformat() if ns.metadata.creation_timestamp else None
        }
    
    def _apply_namespace_filters(self, ns_info: Dict, filters: Optional[Dict]) -> bool:
        """应用命名空间过滤器"""
        if not filters:
            return True
        
        # 状态过滤
        if 'status' in filters and filters['status']:
            if ns_info['status'].lower() != filters['status'].lower():
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in ns_info['name'].lower():
                return False
        
        return True
    
    def _get_namespace_resource_stats(self, core_v1, namespace: str) -> Dict[str, int]:
        """获取命名空间资源统计"""
        stats = {
            'pods': 0,
            'services': 0,
            'configmaps': 0,
            'secrets': 0,
            'persistentvolumeclaims': 0
        }
        
        try:
            # 统计Pods
            pods = core_v1.list_namespaced_pod(namespace=namespace)
            stats['pods'] = len(pods.items)
            
            # 统计Services
            services = core_v1.list_namespaced_service(namespace=namespace)
            stats['services'] = len(services.items)
            
            # 统计ConfigMaps
            configmaps = core_v1.list_namespaced_config_map(namespace=namespace)
            stats['configmaps'] = len(configmaps.items)
            
            # 统计Secrets
            secrets = core_v1.list_namespaced_secret(namespace=namespace)
            stats['secrets'] = len(secrets.items)
            
            # 统计PVCs
            pvcs = core_v1.list_namespaced_persistent_volume_claim(namespace=namespace)
            stats['persistentvolumeclaims'] = len(pvcs.items)
            
        except Exception as e:
            logger.warning(f"Failed to get resource stats for namespace {namespace}: {str(e)}")
        
        return stats
    
    def _format_quota_data(self, quota) -> Dict[str, Any]:
        """格式化资源配额数据"""
        return {
            'name': quota.metadata.name,
            'hard': dict(quota.status.hard) if quota.status and quota.status.hard else {},
            'used': dict(quota.status.used) if quota.status and quota.status.used else {}
        }
    
    def _format_limit_range_data(self, limit_range) -> Dict[str, Any]:
        """格式化限制范围数据"""
        limits = []
        if limit_range.spec and limit_range.spec.limits:
            for limit in limit_range.spec.limits:
                limits.append({
                    'type': limit.type,
                    'default': dict(limit.default) if limit.default else {},
                    'default_request': dict(limit.default_request) if limit.default_request else {},
                    'max': dict(limit.max) if limit.max else {},
                    'min': dict(limit.min) if limit.min else {}
                })
        
        return {
            'name': limit_range.metadata.name,
            'limits': limits
        }
    
    # ====== 工作负载管理 ======
    
    def list_pods(self, cluster_id: int, namespace: str = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取Pods列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            if namespace:
                pods = core_v1.list_namespaced_pod(namespace=namespace)
            else:
                pods = core_v1.list_pod_for_all_namespaces()
            
            pods_data = []
            for pod in pods.items:
                pod_info = self._format_pod_data(pod)
                
                # 应用过滤器
                if self._apply_pod_filters(pod_info, filters):
                    pods_data.append(pod_info)
            
            # 排序和分页
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                pods_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(pods_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(pods_data) + per_page - 1) // per_page,
                'data': pods_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list pods for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_pod_details(self, cluster_id: int, namespace: str, pod_name: str) -> Dict[str, Any]:
        """获取Pod详情"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            pod_info = self._format_pod_data(pod)
            
            # 获取Pod日志
            try:
                logs = core_v1.read_namespaced_pod_log(
                    name=pod_name, 
                    namespace=namespace,
                    tail_lines=100
                )
                pod_info['logs'] = logs
            except Exception:
                pod_info['logs'] = "无法获取日志"
            
            # 获取Pod事件
            try:
                events = core_v1.list_namespaced_event(
                    namespace=namespace,
                    field_selector=f'involvedObject.name={pod_name}'
                )
                pod_info['events'] = [self._format_event_data(event) for event in events.items]
            except Exception:
                pod_info['events'] = []
            
            return {
                'success': True,
                'data': pod_info
            }
            
        except Exception as e:
            logger.error(f"Failed to get pod details for {pod_name} in {namespace}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_pod(self, cluster_id: int, namespace: str, pod_name: str) -> Dict[str, Any]:
        """删除Pod"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            core_v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            
            return {
                'success': True,
                'message': f'Pod {pod_name} deleted successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to delete pod {pod_name} in {namespace}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    
    def get_pod_logs(self, cluster_id: int, namespace: str, pod_name: str, 
                     container: str = None, tail_lines: int = 100, 
                     since_seconds: int = None, since_time: str = None,
                     timestamps: bool = False, follow: bool = False) -> Dict[str, Any]:
        """获取Pod日志"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 构建参数
            kwargs = {
                'name': pod_name,
                'namespace': namespace,
                'timestamps': timestamps
            }
            
            # 设置tail_lines，如果为None则获取所有日志
            if tail_lines is not None and tail_lines > 0:
                kwargs['tail_lines'] = tail_lines
            
            if container:
                kwargs['container'] = container
            if since_seconds:
                kwargs['since_seconds'] = since_seconds
            if since_time:
                # 解析时间字符串
                try:
                    from datetime import datetime
                    import dateutil.parser
                    parsed_time = dateutil.parser.parse(since_time)
                    kwargs['since_time'] = parsed_time
                except Exception as parse_error:
                    logger.warning(f"Failed to parse since_time '{since_time}': {parse_error}")
                    
            # 注意：follow参数在read_namespaced_pod_log中不支持，
            # 如果需要实时流，需要使用不同的方法
            # 这里我们忽略follow参数，因为HTTP请求不适合长时间流式传输
                
            # 获取日志
            logs = core_v1.read_namespaced_pod_log(**kwargs)
            
            return {
                'success': True,
                'data': logs,  # 直接返回日志字符串
                'metadata': {
                    'pod_name': pod_name,
                    'namespace': namespace,
                    'container': container,
                    'tail_lines': tail_lines,
                    'timestamps': timestamps,
                    'since_time': since_time,
                    'since_seconds': since_seconds
                }
            }
            
        except ApiException as e:
            if e.status == 404:
                return {
                    'success': False,
                    'error': f'Pod {pod_name} not found'
                }
            else:
                logger.error(f"Failed to get logs for pod {pod_name} in {namespace}: {str(e)}")
                return {
                    'success': False,
                    'error': str(e)
                }
        except Exception as e:
            logger.error(f"Failed to get logs for pod {pod_name} in {namespace}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_pod_yaml(self, cluster_id: int, namespace: str, pod_name: str) -> Dict[str, Any]:
        """获取Pod的YAML配置"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 获取Pod对象
            pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            # 清理管理字段
            if pod.metadata:
                pod.metadata.managed_fields = None
                pod.metadata.resource_version = None
                pod.metadata.uid = None
                pod.metadata.self_link = None
                pod.metadata.creation_timestamp = None
            
            if pod.status:
                # 清理状态字段，这些在YAML中通常不需要
                pod.status = None
            
            # 转换为YAML字符串
            import yaml
            from kubernetes.client.rest import ApiException
            
            # 转换为字典
            pod_dict = pod.to_dict()
            
            # 移除空值和系统生成的字段
            pod_dict = self._clean_k8s_object_for_yaml(pod_dict)
            
            # 添加API版本和种类
            pod_dict['apiVersion'] = 'v1'
            pod_dict['kind'] = 'Pod'
            
            # 转换为YAML
            yaml_content = yaml.dump(pod_dict, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            return {
                'success': True,
                'data': yaml_content,
                'metadata': {
                    'pod_name': pod_name,
                    'namespace': namespace
                }
            }
            
        except ApiException as e:
            if e.status == 404:
                return {
                    'success': False,
                    'error': f'Pod {pod_name} not found'
                }
            else:
                logger.error(f"Failed to get YAML for pod {pod_name} in {namespace}: {str(e)}")
                return {
                    'success': False,
                    'error': str(e)
                }
        except Exception as e:
            logger.error(f"Failed to get YAML for pod {pod_name} in {namespace}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _clean_k8s_object_for_yaml(self, obj):
        """清理Kubernetes对象用于YAML导出"""
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                # 跳过这些系统字段
                if key in ['resource_version', 'uid', 'self_link', 'creation_timestamp', 
                          'managed_fields', 'status', 'generation', 'owner_references']:
                    continue
                if value is not None:
                    cleaned[key] = self._clean_k8s_object_for_yaml(value)
            return cleaned
        elif isinstance(obj, list):
            return [self._clean_k8s_object_for_yaml(item) for item in obj if item is not None]
        else:
            return obj
    
    def list_deployments(self, cluster_id: int, namespace: str = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取Deployments列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            
            if namespace:
                deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
            else:
                deployments = apps_v1.list_deployment_for_all_namespaces()
            
            deployments_data = []
            for deployment in deployments.items:
                deployment_info = self._format_deployment_data(deployment)
                
                # 应用过滤器
                if self._apply_deployment_filters(deployment_info, filters):
                    deployments_data.append(deployment_info)
            
            # 排序和分页
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                deployments_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(deployments_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(deployments_data) + per_page - 1) // per_page,
                'data': deployments_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list deployments for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def scale_deployment(self, cluster_id: int, namespace: str, deployment_name: str, replicas: int) -> Dict[str, Any]:
        """扩缩容Deployment"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            
            # 获取当前deployment
            deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            
            # 更新副本数
            deployment.spec.replicas = replicas
            
            # 应用更新
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=deployment
            )
            
            return {
                'success': True,
                'message': f'Deployment {deployment_name} scaled to {replicas} replicas'
            }
            
        except Exception as e:
            logger.error(f"Failed to scale deployment {deployment_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def restart_deployment(self, cluster_id: int, namespace: str, deployment_name: str) -> Dict[str, Any]:
        """重启Deployment"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            
            # 通过添加annotation来触发重启
            now = datetime.utcnow().isoformat()
            patch_body = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'kubectl.kubernetes.io/restartedAt': now
                            }
                        }
                    }
                }
            }
            
            apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch_body
            )
            
            return {
                'success': True,
                'message': f'Deployment {deployment_name} restart initiated'
            }
            
        except Exception as e:
            logger.error(f"Failed to restart deployment {deployment_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def delete_deployment(self, cluster_id: int, namespace: str, deployment_name: str) -> Dict[str, Any]:
        """删除Deployment"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            
            apps_v1.delete_namespaced_deployment(name=deployment_name, namespace=namespace)
            
            return {
                'success': True,
                'message': f'Deployment {deployment_name} deleted successfully'
            }
            
        except Exception as e:
            logger.error(f"Failed to delete deployment {deployment_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_pod_data(self, pod) -> Dict[str, Any]:
        """格式化Pod数据"""
        # 获取Pod状态
        status = 'Unknown'
        if pod.status:
            if pod.status.phase:
                status = pod.status.phase
            
            # 检查是否有问题
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    if condition.type == 'Ready' and condition.status != 'True':
                        status = 'NotReady'
                        break
        
        # 获取重启次数
        restart_count = 0
        if pod.status and pod.status.container_statuses:
            restart_count = sum(container.restart_count for container in pod.status.container_statuses)
        
        # 获取容器信息和资源统计
        containers = []
        total_cpu_requests = 0  # 毫核心
        total_memory_requests = 0  # Mi
        
        if pod.spec and pod.spec.containers:
            for container in pod.spec.containers:
                container_resources = {
                    'requests': dict(container.resources.requests) if container.resources and container.resources.requests else {},
                    'limits': dict(container.resources.limits) if container.resources and container.resources.limits else {}
                }
                
                # 获取容器的volume mounts
                volume_mounts = []
                if container.volume_mounts:
                    for volume_mount in container.volume_mounts:
                        volume_mounts.append({
                            'name': volume_mount.name,
                            'mount_path': volume_mount.mount_path,
                            'read_only': volume_mount.read_only or False,
                            'sub_path': volume_mount.sub_path
                        })
                
                containers.append({
                    'name': container.name,
                    'image': container.image,
                    'resources': container_resources,
                    'volume_mounts': volume_mounts
                })
                
                # 累加CPU和内存请求
                if container.resources and container.resources.requests:
                    if 'cpu' in container.resources.requests:
                        cpu_str = container.resources.requests['cpu']
                        total_cpu_requests += self._parse_cpu_value(cpu_str)
                    if 'memory' in container.resources.requests:
                        memory_str = container.resources.requests['memory']
                        total_memory_requests += self._parse_memory_value(memory_str)
        
        # 获取卷信息
        volumes = []
        if pod.spec and pod.spec.volumes:
            for volume in pod.spec.volumes:
                volume_info = {
                    'name': volume.name,
                    'type': 'Unknown'
                }
                
                # 确定卷类型和详细信息
                if volume.persistent_volume_claim:
                    volume_info['type'] = 'PersistentVolumeClaim'
                    volume_info['claim_name'] = volume.persistent_volume_claim.claim_name
                elif volume.config_map:
                    volume_info['type'] = 'ConfigMap'
                    volume_info['config_map_name'] = volume.config_map.name
                elif volume.secret:
                    volume_info['type'] = 'Secret'
                    volume_info['secret_name'] = volume.secret.secret_name
                elif volume.empty_dir is not None:
                    volume_info['type'] = 'EmptyDir'
                    if volume.empty_dir.size_limit:
                        volume_info['size_limit'] = str(volume.empty_dir.size_limit)
                elif volume.host_path:
                    volume_info['type'] = 'HostPath'
                    volume_info['host_path'] = volume.host_path.path
                    volume_info['path_type'] = volume.host_path.type
                elif volume.nfs:
                    volume_info['type'] = 'NFS'
                    volume_info['server'] = volume.nfs.server
                    volume_info['path'] = volume.nfs.path
                elif volume.downward_api:
                    volume_info['type'] = 'DownwardAPI'
                elif volume.projected:
                    volume_info['type'] = 'Projected'
                
                volumes.append(volume_info)
        
        return {
            'name': pod.metadata.name,
            'namespace': pod.metadata.namespace,
            'status': status,
            'node_name': pod.spec.node_name if pod.spec else None,
            'pod_ip': pod.status.pod_ip if pod.status else None,
            'host_ip': pod.status.host_ip if pod.status else None,
            'restart_count': restart_count,
            'age': self._calculate_age(pod.metadata.creation_timestamp),
            'cpu': f"{total_cpu_requests}m" if total_cpu_requests > 0 else "0m",
            'memory': f"{total_memory_requests}Mi" if total_memory_requests > 0 else "0Mi",
            'labels': pod.metadata.labels or {},
            'annotations': pod.metadata.annotations or {},
            'containers': containers,
            'volumes': volumes,
            'created_at': pod.metadata.creation_timestamp.isoformat() if pod.metadata.creation_timestamp else None
        }
    
    def _format_deployment_data(self, deployment) -> Dict[str, Any]:
        """格式化Deployment数据"""
        ready_replicas = deployment.status.ready_replicas or 0
        replicas = deployment.spec.replicas or 0
        available_replicas = deployment.status.available_replicas or 0
        
        return {
            'name': deployment.metadata.name,
            'namespace': deployment.metadata.namespace,
            'replicas': replicas,
            'ready_replicas': ready_replicas,
            'available_replicas': available_replicas,
            'updated_replicas': deployment.status.updated_replicas or 0,
            'unavailable_replicas': deployment.status.unavailable_replicas or 0,
            'age': self._calculate_age(deployment.metadata.creation_timestamp),
            'labels': deployment.metadata.labels or {},
            'selector': deployment.spec.selector.match_labels if deployment.spec.selector else {},
            'strategy': deployment.spec.strategy.type if deployment.spec.strategy else 'RollingUpdate',
            'created_at': deployment.metadata.creation_timestamp.isoformat() if deployment.metadata.creation_timestamp else None
        }
    
    def _format_event_data(self, event) -> Dict[str, Any]:
        """格式化事件数据"""
        return {
            'type': event.type,
            'reason': event.reason,
            'message': event.message,
            'source': event.source.component if event.source else 'Unknown',
            'first_timestamp': event.first_timestamp.isoformat() if event.first_timestamp else None,
            'last_timestamp': event.last_timestamp.isoformat() if event.last_timestamp else None,
            'count': event.count or 1
        }
    
    def _apply_pod_filters(self, pod_info: Dict, filters: Optional[Dict]) -> bool:
        """应用Pod过滤器"""
        if not filters:
            return True
        
        # 状态过滤
        if 'status' in filters and filters['status']:
            if pod_info['status'].lower() != filters['status'].lower():
                return False
        
        # 命名空间过滤
        if 'namespace' in filters and filters['namespace']:
            if pod_info['namespace'] != filters['namespace']:
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in pod_info['name'].lower():
                return False
        
        return True
    
    def _apply_deployment_filters(self, deployment_info: Dict, filters: Optional[Dict]) -> bool:
        """应用Deployment过滤器"""
        if not filters:
            return True
        
        # 命名空间过滤
        if 'namespace' in filters and filters['namespace']:
            if deployment_info['namespace'] != filters['namespace']:
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in deployment_info['name'].lower():
                return False
        
        return True
    
    def get_deployment_details(self, cluster_id: int, namespace: str, deployment_name: str) -> Dict[str, Any]:
        """获取Deployment详情"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            core_v1 = clients['core_v1']
            
            # 获取Deployment基本信息
            deployment = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            deployment_info = self._format_deployment_data(deployment)
            
            # 获取ReplicaSet信息
            selector_labels = deployment.spec.selector.match_labels if deployment.spec.selector else {}
            label_selector = ','.join([f"{k}={v}" for k, v in selector_labels.items()])
            
            if label_selector:
                replicasets = apps_v1.list_namespaced_replica_set(
                    namespace=namespace,
                    label_selector=label_selector
                )
                deployment_info['replicasets'] = [
                    self._format_replicaset_data(rs) for rs in replicasets.items
                ]
            else:
                deployment_info['replicasets'] = []
            
            # 获取Pod信息
            if label_selector:
                pods = core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=label_selector
                )
                deployment_info['pods'] = [
                    self._format_pod_data(pod) for pod in pods.items
                ]
            else:
                deployment_info['pods'] = []
            
            # 获取事件
            try:
                events = core_v1.list_namespaced_event(
                    namespace=namespace,
                    field_selector=f'involvedObject.name={deployment_name}'
                )
                deployment_info['events'] = [self._format_event_data(event) for event in events.items]
            except Exception:
                deployment_info['events'] = []
            
            return {
                'success': True,
                'data': deployment_info
            }
            
        except Exception as e:
            logger.error(f"Failed to get deployment details for {deployment_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    # ====== ReplicaSet管理 ======
    
    def list_replicasets(self, cluster_id: int, namespace: str = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取ReplicaSets列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            
            if namespace:
                replicasets = apps_v1.list_namespaced_replica_set(namespace=namespace)
            else:
                replicasets = apps_v1.list_replica_set_for_all_namespaces()
            
            replicasets_data = []
            for rs in replicasets.items:
                rs_info = self._format_replicaset_data(rs)
                
                # 应用过滤器
                if self._apply_replicaset_filters(rs_info, filters):
                    replicasets_data.append(rs_info)
            
            # 排序和分页
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                replicasets_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(replicasets_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(replicasets_data) + per_page - 1) // per_page,
                'data': replicasets_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list replicasets for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_replicaset_data(self, replicaset) -> Dict[str, Any]:
        """格式化ReplicaSet数据"""
        ready_replicas = replicaset.status.ready_replicas or 0
        replicas = replicaset.spec.replicas or 0
        
        return {
            'name': replicaset.metadata.name,
            'namespace': replicaset.metadata.namespace,
            'replicas': replicas,
            'ready_replicas': ready_replicas,
            'fully_labeled_replicas': replicaset.status.fully_labeled_replicas or 0,
            'available_replicas': replicaset.status.available_replicas or 0,
            'age': self._calculate_age(replicaset.metadata.creation_timestamp),
            'labels': replicaset.metadata.labels or {},
            'selector': replicaset.spec.selector.match_labels if replicaset.spec.selector else {},
            'created_at': replicaset.metadata.creation_timestamp.isoformat() if replicaset.metadata.creation_timestamp else None
        }
    
    def _apply_replicaset_filters(self, rs_info: Dict, filters: Optional[Dict]) -> bool:
        """应用ReplicaSet过滤器"""
        if not filters:
            return True
        
        # 命名空间过滤
        if 'namespace' in filters and filters['namespace']:
            if rs_info['namespace'] != filters['namespace']:
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in rs_info['name'].lower():
                return False
        
        return True
    
    # ====== DaemonSet管理 ======
    
    def list_daemonsets(self, cluster_id: int, namespace: str = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取DaemonSets列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            
            if namespace:
                daemonsets = apps_v1.list_namespaced_daemon_set(namespace=namespace)
            else:
                daemonsets = apps_v1.list_daemon_set_for_all_namespaces()
            
            daemonsets_data = []
            for ds in daemonsets.items:
                ds_info = self._format_daemonset_data(ds)
                
                # 应用过滤器
                if self._apply_daemonset_filters(ds_info, filters):
                    daemonsets_data.append(ds_info)
            
            # 排序和分页
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                daemonsets_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(daemonsets_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(daemonsets_data) + per_page - 1) // per_page,
                'data': daemonsets_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list daemonsets for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_daemonset_data(self, daemonset) -> Dict[str, Any]:
        """格式化DaemonSet数据"""
        return {
            'name': daemonset.metadata.name,
            'namespace': daemonset.metadata.namespace,
            'desired': daemonset.status.desired_number_scheduled or 0,
            'current': daemonset.status.current_number_scheduled or 0,
            'ready': daemonset.status.number_ready or 0,
            'up_to_date': daemonset.status.updated_number_scheduled or 0,
            'available': daemonset.status.number_available or 0,
            'age': self._calculate_age(daemonset.metadata.creation_timestamp),
            'labels': daemonset.metadata.labels or {},
            'selector': daemonset.spec.selector.match_labels if daemonset.spec.selector else {},
            'created_at': daemonset.metadata.creation_timestamp.isoformat() if daemonset.metadata.creation_timestamp else None
        }
    
    def _apply_daemonset_filters(self, ds_info: Dict, filters: Optional[Dict]) -> bool:
        """应用DaemonSet过滤器"""
        if not filters:
            return True
        
        # 命名空间过滤
        if 'namespace' in filters and filters['namespace']:
            if ds_info['namespace'] != filters['namespace']:
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in ds_info['name'].lower():
                return False
        
        return True
    
    # ====== StatefulSet管理 ======
    
    def list_statefulsets(self, cluster_id: int, namespace: str = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取StatefulSets列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            apps_v1 = clients['apps_v1']
            
            if namespace:
                statefulsets = apps_v1.list_namespaced_stateful_set(namespace=namespace)
            else:
                statefulsets = apps_v1.list_stateful_set_for_all_namespaces()
            
            statefulsets_data = []
            for sts in statefulsets.items:
                sts_info = self._format_statefulset_data(sts)
                
                # 应用过滤器
                if self._apply_statefulset_filters(sts_info, filters):
                    statefulsets_data.append(sts_info)
            
            # 排序和分页
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                statefulsets_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(statefulsets_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(statefulsets_data) + per_page - 1) // per_page,
                'data': statefulsets_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list statefulsets for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_statefulset_data(self, statefulset) -> Dict[str, Any]:
        """格式化StatefulSet数据"""
        ready_replicas = statefulset.status.ready_replicas or 0
        replicas = statefulset.spec.replicas or 0
        
        return {
            'name': statefulset.metadata.name,
            'namespace': statefulset.metadata.namespace,
            'replicas': replicas,
            'ready_replicas': ready_replicas,
            'current_replicas': statefulset.status.current_replicas or 0,
            'updated_replicas': statefulset.status.updated_replicas or 0,
            'age': self._calculate_age(statefulset.metadata.creation_timestamp),
            'labels': statefulset.metadata.labels or {},
            'selector': statefulset.spec.selector.match_labels if statefulset.spec.selector else {},
            'service_name': statefulset.spec.service_name,
            'created_at': statefulset.metadata.creation_timestamp.isoformat() if statefulset.metadata.creation_timestamp else None
        }
    
    def _apply_statefulset_filters(self, sts_info: Dict, filters: Optional[Dict]) -> bool:
        """应用StatefulSet过滤器"""
        if not filters:
            return True
        
        # 命名空间过滤
        if 'namespace' in filters and filters['namespace']:
            if sts_info['namespace'] != filters['namespace']:
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in sts_info['name'].lower():
                return False
        
        return True
    
    # ====== Job管理 ======
    
    def list_jobs(self, cluster_id: int, namespace: str = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取Jobs列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            batch_v1 = clients['batch_v1']
            
            if namespace:
                jobs = batch_v1.list_namespaced_job(namespace=namespace)
            else:
                jobs = batch_v1.list_job_for_all_namespaces()
            
            jobs_data = []
            for job in jobs.items:
                job_info = self._format_job_data(job)
                
                # 应用过滤器
                if self._apply_job_filters(job_info, filters):
                    jobs_data.append(job_info)
            
            # 排序和分页
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                jobs_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(jobs_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(jobs_data) + per_page - 1) // per_page,
                'data': jobs_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list jobs for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_job_data(self, job) -> Dict[str, Any]:
        """格式化Job数据"""
        status = 'Unknown'
        if job.status:
            if job.status.succeeded:
                status = 'Succeeded'
            elif job.status.failed:
                status = 'Failed'
            elif job.status.active:
                status = 'Running'
            else:
                status = 'Pending'
        
        return {
            'name': job.metadata.name,
            'namespace': job.metadata.namespace,
            'status': status,
            'completions': job.spec.completions,
            'parallelism': job.spec.parallelism,
            'active': job.status.active or 0,
            'succeeded': job.status.succeeded or 0,
            'failed': job.status.failed or 0,
            'start_time': job.status.start_time.isoformat() if job.status and job.status.start_time else None,
            'completion_time': job.status.completion_time.isoformat() if job.status and job.status.completion_time else None,
            'age': self._calculate_age(job.metadata.creation_timestamp),
            'labels': job.metadata.labels or {},
            'created_at': job.metadata.creation_timestamp.isoformat() if job.metadata.creation_timestamp else None
        }
    
    def _apply_job_filters(self, job_info: Dict, filters: Optional[Dict]) -> bool:
        """应用Job过滤器"""
        if not filters:
            return True
        
        # 命名空间过滤
        if 'namespace' in filters and filters['namespace']:
            if job_info['namespace'] != filters['namespace']:
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in job_info['name'].lower():
                return False
        
        return True
    
    # ====== CronJob管理 ======
    
    def list_cronjobs(self, cluster_id: int, namespace: str = None, filters: Optional[Dict] = None) -> Dict[str, Any]:
        """获取CronJobs列表"""
        try:
            clients = self.get_cluster_client(cluster_id)
            batch_v1 = clients['batch_v1']
            
            if namespace:
                cronjobs = batch_v1.list_namespaced_cron_job(namespace=namespace)
            else:
                cronjobs = batch_v1.list_cron_job_for_all_namespaces()
            
            cronjobs_data = []
            for cronjob in cronjobs.items:
                cronjob_info = self._format_cronjob_data(cronjob)
                
                # 应用过滤器
                if self._apply_cronjob_filters(cronjob_info, filters):
                    cronjobs_data.append(cronjob_info)
            
            # 排序和分页
            if filters and 'sort_by' in filters:
                reverse = filters.get('sort_order', 'asc').lower() == 'desc'
                sort_key = filters['sort_by']
                cronjobs_data.sort(key=lambda x: str(x.get(sort_key, '')), reverse=reverse)
            
            page = filters.get('page', 1) if filters else 1
            per_page = filters.get('per_page', 20) if filters else 20
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            
            return {
                'success': True,
                'total': len(cronjobs_data),
                'page': page,
                'per_page': per_page,
                'total_pages': (len(cronjobs_data) + per_page - 1) // per_page,
                'data': cronjobs_data[start_idx:end_idx]
            }
            
        except Exception as e:
            logger.error(f"Failed to list cronjobs for cluster {cluster_id}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _format_cronjob_data(self, cronjob) -> Dict[str, Any]:
        """格式化CronJob数据"""
        suspend = cronjob.spec.suspend if cronjob.spec.suspend is not None else False
        
        return {
            'name': cronjob.metadata.name,
            'namespace': cronjob.metadata.namespace,
            'schedule': cronjob.spec.schedule,
            'suspend': suspend,
            'active': len(cronjob.status.active) if cronjob.status and cronjob.status.active else 0,
            'last_schedule': cronjob.status.last_schedule_time.isoformat() if cronjob.status and cronjob.status.last_schedule_time else None,
            'successful_job_history_limit': cronjob.spec.successful_jobs_history_limit,
            'failed_job_history_limit': cronjob.spec.failed_jobs_history_limit,
            'age': self._calculate_age(cronjob.metadata.creation_timestamp),
            'labels': cronjob.metadata.labels or {},
            'created_at': cronjob.metadata.creation_timestamp.isoformat() if cronjob.metadata.creation_timestamp else None
        }
    
    def _apply_cronjob_filters(self, cronjob_info: Dict, filters: Optional[Dict]) -> bool:
        """应用CronJob过滤器"""
        if not filters:
            return True
        
        # 命名空间过滤
        if 'namespace' in filters and filters['namespace']:
            if cronjob_info['namespace'] != filters['namespace']:
                return False
        
        # 名称过滤
        if 'name' in filters and filters['name']:
            if filters['name'].lower() not in cronjob_info['name'].lower():
                return False
        
        return True
    
    # ====== Pod终端功能 ======
    
    def pod_exec_stream(self, cluster_id: int, namespace: str, pod_name: str, container: str = None, 
                       command: List[str] = None) -> Dict[str, Any]:
        """获取Pod exec流连接信息"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 默认命令
            if not command:
                command = ['/bin/sh', '-c', 'TERM=xterm-256color; export TERM; [ -x /bin/bash ] && ([ -x /usr/bin/script ] && /usr/bin/script -q -c "/bin/bash" /dev/null || exec /bin/bash) || exec /bin/sh']
            
            # 检查Pod是否存在且在运行
            try:
                pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
                if pod.status.phase != 'Running':
                    return {
                        'success': False,
                        'error': f'Pod {pod_name} is not running (status: {pod.status.phase})'
                    }
                
                # 获取容器列表
                if not container:
                    if pod.spec.containers:
                        container = pod.spec.containers[0].name
                    else:
                        return {
                            'success': False,
                            'error': 'No containers found in pod'
                        }
                
                # 验证容器存在
                container_names = [c.name for c in pod.spec.containers]
                if container not in container_names:
                    return {
                        'success': False,
                        'error': f'Container {container} not found. Available containers: {", ".join(container_names)}'
                    }
                
            except ApiException as e:
                if e.status == 404:
                    return {
                        'success': False,
                        'error': f'Pod {pod_name} not found'
                    }
                else:
                    raise
            
            # 返回连接信息供WebSocket使用
            return {
                'success': True,
                'data': {
                    'cluster_id': cluster_id,
                    'namespace': namespace,
                    'pod_name': pod_name,
                    'container': container,
                    'command': command,
                    'available_containers': container_names
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to prepare pod exec for {pod_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_pod_exec_ws_stream(self, cluster_id: int, namespace: str, pod_name: str, 
                                 container: str = None, command: List[str] = None):
        """创建Pod exec WebSocket流（用于WebSocket处理器）"""
        try:
            logger.info(f"创建Pod exec流: cluster={cluster_id}, namespace={namespace}, pod={pod_name}, container={container}")
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            
            # 默认命令 
            if not command:
                command = ['/bin/sh', '-c', 'TERM=xterm-256color; export TERM; [ -x /bin/bash ] && ([ -x /usr/bin/script ] && /usr/bin/script -q -c "/bin/bash" /dev/null || exec /bin/bash) || exec /bin/sh']
            
            # 使用kubernetes stream包处理exec
            from kubernetes.stream import stream
            
            exec_stream = stream(
                core_v1.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=namespace,
                container=container,
                command=command,
                stderr=True,
                stdin=True,
                stdout=True,
                tty=True,
                _preload_content=False
            )
            
            return exec_stream
            
        except Exception as e:
            logger.error(f"Failed to create pod exec stream for {pod_name}: {str(e)}")
            raise
    
    def get_pod_metrics(self, cluster_id: int, namespace: str, pod_name: str) -> Dict[str, Any]:
        """获取Pod监控指标"""
        try:
            clients = self.get_cluster_client(cluster_id)
            core_v1 = clients['core_v1']
            custom_objects = clients['custom_objects']
            
            # 获取Pod基本信息
            pod = core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            
            # 尝试获取 metrics-server 数据
            metrics_data = None
            try:
                # 获取Pod metrics
                pod_metrics = custom_objects.get_namespaced_custom_object(
                    group="metrics.k8s.io",
                    version="v1beta1",
                    namespace=namespace,
                    plural="pods",
                    name=pod_name
                )
                metrics_data = self._parse_pod_metrics(pod_metrics)
            except Exception as metrics_error:
                # Metrics-server 不可用或Pod没有metrics数据，使用资源请求/限制作为基准数据
                logger.debug(f"Metrics API unavailable for pod {pod_name}, using resource baseline: {str(metrics_error)}")
                metrics_data = self._get_pod_resource_baseline(pod)
            
            # 获取节点信息用于磁盘统计
            node_name = pod.spec.node_name
            node_metrics = None
            if node_name:
                try:
                    node_metrics = custom_objects.get_cluster_custom_object(
                        group="metrics.k8s.io",
                        version="v1beta1",
                        plural="nodes",
                        name=node_name
                    )
                except Exception:
                    logger.debug(f"Could not get node metrics for {node_name}")
            
            # 组装监控数据
            monitoring_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'pod_name': pod_name,
                'namespace': namespace,
                'node_name': node_name,
                'status': pod.status.phase if pod.status else 'Unknown',
                'cpu': metrics_data.get('cpu', {}),
                'memory': metrics_data.get('memory', {}),
                'disk': self._get_pod_disk_metrics(pod, node_metrics, cluster_id),
                'network': self._get_pod_network_metrics(pod),
                'containers': self._get_container_metrics(pod, metrics_data.get('containers', [])),
                'resource_quotas': self._get_pod_resource_quotas(pod)
            }
            
            return {
                'success': True,
                'data': monitoring_data
            }
            
        except Exception as e:
            logger.error(f"Failed to get pod metrics for {pod_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _parse_pod_metrics(self, pod_metrics: Dict) -> Dict[str, Any]:
        """解析Pod metrics数据"""
        containers = pod_metrics.get('containers', [])
        
        total_cpu_usage = 0  # 毫核心
        total_memory_usage = 0  # 字节
        container_metrics = []
        
        for container in containers:
            usage = container.get('usage', {})
            
            # 解析CPU使用量
            cpu_usage = self._parse_cpu_value(usage.get('cpu', '0'))
            total_cpu_usage += cpu_usage
            
            # 解析内存使用量  
            memory_usage = self._parse_memory_bytes(usage.get('memory', '0'))
            total_memory_usage += memory_usage
            
            container_metrics.append({
                'name': container.get('name'),
                'cpu_usage': cpu_usage,
                'memory_usage': memory_usage
            })
        
        return {
            'cpu': {
                'usage_millicores': total_cpu_usage,
                'usage_cores': round(total_cpu_usage / 1000, 3)
            },
            'memory': {
                'usage_bytes': total_memory_usage,
                'usage_mi': round(total_memory_usage / (1024 * 1024), 1)
            },
            'containers': container_metrics
        }
    
    def _parse_memory_bytes(self, memory_str: str) -> int:
        """解析内存值为字节"""
        if not memory_str or memory_str == "0":
            return 0
            
        try:
            memory_str = memory_str.strip()
            if memory_str.endswith('Ki'):
                return int(memory_str[:-2]) * 1024
            elif memory_str.endswith('Mi'):
                return int(memory_str[:-2]) * 1024 * 1024
            elif memory_str.endswith('Gi'):
                return int(memory_str[:-2]) * 1024 * 1024 * 1024
            elif memory_str.endswith('Ti'):
                return int(memory_str[:-2]) * 1024 * 1024 * 1024 * 1024
            else:
                # 假设是字节
                return int(memory_str)
        except (ValueError, AttributeError):
            return 0
    
    def _get_pod_resource_baseline(self, pod) -> Dict[str, Any]:
        """获取Pod资源基准数据（用于metrics不可用时）"""
        total_cpu_requests = 0
        total_memory_requests = 0
        total_cpu_limits = 0
        total_memory_limits = 0
        
        if pod.spec and pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources:
                    if container.resources.requests:
                        cpu_req = container.resources.requests.get('cpu', '0')
                        memory_req = container.resources.requests.get('memory', '0')
                        total_cpu_requests += self._parse_cpu_value(cpu_req)
                        total_memory_requests += self._parse_memory_value(memory_req)
                    
                    if container.resources.limits:
                        cpu_limit = container.resources.limits.get('cpu', '0')
                        memory_limit = container.resources.limits.get('memory', '0')
                        total_cpu_limits += self._parse_cpu_value(cpu_limit)
                        total_memory_limits += self._parse_memory_value(memory_limit)
        
        return {
            'cpu': {
                'usage_millicores': int(total_cpu_requests * 0.7),  # 估算70%使用率
                'usage_cores': round((total_cpu_requests * 0.7) / 1000, 3),
                'requests_millicores': total_cpu_requests,
                'limits_millicores': total_cpu_limits
            },
            'memory': {
                'usage_bytes': int(total_memory_requests * 1024 * 1024 * 0.6),  # 估算60%使用率
                'usage_mi': int(total_memory_requests * 0.6),
                'requests_mi': total_memory_requests,
                'limits_mi': total_memory_limits
            }
        }
    
    def _get_pod_disk_metrics(self, pod, node_metrics: Dict = None, cluster_id: int = None) -> Dict[str, Any]:
        """获取Pod磁盘指标"""
        disk_data = {
            'volumes': [],
            'total_usage_bytes': 0,
            'ephemeral_storage': {}
        }
        
        if pod.spec and pod.spec.volumes:
            for volume in pod.spec.volumes:
                volume_info = {
                    'name': volume.name,
                    'type': self._get_volume_type(volume),
                    'size_estimate': 'Unknown'
                }
                
                # 尝试从PVC获取大小
                if volume.persistent_volume_claim and cluster_id:
                    try:
                        clients = self.get_cluster_client(cluster_id)
                        core_v1 = clients['core_v1']
                        pvc = core_v1.read_namespaced_persistent_volume_claim(
                            name=volume.persistent_volume_claim.claim_name,
                            namespace=pod.metadata.namespace
                        )
                        if pvc.spec.resources and pvc.spec.resources.requests:
                            storage_request = pvc.spec.resources.requests.get('storage', 'Unknown')
                            volume_info['size_estimate'] = storage_request
                    except Exception:
                        pass
                
                disk_data['volumes'].append(volume_info)
        
        # 临时存储使用情况
        if pod.spec and pod.spec.containers:
            ephemeral_requests = 0
            for container in pod.spec.containers:
                if container.resources and container.resources.requests:
                    ephemeral = container.resources.requests.get('ephemeral-storage', '0')
                    ephemeral_requests += self._parse_memory_value(ephemeral)  # 复用内存解析
            
            disk_data['ephemeral_storage'] = {
                'requests_mi': ephemeral_requests,
                'estimated_usage_mi': int(ephemeral_requests * 0.4)  # 估算40%使用率
            }
        
        return disk_data
    
    def _get_volume_type(self, volume) -> str:
        """获取存储卷类型"""
        if volume.persistent_volume_claim:
            return 'PersistentVolumeClaim'
        elif volume.config_map:
            return 'ConfigMap'
        elif volume.secret:
            return 'Secret'
        elif volume.empty_dir:
            return 'EmptyDir'
        elif volume.host_path:
            return 'HostPath'
        else:
            return 'Other'
    
    def _get_pod_network_metrics(self, pod) -> Dict[str, Any]:
        """获取Pod网络指标（基础版本）"""
        network_data = {
            'pod_ip': pod.status.pod_ip if pod.status else None,
            'host_ip': pod.status.host_ip if pod.status else None,
            'ports': []
        }
        
        if pod.spec and pod.spec.containers:
            for container in pod.spec.containers:
                if container.ports:
                    for port in container.ports:
                        network_data['ports'].append({
                            'container': container.name,
                            'port': port.container_port,
                            'protocol': port.protocol or 'TCP',
                            'name': port.name
                        })
        
        return network_data
    
    def _get_container_metrics(self, pod, container_metrics: List) -> List[Dict]:
        """获取容器级别的监控数据"""
        containers_data = []
        
        if pod.spec and pod.spec.containers:
            for container in pod.spec.containers:
                container_data = {
                    'name': container.name,
                    'image': container.image,
                    'resources': {
                        'requests': {},
                        'limits': {}
                    },
                    'metrics': {}
                }
                
                # 获取资源配置
                if container.resources:
                    if container.resources.requests:
                        container_data['resources']['requests'] = dict(container.resources.requests)
                    if container.resources.limits:
                        container_data['resources']['limits'] = dict(container.resources.limits)
                
                # 匹配监控数据
                for metrics in container_metrics:
                    if metrics.get('name') == container.name:
                        container_data['metrics'] = {
                            'cpu_usage_millicores': metrics.get('cpu_usage', 0),
                            'memory_usage_bytes': metrics.get('memory_usage', 0)
                        }
                        break
                
                containers_data.append(container_data)
        
        return containers_data
    
    def _get_pod_resource_quotas(self, pod) -> Dict[str, Any]:
        """获取Pod资源配额信息"""
        quota_data = {
            'cpu': {'requests': 0, 'limits': 0},
            'memory': {'requests': 0, 'limits': 0},
            'usage_percentages': {}
        }
        
        if pod.spec and pod.spec.containers:
            for container in pod.spec.containers:
                if container.resources:
                    if container.resources.requests:
                        cpu_req = self._parse_cpu_value(container.resources.requests.get('cpu', '0'))
                        memory_req = self._parse_memory_value(container.resources.requests.get('memory', '0'))
                        quota_data['cpu']['requests'] += cpu_req
                        quota_data['memory']['requests'] += memory_req
                    
                    if container.resources.limits:
                        cpu_limit = self._parse_cpu_value(container.resources.limits.get('cpu', '0'))
                        memory_limit = self._parse_memory_value(container.resources.limits.get('memory', '0'))
                        quota_data['cpu']['limits'] += cpu_limit
                        quota_data['memory']['limits'] += memory_limit
        
        return quota_data

    def get_pod_metrics_history(self, cluster_id: int, namespace: str, pod_name: str, 
                               duration_minutes: int = 60) -> Dict[str, Any]:
        """获取Pod历史监控数据（模拟实现）"""
        try:
            # 获取当前指标作为基准
            current_metrics = self.get_pod_metrics(cluster_id, namespace, pod_name)
            
            if not current_metrics['success']:
                return current_metrics
            
            # 生成历史数据点（每分钟一个数据点）
            history_points = []
            current_data = current_metrics['data']
            base_cpu = current_data['cpu'].get('usage_millicores', 100)
            base_memory = current_data['memory'].get('usage_bytes', 100 * 1024 * 1024)
            
            import random
            from datetime import datetime, timedelta
            
            for i in range(duration_minutes):
                timestamp = datetime.utcnow() - timedelta(minutes=duration_minutes - i)
                
                # 模拟波动的监控数据
                cpu_variation = random.uniform(0.8, 1.2)  # ±20% 波动
                memory_variation = random.uniform(0.9, 1.1)  # ±10% 波动
                
                history_points.append({
                    'timestamp': timestamp.isoformat(),
                    'cpu_millicores': int(base_cpu * cpu_variation),
                    'memory_bytes': int(base_memory * memory_variation),
                    'cpu_percentage': round(base_cpu * cpu_variation / 10, 1),  # 假设总量为10核
                    'memory_percentage': round(base_memory * memory_variation / (2 * 1024**3) * 100, 1)  # 假设总量为2GB
                })
            
            return {
                'success': True,
                'data': {
                    'pod_name': pod_name,
                    'namespace': namespace,
                    'duration_minutes': duration_minutes,
                    'data_points': history_points,
                    'current_metrics': current_data
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get pod metrics history for {pod_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def clear_cache(self, cluster_id: Optional[int] = None):
        """清除缓存"""
        if cluster_id:
            cluster_key = f"k8s_cluster_{cluster_id}"
            if cluster_key in self.clients:
                del self.clients[cluster_key]
            
            cache_keys = [k for k in self.resource_cache.keys() if k.endswith(f"_{cluster_id}")]
            for key in cache_keys:
                if key in self.resource_cache:
                    del self.resource_cache[key]
                if key in self.last_cache_update:
                    del self.last_cache_update[key]
        else:
            self.clients.clear()
            self.resource_cache.clear()
            self.last_cache_update.clear()

# 全局服务实例
k8s_service = None

def get_k8s_service():
    """获取K8s服务实例"""
    global k8s_service
    if k8s_service is None:
        k8s_service = K8sService()
    return k8s_service