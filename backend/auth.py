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
from config.settings import DATA_SCOPES, ORGANIZATION_TREE, ROLES, WORKSHOPS
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
    scope_type: Optional[str] = Field('all', description='数据范围：all / factory / workshop')
    scope_value: Optional[str] = Field(None, description='范围值：工厂code(F-01) 或 车间id(WS-01)')


class RegisterRequest(BaseModel):
    account: str = Field(..., min_length=3, max_length=64, description='账号（至少 3 位）')
    password: str = Field(..., min_length=6, description='密码（至少 6 位）')


class UserUpdate(BaseModel):
    role: Optional[str] = Field(None, description='角色：management / operator / it_admin')
    permissions: Optional[list] = Field(None, description='权限列表')
    password: Optional[str] = Field(None, min_length=6, description='重置密码（可选）')
    scope_type: Optional[str] = Field(None, description='数据范围：all / factory / workshop')
    scope_value: Optional[str] = Field(None, description='范围值：工厂code 或 车间id')


def _scope_label(scope_type: Optional[str], scope_value: Optional[str]) -> str:
    """数据范围 → 人类可读描述，如「华南一厂（电芯基地）」/「电芯制备车间」/「全集团」"""
    st = scope_type or 'all'
    if st == 'all':
        return '全集团'
    if st == 'factory' and scope_value:
        for f in ORGANIZATION_TREE['factories']:
            if f['code'] == scope_value:
                return f['name']
    if st == 'workshop' and scope_value:
        return WORKSHOPS.get(scope_value, {}).get('name', scope_value)
    return f'{st}:{scope_value}' if scope_value else st


def _user_out(u: User) -> dict:
    """用户 → 对外结构（不含密码哈希）"""
    permissions = u.permissions if u.permissions is not None else ROLES.get(u.role, {}).get('permissions', [])
    return {
        'id': u.id,
        'account': u.account,
        'role': u.role,
        'role_name': ROLES.get(u.role, {}).get('name', u.role),
        'permissions': permissions,
        'scope_type': getattr(u, 'scope_type', 'all') or 'all',
        'scope_value': getattr(u, 'scope_value', None),
        'scope_label': _scope_label(getattr(u, 'scope_type', 'all'), getattr(u, 'scope_value', None)),
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


def _resolve_scope(scope_type: Optional[str], scope_value: Optional[str]) -> tuple:
    """校验数据范围并归一化；组织级权限参数非法时抛 422。"""
    st = (scope_type or 'all').strip()
    if st not in DATA_SCOPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f'非法数据范围 {st!r}，可选 {DATA_SCOPES}',
        )
    if st == 'all':
        return 'all', None
    if not scope_value:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f'数据范围 {st} 必须提供 scope_value（工厂code 或 车间id）',
        )
    if st == 'factory':
        valid = [f['code'] for f in ORGANIZATION_TREE['factories']]
        if scope_value not in valid:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f'非法工厂 {scope_value!r}，可选 {valid}',
            )
    if st == 'workshop' and scope_value not in WORKSHOPS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f'非法车间 {scope_value!r}，可选 {list(WORKSHOPS)}',
        )
    return st, scope_value


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


@router.get('/scopes', summary='可选数据范围（组织级权限下拉）')
async def list_scopes(_: User = Depends(get_current_user)):
    return {
        'scopes': DATA_SCOPES,
        'factories': [
            {'code': f['code'], 'name': f['name'], 'workshops': f['workshops']}
            for f in ORGANIZATION_TREE['factories']
        ],
        'workshops': [{'id': k, 'name': v['name']} for k, v in WORKSHOPS.items()],
    }


@router.get('/org-tree', summary='组织层级（集团-工厂-车间）')
async def org_tree(_: User = Depends(get_current_user)):
    return {
        'organization': {'code': ORGANIZATION_TREE['code'], 'name': ORGANIZATION_TREE['name']},
        'factories': [
            {
                'code': f['code'],
                'name': f['name'],
                'workshops': [
                    {'id': ws, 'name': WORKSHOPS.get(ws, {}).get('name', ws)}
                    for ws in f['workshops']
                ],
            }
            for f in ORGANIZATION_TREE['factories']
        ],
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
    scope_type, scope_value = _resolve_scope(req.scope_type, req.scope_value)
    if db.query(User).filter(User.account == req.account).first():
        raise HTTPException(status.HTTP_409_CONFLICT, f'账号 {req.account} 已存在')
    user = User(
        account=req.account,
        role=req.role,
        password_hash=hash_password(req.password),
        permissions=_resolve_permissions(req.role, req.permissions),
        scope_type=scope_type,
        scope_value=scope_value,
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
    if req.scope_type is not None or req.scope_value is not None:
        scope_type, scope_value = _resolve_scope(
            req.scope_type if req.scope_type is not None else getattr(user, 'scope_type', 'all'),
            req.scope_value if req.scope_value is not None else getattr(user, 'scope_value', None),
        )
        user.scope_type = scope_type
        user.scope_value = scope_value

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