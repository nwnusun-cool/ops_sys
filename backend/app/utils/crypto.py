"""
加密解密工具模块
用于敏感数据的加密存储
"""
import base64
import json
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask import current_app
import os

def get_encryption_key():
    """获取加密密钥"""
    # 从环境变量或配置中获取密钥
    secret_key = current_app.config.get('SECRET_KEY', 'default-secret-key-change-this')
    
    # 使用PBKDF2生成固定的加密密钥
    salt = b'stable_salt_for_k8s_ops'  # 在生产环境中应该使用随机salt
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
    return key

def encrypt_data(data: str) -> str:
    """加密数据"""
    try:
        key = get_encryption_key()
        f = Fernet(key)
        encrypted_data = f.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted_data).decode()
    except Exception as e:
        raise Exception(f"Encryption failed: {str(e)}")

def decrypt_data(encrypted_data: str) -> str:
    """解密数据"""
    try:
        key = get_encryption_key()
        f = Fernet(key)
        decoded_data = base64.urlsafe_b64decode(encrypted_data.encode())
        decrypted_data = f.decrypt(decoded_data)
        return decrypted_data.decode()
    except Exception as e:
        raise Exception(f"Decryption failed: {str(e)}")