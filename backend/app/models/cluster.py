"""
OpenStack集群模型
"""
from datetime import datetime
from .base import db
from app.utils.config_manager import config_manager

class OpenstackCluster(db.Model):
    """OpenStack集群模型"""
    
    __tablename__ = 'openstack_clusters'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    auth_url = db.Column(db.String(255), nullable=False)
    
    # 加密存储的凭据信息
    encrypted_credentials = db.Column(db.Text, nullable=False)
    
    # 连接配置
    region_name = db.Column(db.String(100), default='RegionOne')
    api_version = db.Column(db.String(20), default='3')
    
    # 状态和元数据
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_connection_test = db.Column(db.DateTime)
    connection_status = db.Column(db.Enum('unknown', 'connected', 'failed', name='connection_status'), 
                                  default='unknown')
    error_message = db.Column(db.Text)
    
    # 统计信息
    instance_count = db.Column(db.Integer, default=0)
    volume_count = db.Column(db.Integer, default=0)
    network_count = db.Column(db.Integer, default=0)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联关系
    operation_logs = db.relationship('OperationLog', backref='cluster', lazy='dynamic')
    
    def set_credentials(self, credentials_dict):
        """设置加密的凭据"""
        self.encrypted_credentials = config_manager.encrypt_credentials(credentials_dict)
    
    def get_credentials(self):
        """获取解密的凭据"""
        if not self.encrypted_credentials:
            return {}
        return config_manager.decrypt_credentials(self.encrypted_credentials)
    
    def get_auth_config(self):
        """获取OpenStack认证配置"""
        credentials = self.get_credentials()
        
        auth_config = {
            'auth_url': self.auth_url,
            'username': credentials.get('username'),
            'password': credentials.get('password'),
            'project_name': credentials.get('project_name'),
            'user_domain_name': credentials.get('user_domain_name', 'Default'),
            'project_domain_name': credentials.get('project_domain_name', 'Default')
        }
        
        return auth_config
    
    def test_connection(self):
        """测试连接状态"""
        try:
            from app.services.openstack_service import openstack_service
            result = openstack_service.test_cluster_connection(self.id)
            
            self.last_connection_test = datetime.utcnow()
            self.connection_status = 'connected' if result['success'] else 'failed'
            self.error_message = result.get('error', None)
            
            db.session.commit()
            return result
            
        except Exception as e:
            self.last_connection_test = datetime.utcnow()
            self.connection_status = 'failed'
            self.error_message = str(e)
            db.session.commit()
            
            return {'success': False, 'error': str(e)}
    
    def update_resource_counts(self, instances=None, volumes=None, networks=None):
        """更新资源统计"""
        if instances is not None:
            self.instance_count = instances
        if volumes is not None:
            self.volume_count = volumes
        if networks is not None:
            self.network_count = networks
        
        self.updated_at = datetime.utcnow()
        db.session.commit()
    
    def to_dict(self, include_credentials=False):
        """转换为字典"""
        data = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'auth_url': self.auth_url,
            'region_name': self.region_name,
            'api_version': self.api_version,
            'is_active': self.is_active,
            'connection_status': self.connection_status,
            'last_connection_test': self.last_connection_test.isoformat() if self.last_connection_test else None,
            'error_message': self.error_message,
            'instance_count': self.instance_count,
            'volume_count': self.volume_count,
            'network_count': self.network_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
        
        if include_credentials:
            data['credentials'] = self.get_credentials()
        
        return data
    
    @classmethod
    def get_active_clusters(cls):
        """获取所有活跃的集群"""
        return cls.query.filter_by(is_active=True).all()
    
    @classmethod
    def get_cluster_by_name(cls, name):
        """根据名称获取集群"""
        return cls.query.filter_by(name=name).first()
    
    def __repr__(self):
        return f'<OpenstackCluster {self.name}>'