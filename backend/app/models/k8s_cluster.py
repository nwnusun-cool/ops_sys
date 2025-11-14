"""
Kubernetes集群管理数据模型
"""
import json
import logging
import yaml
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from flask_login import current_user
from .base import db, BaseModel
from app.utils.crypto import encrypt_data, decrypt_data

logger = logging.getLogger(__name__)

class K8sCluster(BaseModel):
    """
    Kubernetes集群模型
    """
    __tablename__ = 'k8s_clusters'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False, comment='集群名称')
    description = Column(Text, comment='集群描述')
    
    # 连接配置
    api_server = Column(String(255), nullable=False, comment='API Server地址')
    kubeconfig_content = Column(Text, comment='加密存储的kubeconfig内容')
    auth_type = Column(String(20), default='kubeconfig', comment='认证类型: kubeconfig, token, cert')
    
    # 集群信息
    k8s_version = Column(String(50), comment='Kubernetes版本')
    cluster_status = Column(String(20), default='unknown', comment='集群状态: connected, failed, unknown')
    
    # 资源统计
    node_count = Column(Integer, default=0, comment='节点数量')
    namespace_count = Column(Integer, default=0, comment='命名空间数量')
    pod_count = Column(Integer, default=0, comment='Pod数量')
    service_count = Column(Integer, default=0, comment='Service数量')
    deployment_count = Column(Integer, default=0, comment='Deployment数量')
    
    # 状态和监控
    last_connection_test = Column(DateTime, comment='最后连接测试时间')
    error_message = Column(Text, comment='错误信息')
    is_active = Column(Boolean, default=True, comment='是否启用')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    def __repr__(self):
        return f'<K8sCluster {self.name}>'
    
    def set_kubeconfig(self, kubeconfig_data: Dict[str, Any]):
        """设置kubeconfig配置（加密存储）"""
        try:
            if isinstance(kubeconfig_data, str):
                kubeconfig_content = kubeconfig_data
            else:
                kubeconfig_content = json.dumps(kubeconfig_data, indent=2)
            
            # 加密存储
            self.kubeconfig_content = encrypt_data(kubeconfig_content)
            logger.info(f"Kubeconfig set for cluster {self.name}")
            
        except Exception as e:
            logger.error(f"Failed to set kubeconfig for cluster {self.name}: {str(e)}")
            raise
    
    def get_kubeconfig(self) -> Optional[str]:
        """获取解密后的kubeconfig内容"""
        try:
            if not self.kubeconfig_content:
                return None
            
            return decrypt_data(self.kubeconfig_content)
            
        except Exception as e:
            logger.error(f"Failed to decrypt kubeconfig for cluster {self.name}: {str(e)}")
            return None
    
    def get_kubeconfig_dict(self) -> Optional[Dict]:
        """获取kubeconfig字典格式"""
        try:
            kubeconfig_str = self.get_kubeconfig()
            if not kubeconfig_str:
                return None
                
            # 尝试解析JSON格式
            try:
                return json.loads(kubeconfig_str)
            except json.JSONDecodeError:
                # 如果不是JSON格式，可能是YAML格式
                import yaml
                return yaml.safe_load(kubeconfig_str)
                
        except Exception as e:
            logger.error(f"Failed to parse kubeconfig for cluster {self.name}: {str(e)}")
            return None
    
    def test_connection(self) -> Dict[str, Any]:
        """测试集群连接"""
        try:
            from app.services.k8s_service import get_k8s_service
            k8s_service = get_k8s_service()
            
            result = k8s_service.test_cluster_connection(self.id)
            
            # 更新连接状态
            self.cluster_status = 'connected' if result['success'] else 'failed'
            self.last_connection_test = datetime.utcnow()
            self.error_message = result.get('error') if not result['success'] else None
            
            if result['success']:
                # 更新集群信息
                self.k8s_version = result.get('version')
                
            db.session.commit()
            
            return result
            
        except Exception as e:
            self.cluster_status = 'failed'
            self.last_connection_test = datetime.utcnow()
            self.error_message = str(e)
            db.session.commit()
            
            logger.error(f"Connection test failed for cluster {self.name}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def update_resource_counts(self, nodes: int = None, namespaces: int = None, 
                             pods: int = None, services: int = None, 
                             deployments: int = None):
        """更新资源计数"""
        try:
            if nodes is not None:
                self.node_count = nodes
            if namespaces is not None:
                self.namespace_count = namespaces
            if pods is not None:
                self.pod_count = pods
            if services is not None:
                self.service_count = services
            if deployments is not None:
                self.deployment_count = deployments
                
            self.updated_at = datetime.utcnow()
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Failed to update resource counts for cluster {self.name}: {str(e)}")
    
    def to_dict(self, include_kubeconfig: bool = False) -> Dict[str, Any]:
        """转换为字典格式"""
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'api_server': self.api_server,
            'auth_type': self.auth_type,
            'k8s_version': self.k8s_version,
            'cluster_status': self.cluster_status,
            'node_count': self.node_count,
            'namespace_count': self.namespace_count,
            'pod_count': self.pod_count,
            'service_count': self.service_count,
            'deployment_count': self.deployment_count,
            'last_connection_test': self.last_connection_test.isoformat() if self.last_connection_test else None,
            'error_message': self.error_message,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        # 根据用户权限决定是否包含kubeconfig
        if include_kubeconfig and hasattr(current_user, 'has_role'):
            if current_user.has_role(['super_admin', 'admin']):
                kubeconfig_dict = self.get_kubeconfig_dict()
                if kubeconfig_dict:
                    data['kubeconfig'] = kubeconfig_dict
        
        return data
    
    @classmethod
    def get_active_clusters(cls):
        """获取活跃的集群列表"""
        return cls.query.filter_by(is_active=True).all()
    
    @classmethod
    def get_by_name(cls, name: str):
        """通过名称获取集群"""
        return cls.query.filter_by(name=name).first()