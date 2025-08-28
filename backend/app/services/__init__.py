"""
服务层包
"""
from .openstack_service import get_openstack_service

# 直接导出服务实例
openstack_service = get_openstack_service()

__all__ = ['openstack_service', 'get_openstack_service']