"""
seed —— 种子数据灌入

设备表种子数据直接来自 config.settings 的 EQUIPMENT_LIST + EQUIPMENT_TYPES，
保证数据库与算法侧设备主数据完全一致（共 78 台 / 12 类）。

用户表种子数据：默认三个角色各一个账号（管理层 / 运维岗 / IT管理员），
初始密码见 init_db 打印，生产环境首次登录后应及时修改。
"""

from __future__ import annotations

from config.settings import EQUIPMENT_LIST, EQUIPMENT_TYPES
from database.database import SessionLocal
from database.models import Equipment, User


def seed_equipment() -> int:
    """灌入设备表（幂等：已存在则跳过），返回本次新增条数"""
    added = 0
    with SessionLocal() as db:
        existing = {eq.equipment_id for eq in db.query(Equipment.equipment_id).all()}
        for eq_id, info in EQUIPMENT_LIST.items():
            if eq_id in existing:
                continue
            type_info = EQUIPMENT_TYPES.get(info.get('equipment_type'), {})
            db.add(
                Equipment(
                    equipment_id=eq_id,
                    name=info.get('name', eq_id),
                    equipment_type=info.get('equipment_type', 'unknown'),
                    workshop_id=info.get('workshop_id'),
                    team_id=info.get('team_id'),
                    rated_power=float(type_info.get('rated_power', 0.0)),
                )
            )
            added += 1
        db.commit()
    return added


# 默认账号（角色 + 初始密码），开发/验收用
DEFAULT_USERS = [
    ('admin', 'it_admin', 'Admin@123'),
    ('manager', 'management', 'Manager@123'),
    ('operator', 'operator', 'Operator@123'),
]


def seed_users() -> int:
    """灌入默认用户（幂等：账号已存在则跳过），返回本次新增条数"""
    from backend.security import hash_password  # 延迟导入，避免 database 层启动即依赖 backend

    from config.settings import ROLES

    added = 0
    with SessionLocal() as db:
        existing = {u.account for u in db.query(User.account).all()}
        for account, role, password in DEFAULT_USERS:
            if account in existing:
                continue
            db.add(
                User(
                    account=account,
                    role=role,
                    password_hash=hash_password(password),
                    permissions=ROLES[role]['permissions'],
                )
            )
            added += 1
        db.commit()
    return added