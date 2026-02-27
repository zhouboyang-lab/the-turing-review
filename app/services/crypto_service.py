"""API Key 加密/解密服务 — 用于安全存储社区审稿人的 API Key。"""

import base64
import hashlib
from cryptography.fernet import Fernet
from app.config import GUEST_API_KEY_SECRET


def _get_fernet() -> Fernet:
    """从配置的 secret 派生 Fernet key。"""
    key = hashlib.sha256(GUEST_API_KEY_SECRET.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_api_key(plain_key: str) -> str:
    if not plain_key:
        return ""
    return _get_fernet().encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    if not encrypted_key:
        return ""
    return _get_fernet().decrypt(encrypted_key.encode()).decode()
