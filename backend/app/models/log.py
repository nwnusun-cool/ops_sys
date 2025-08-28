"""
操作日志模型
"""
from datetime import datetime
from .base import db

class OperationLog(db.Model):
    """操作日志模型"""
    
    __tablename__ = 'operation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # 关联的用户和集群
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    cluster_id = db.Column(db.Integer, db.ForeignKey('openstack_clusters.id'))
    
    # 操作信息
    operation_type = db.Column(db.String(50), nullable=False)  # create, delete, update, start, stop等
    resource_type = db.Column(db.String(50), nullable=False)   # instance, volume, network等
    resource_id = db.Column(db.String(255))                    # 资源ID
    resource_name = db.Column(db.String(255))                  # 资源名称
    
    # 操作详情
    action = db.Column(db.String(100))                         # 具体的操作动作
    details = db.Column(db.JSON)                               # 详细参数和信息
    
    # 操作结果
    result = db.Column(db.Enum('success', 'failed', 'pending', name='operation_result'), 
                       nullable=False)
    error_message = db.Column(db.Text)                         # 错误信息
    
    # 请求信息
    ip_address = db.Column(db.String(45))                      # 客户端IP地址
    user_agent = db.Column(db.Text)                            # 用户代理
    
    # 时间信息
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    duration_ms = db.Column(db.Integer)                        # 操作耗时（毫秒）
    
    def __init__(self, **kwargs):
        super(OperationLog, self).__init__(**kwargs)
    
    @classmethod
    def create_log(cls, user_id, operation_type, resource_type, 
                   cluster_id=None, resource_id=None, resource_name=None,
                   action=None, details=None, result='pending',
                   error_message=None, ip_address=None, user_agent=None):
        """创建操作日志"""
        log = cls(
            user_id=user_id,
            cluster_id=cluster_id,
            operation_type=operation_type,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            action=action,
            details=details,
            result=result,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent
        )
        db.session.add(log)
        db.session.commit()
        return log
    
    def update_result(self, result, error_message=None, duration_ms=None):
        """更新操作结果"""
        self.result = result
        if error_message:
            self.error_message = error_message
        if duration_ms:
            self.duration_ms = duration_ms
        db.session.commit()
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'cluster_id': self.cluster_id,
            'cluster_name': self.cluster.name if self.cluster else None,
            'operation_type': self.operation_type,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'resource_name': self.resource_name,
            'action': self.action,
            'details': self.details,
            'result': self.result,
            'error_message': self.error_message,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'duration_ms': self.duration_ms
        }
    
    @classmethod
    def get_user_logs(cls, user_id, limit=100):
        """获取用户的操作日志"""
        return cls.query.filter_by(user_id=user_id)\
                       .order_by(cls.created_at.desc())\
                       .limit(limit).all()
    
    @classmethod
    def get_resource_logs(cls, resource_type, resource_id, limit=50):
        """获取资源的操作日志"""
        return cls.query.filter_by(resource_type=resource_type, resource_id=resource_id)\
                       .order_by(cls.created_at.desc())\
                       .limit(limit).all()
    
    @classmethod
    def get_cluster_logs(cls, cluster_id, limit=100):
        """获取集群的操作日志"""
        return cls.query.filter_by(cluster_id=cluster_id)\
                       .order_by(cls.created_at.desc())\
                       .limit(limit).all()
    
    @classmethod
    def log_operation(cls, user_id, operation_type, operation_object, result, details=None, cluster_id=None):
        """简化的日志记录方法（与API路由兼容）"""
        # 解析operation_object
        if ':' in operation_object:
            resource_type, resource_name = operation_object.split(':', 1)
        else:
            resource_type = 'unknown'
            resource_name = operation_object
        
        log = cls(
            user_id=user_id,
            cluster_id=cluster_id,
            operation_type=operation_type,
            resource_type=resource_type,
            resource_name=resource_name,
            result=result,
            details={'description': details} if isinstance(details, str) else details
        )
        db.session.add(log)
        db.session.commit()
        return log
    
    def __repr__(self):
        return f'<OperationLog {self.operation_type}:{self.resource_type}>'