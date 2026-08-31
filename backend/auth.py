"""
auth —— 认证与角色管理路由（阶段2 · 登录/角色管理）

【公开接口】
    POST /api/auth/login     登录，返回 access_token + 用户信息
    GET  /api/auth/roles     角色定义（登录用户可查，前端下拉框用）

【需登录接口】
    GET  /api/auth/me        当前登录用户信息
    POST /api/auth/logout    登出（无状态令牌，服务端仅返回确认）

【角色管理接口（仅 IT管理员）】
    GET    /api/auth/users        列出全部用户
    POST   /api/auth/users        创建用户
    PUT    /api/auth/users/{id}   更新用户（改角色/权限/重置密码）
    DELETE /api/auth/users/{id}   删除用户

角色取值：
    management  管理层    it_admin  IT管理员    operator  运维岗
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.security import (
    create_access_token,
    get_current_user,
    hash_password,
    require_roles,
    verify_password,
)
from config.settings import ROLES
from database.database import get_db
from database.models import User

router = APIRouter(prefix='/api/auth', tags=['认证与权限'])


# ============================================================
# 入站 / 出站模型
# ============================================================
class LoginRequest(BaseModel):
    account: str = Field(..., description='账号')
    password: str = Field(..., description='密码')


class UserCreate(BaseModel):
    account: str = Field(..., min_length=3, max_length=64, description='账号')
    password: str = Field(..., min_length=6, description='初始密码（至少 6 位）')
    role: str = Field(..., description='角色：management / operator / it_admin')
    permissions: Optional[list] = Field(None, description='自定义权限列表，缺省用角色默认权限')


class RegisterRequest(BaseModel):
    account: str = Field(..., min_length=3, max_length=64, description='账号（至少 3 位）')
    password: str = Field(..., min_length=6, description='密码（至少 6 位）')


class UserUpdate(BaseModel):
    role: Optional[str] = Field(None, description='角色：management / operator / it_admin')
    permissions: Optional[list] = Field(None, description='权限列表')
    password: Optional[str] = Field(None, min_length=6, description='重置密码（可选）')


def _user_out(u: User) -> dict:
    """用户 → 对外结构（不含密码哈希）"""
    permissions = u.permissions if u.permissions is not None else ROLES.get(u.role, {}).get('permissions', [])
    return {
        'id': u.id,
        'account': u.account,
        'role': u.role,
        'role_name': ROLES.get(u.role, {}).get('name', u.role),
        'permissions': permissions,
    }


def _resolve_permissions(role: str, permissions: Optional[list]) -> list:
    if permissions is not None:
        return permissions
    return ROLES.get(role, {}).get('permissions', [])


def _ensure_role(role: str) -> None:
    if role not in ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f'非法角色 {role!r}，可选 {list(ROLES.keys())}',
        )


# ============================================================
# 登录 / 当前用户 / 登出 / 角色定义
# ============================================================
@router.post('/login', summary='登录')
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.account == req.account).first()
    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '账号或密码错误')
    token = create_access_token(user.account, user.role)
    return {
        'access_token': token,
        'token_type': 'bearer',
        'user': _user_out(user),
    }


@router.post('/register', summary='用户注册（固定为运维岗，注册即登录）', status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    # 开放注册固定为最低权限角色，避免任何人自选管理层/IT管理员造成越权
    role = 'operator'
    if db.query(User).filter(User.account == req.account).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f'账号 {req.account} 已存在')
    user = User(
        account=req.account,
        role=role,
        password_hash=hash_password(req.password),
        permissions=_resolve_permissions(role, None),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.account, user.role)
    return {
        'access_token': token,
        'token_type': 'bearer',
        'user': _user_out(user),
    }


@router.get('/me', summary='当前登录用户')
async def me(user: User = Depends(get_current_user)):
    return _user_out(user)


@router.post('/logout', summary='登出')
async def logout(user: User = Depends(get_current_user)):
    # 无状态令牌：服务端无需销毁会话，客户端应丢弃本地 token
    return {'message': '已登出', 'account': user.account}


@router.get('/roles', summary='角色定义')
async def list_roles(_: User = Depends(get_current_user)):
    return {
        key: {
            'name': v['name'],
            'description': v['description'],
            'permissions': v['permissions'],
        }
        for key, v in ROLES.items()
    }


# ============================================================
# 角色管理（仅 IT管理员）
# ============================================================
@router.get('/users', summary='列出全部用户')
async def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles('it_admin')),
):
    users = db.query(User).order_by(User.id).all()
    return [_user_out(u) for u in users]


@router.post('/users', summary='创建用户', status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles('it_admin')),
):
    _ensure_role(req.role)
    if db.query(User).filter(User.account == req.account).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f'账号 {req.account} 已存在')
    user = User(
        account=req.account,
        role=req.role,
        password_hash=hash_password(req.password),
        permissions=_resolve_permissions(req.role, req.permissions),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.put('/users/{user_id}', summary='更新用户')
async def update_user(
    user_id: int,
    req: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles('it_admin')),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, '用户不存在')

    if req.role is not None:
        _ensure_role(req.role)
        user.role = req.role
        # 改角色且未显式指定权限时，重置为该角色默认权限
        if req.permissions is None:
            user.permissions = ROLES[req.role]['permissions']
    if req.permissions is not None:
        user.permissions = req.permissions
    if req.password is not None:
        user.password_hash = hash_password(req.password)

    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.delete('/users/{user_id}', summary='删除用户')
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles('it_admin')),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, '用户不存在')

    # 防止删光 IT管理员导致无人可管理系统
    if user.role == 'it_admin':
        admin_count = db.query(User).filter(User.role == 'it_admin').count()
        if admin_count <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, '至少保留一名 IT管理员')

    db.delete(user)
    db.commit()
    return {'message': f'已删除用户 {user.account}'}