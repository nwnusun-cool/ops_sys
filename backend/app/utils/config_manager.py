"""
配置管理工具
处理OpenStack集群配置的加密存储和解密
"""
import json
import os
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
import base64
from flask import current_app

class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self._fernet = None
    
    @property
    def fernet(self):
        """获取加密器实例"""
        if self._fernet is None:
            key = self._get_or_create_key()
            self._fernet = Fernet(key)
        return self._fernet
    
    def _get_or_create_key(self) -> bytes:
        """获取或创建加密密钥"""
        key_file = os.path.join(current_app.instance_path, 'secret.key')
        
        # 确保目录存在
        os.makedirs(os.path.dirname(key_file), exist_ok=True)
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # 生成新密钥
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            return key
    
    def encrypt_credentials(self, credentials: Dict[str, Any]) -> str:
        """加密OpenStack凭据"""
        json_str = json.dumps(credentials)
        encrypted_data = self.fernet.encrypt(json_str.encode())
        return base64.b64encode(encrypted_data).decode()
    
    def decrypt_credentials(self, encrypted_credentials: str) -> Dict[str, Any]:
        """解密OpenStack凭据"""
        try:
            encrypted_data = base64.b64decode(encrypted_credentials.encode())
            decrypted_data = self.fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            current_app.logger.error(f"Failed to decrypt credentials: {e}")
            return {}
    
    def load_openstack_config(self, config_file: Optional[str] = None) -> Dict[str, Any]:
        """加载OpenStack配置文件（兼容旧版本）"""
        if config_file is None:
            config_file = current_app.config.get('OPENSTACK_CONFIG_FILE')
        
        config_path = os.path.join(current_app.instance_path, config_file)
        
        if not os.path.exists(config_path):
            # 如果新配置文件不存在，尝试从旧配置迁移
            old_config_path = os.path.join(
                os.path.dirname(current_app.instance_path), 
                'app', 'config', 'config.json'
            )
            if os.path.exists(old_config_path):
                return self._migrate_old_config(old_config_path, config_path)
            return {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            current_app.logger.error(f"Failed to load config: {e}")
            return {}
    
    def save_openstack_config(self, config: Dict[str, Any], config_file: Optional[str] = None):
        """保存OpenStack配置"""
        if config_file is None:
            config_file = current_app.config.get('OPENSTACK_CONFIG_FILE')
        
        config_path = os.path.join(current_app.instance_path, config_file)
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            current_app.logger.error(f"Failed to save config: {e}")
            raise
    
    def _migrate_old_config(self, old_path: str, new_path: str) -> Dict[str, Any]:
        """迁移旧配置文件"""
        try:
            with open(old_path, 'r', encoding='utf-8') as f:
                old_config = json.load(f)
            
            # 转换配置格式
            new_config = {
                'version': '2.0',
                'clusters': {},
                'settings': {}
            }
            
            # 迁移OpenStack环境配置
            if 'openstack_environments' in old_config:
                for name, env_config in old_config['openstack_environments'].items():
                    new_config['clusters'][name] = {
                        'name': name,
                        'description': f'从旧版本迁移的集群 {name}',
                        'auth_url': env_config.get('auth_url'),
                        'credentials': self.encrypt_credentials({
                            'username': env_config.get('username'),
                            'password': env_config.get('password'),
                            'project_name': env_config.get('project_name'),
                            'user_domain_name': env_config.get('user_domain_name', 'Default'),
                            'project_domain_name': env_config.get('project_domain_name', 'Default')
                        }),
                        'is_active': True
                    }
            
            # 迁移安全设置
            if 'security' in old_config:
                new_config['settings']['security'] = old_config['security']
            
            if 'page_password' in old_config:
                new_config['settings']['page_password'] = old_config['page_password']
            
            # 保存新配置
            self.save_openstack_config(new_config, new_path.split('/')[-1])
            
            current_app.logger.info(f"Successfully migrated config from {old_path} to {new_path}")
            return new_config
            
        except Exception as e:
            current_app.logger.error(f"Failed to migrate config: {e}")
            return {}

# 全局配置管理器实例
config_manager = ConfigManager()