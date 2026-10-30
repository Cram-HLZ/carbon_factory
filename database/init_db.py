"""
init_db —— 数据库初始化入口

用法（在项目根目录执行）：
    python -m database.init_db

步骤：
    1. 建库建表（创建 5 张表，幂等）
    2. 灌入设备表种子数据（来自 config.settings，78 台设备）
    3. 打印各表情况，便于核对
"""

from __future__ import annotations

from database.database import DATABASE_URL, engine, init_database
from database.models import AlarmRecord, Equipment, MrvReport, Strategy, TimeSeriesArchive, TimeSeriesData, User
from database.seed import DEFAULT_USERS, seed_equipment, seed_users
from sqlalchemy import text


def main() -> None:
    print('=' * 60)
    print('碳排监测系统 · 数据库初始化')
    print('=' * 60)
    print(f'连接：{DATABASE_URL}')

    # 1. 建表
    init_database()
    print('\n[1/4] 建表完成（equipment / time_series_data / time_series_archive / alarm_record / strategy / user / mrv_report）')

    # 2. 灌入设备表种子数据
    added = seed_equipment()
    print(f'[2/4] 设备表种子数据灌入完成，本次新增 {added} 台')

    # 3. 灌入默认用户（三种角色）
    added_users = seed_users()
    print(f'[3/4] 默认账号灌入完成，本次新增 {added_users} 个：')
    for account, role, password in DEFAULT_USERS:
        print(f'        账号 {account:<10} 角色 {role:<12} 初始密码 {password}')

    # 4. 打印各表记录数
    print('\n[4/4] 各表记录数：')
    tables = {
        'equipment（设备表）': Equipment,
        'time_series_data（时序数据表）': TimeSeriesData,
        'time_series_archive（归档表）': TimeSeriesArchive,
        'alarm_record（告警记录表）': AlarmRecord,
        'strategy（方案表）': Strategy,
        'user（用户表）': User,
        'mrv_report（MRV核查报告台账）': MrvReport,
    }
    with engine.connect() as conn:
        for label, model in tables.items():
            count = conn.execute(
                text(f'SELECT COUNT(*) FROM {model.__tablename__}')
            ).scalar()
            print(f'  - {label:<28} {count} 条')

    print('\n完成。')

    # 提示切换 MySQL 的方式
    if DATABASE_URL.startswith('sqlite'):
        print('提示：当前使用 SQLite；切换 MySQL 请设置环境变量 DATABASE_URL，')
        print('      格式：mysql+pymysql://user:password@localhost:3306/carbon_factory')


if __name__ == '__main__':
    main()