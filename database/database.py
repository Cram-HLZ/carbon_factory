"""
database —— 数据库引擎 / 会话 / 建表

默认使用 SQLite（项目约束：数据存储用 SQLite，可替换为 MySQL）。
    - 本地默认：database/carbon_factory.db
    - 切换到 MySQL：设置环境变量 DATABASE_URL，例如
        mysql+pymysql://user:password@localhost:3306/carbon_factory

【说明】
    get_db 为 FastAPI 依赖注入用的会话生成器，供后端路由阶段2接入时使用。
"""

from __future__ import annotations

import os
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import BASE_DIR

# 数据库文件目录（database/），首次运行自动创建
DATABASE_DIR = BASE_DIR / 'database'
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

# 默认 SQLite；可通过环境变量 DATABASE_URL 切换（pymysql 已在 requirements.txt 中）
DEFAULT_DATABASE_URL = f"sqlite:///{(DATABASE_DIR / 'carbon_factory.db').as_posix()}"
DATABASE_URL = os.environ.get('DATABASE_URL', DEFAULT_DATABASE_URL)

# SQLite 需关闭同线程检查；MySQL 等远端驱动不传 connect_args
connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个独立会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    """建库建表（幂等：表已存在则跳过）"""
    from database.models import Base  # 本地导入，确保模型已注册到 Base.metadata

    Base.metadata.create_all(bind=engine)