"""
security —— 认证与鉴权核心（阶段2 · 登录/角色管理）

仅依赖 Python 标准库（hashlib / hmac / secrets / base64），无需额外安装三方库，
规避 Python 3.13 下 bcrypt / passlib 的 C 扩展兼容问题。

提供：
    1. 密码哈希   PBKDF2-HMAC-SHA256，随机盐，格式
                  pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    2. 会话令牌   标准 JWT（HS256），格式 `header.payload.signature`
                  header  = {"alg":"HS256","typ":"JWT"}
                  payload = {"sub","role","iat","exp"}，服务端无需存 token
    3. FastAPI 依赖
                  get_current_user   从 Authorization: Bearer <token> 解析当前用户
                  require_roles     角色守卫，如 require_roles('it_admin')

角色定义（管理层 / 运维岗 / IT管理员）见 config.settings.ROLES。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config.settings import AUTH_CONFIG
from database.database import get_db
from database.models import User

_SECRET = AUTH_CONFIG['secret_key'].encode('utf-8')
_ITERATIONS = int(AUTH_CONFIG['pbkdf2_iterations'])


# ============================================================
# 密码哈希
# ============================================================
def hash_password(password: str) -> str:
    """生成 PBKDF2-HMAC-SHA256 哈希（含随机盐 + 迭代次数，自描述格式）"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), bytes.fromhex(salt), _ITERATIONS
    )
    return f'pbkdf2_sha256${_ITERATIONS}${salt}${dk.hex()}'


def verify_password(password: str, stored: str) -> bool:
    """校验明文密码是否匹配已存储哈希（常量时间比较，防时序攻击）"""
    try:
        algo, iters, salt, expected = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        dk = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), bytes.fromhex(salt), int(iters)
        )
        return hmac.compare_digest(dk.hex(), expected)
    except Exception:
        return False


# ============================================================
# 会话令牌（无状态 HMAC 签名）
# ============================================================
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64url_decode(s: str) -> bytes:
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


# JWT 固定头（HS256，所有令牌共用，避免每次重复编码）
_JWT_HEADER = _b64url(
    json.dumps({'alg': AUTH_CONFIG['algorithm'], 'typ': 'JWT'}, separators=(',', ':')).encode('utf-8')
)


def _sign(signing_input: str) -> str:
    """对 `header.payload` 计算 HMAC-SHA256 签名（base64url）"""
    return _b64url(hmac.new(_SECRET, signing_input.encode('ascii'), hashlib.sha256).digest())


def create_access_token(account: str, role: str, expire_seconds: Optional[int] = None) -> str:
    """签发标准 JWT（header.payload.signature，HS256）"""
    expire_sec = expire_seconds or AUTH_CONFIG['access_token_expire_seconds']
    now = int(time.time())
    payload = {
        'sub': account,
        'role': role,
        'iat': now,
        'exp': now + expire_sec,
    }
    payload_b64 = _b64url(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    signing_input = f'{_JWT_HEADER}.{payload_b64}'
    return f'{signing_input}.{_sign(signing_input)}'


def decode_access_token(token: str) -> dict:
    """校验并解出标准 JWT 负载，失败抛 401"""
    parts = token.split('.')
    if len(parts) != 3:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '无效的令牌格式')
    header_b64, payload_b64, sig = parts

    # 1. 校验算法（仅允许 HS256）
    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '令牌头解析失败')
    if header.get('alg') != AUTH_CONFIG['algorithm'] or header.get('typ') != 'JWT':
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '令牌算法不受支持')

    # 2. 校验签名
    if not hmac.compare_digest(sig, _sign(f'{header_b64}.{payload_b64}')):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '令牌签名校验失败')

    # 3. 解析负载
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '令牌负载解析失败')

    # 4. 校验有效期
    if payload.get('exp', 0) < time.time():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '令牌已过期，请重新登录')
    return payload


# ============================================================
# FastAPI 依赖
# ============================================================
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """解析 Bearer 令牌 → 返回当前 User（未登录/令牌无效/用户不存在均抛 401）"""
    if credentials is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, '缺少认证令牌，请先登录',
            headers={'WWW-Authenticate': 'Bearer'},
        )
    payload = decode_access_token(credentials.credentials)
    user = db.query(User).filter(User.account == payload.get('sub')).first()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '用户不存在或已被删除')
    return user


def require_roles(*allowed_roles: str):
    """角色守卫依赖工厂：限制仅指定角色可访问，如 require_roles('it_admin')"""

    def guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, '权限不足：当前角色无权访问')
        return user

    return guard