"""
report_service —— 报表数据聚合服务

统一产出规范化的报表结构，供三种输出形态复用：
    JSON 预览 / Excel 导出 / PDF 导出

规范结构：
    {
        'title': str,
        'subtitle': str,            # 报表期间 / 覆盖范围等说明
        'sections': [               # 顺序渲染的若干小节
            {
                'heading': str,     # 小节标题，如「一、总体概况」
                'tables': [         # 小节内可含多张表
                    {'headers': [str, ...], 'rows': [[str, ...], ...]},
                ],
            },
        ],
    }

三个报表：
    1. monthly_report(db, year, month)        月度碳排报告
    2. traceability_ledger(db, ...)           设备溯源台账
    3. savings_comparison(equipment_ids)      降碳成效对比表（方案台账式）

【能耗换算】
    time_series_data.power 为 kW、按分钟入库；碳排 carbon_emission 已按
    power/60×factor 算好入库（见 collector.service.compute_carbon）。
    因此累计能耗 kWh = Σ power / 60（每条代表 1 分钟）。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from config.settings import (
    ALERT_CONFIG,
    ARCHIVE_CONFIG,
    CARBON_FACTORS,
    EQUIPMENT_LIST,
    EQUIPMENT_TYPES,
    TEAMS,
    WORKSHOPS,
)
from database.models import AlarmRecord, Equipment, TimeSeriesArchive, TimeSeriesData

SEVERITY_ORDER = {'critical': 3, 'high': 2, 'medium': 1, 'low': 0}
SEVERITY_LABELS = {'critical': '严重', 'high': '高', 'medium': '中', 'low': '低'}
STRATEGY_TYPE_LABELS = {
    'equipment_maintenance': '设备运维',
    'production_scheduling': '生产排班',
    'process_optimization': '工艺优化',
}
PRIORITY_LABELS = {'high': '高', 'medium': '中', 'low': '低'}


# ============================================================
# 工具
# ============================================================
def _type_name(eq_type: str) -> str:
    return EQUIPMENT_TYPES.get(eq_type, {}).get('name', eq_type)


def _workshop_name(ws_id: str) -> str:
    name = WORKSHOPS.get(ws_id, {}).get('name', '')
    return f'{ws_id} {name}'.strip()


def _team_name(team_id: str) -> str:
    name = TEAMS.get(team_id, {}).get('name', '')
    return f'{team_id} {name}'.strip()


def _fnum(v, nd: int = 2) -> str:
    """数值 → 千分位字符串；空值返回 '—'"""
    if v is None:
        return '—'
    try:
        return f'{float(v):,.{nd}f}'
    except (TypeError, ValueError):
        return str(v)


def _report(title: str, subtitle: str, sections: List[dict]) -> dict:
    return {'title': title, 'subtitle': subtitle, 'sections': sections}


def _table(headers: List[str], rows: Sequence[Sequence]) -> dict:
    return {'headers': list(headers), 'rows': [[str(c) for c in r] for r in rows]}


# ============================================================
# 归档感知的时序聚合（原始表 + 归档表透明合并）
# ============================================================
def _collect_daily(db: Session, start: datetime, end: datetime) -> List[dict]:
    """按「设备 × 日」粒度聚合 [start, end)，透明跨原始表与归档表读取。

    归档表仅覆盖早于 retention_raw_days 的历史；近期部分仍从原始表按日实时
    聚合，两段结果合并后返回统一结构。返回 list[dict]：
        {equipment_id, day, carbon(kgCO2), energy(kWh), load, temp, samples}
    """
    cutoff = datetime.now() - timedelta(days=ARCHIVE_CONFIG['retention_raw_days'])
    rows: List[dict] = []

    # 近期原始段：按日实时聚合
    r_start = max(start, cutoff)
    if r_start < end:
        day = func.strftime('%Y-%m-%d', TimeSeriesData.timestamp)
        raw = (
            db.query(
                TimeSeriesData.equipment_id,
                day,
                func.coalesce(func.sum(TimeSeriesData.carbon_emission), 0.0),
                (func.coalesce(func.sum(TimeSeriesData.power), 0.0) / 60.0),
                func.avg(TimeSeriesData.load_rate),
                func.avg(TimeSeriesData.temperature),
                func.count(TimeSeriesData.id),
            )
            .filter(TimeSeriesData.timestamp >= r_start, TimeSeriesData.timestamp < end)
            .group_by(TimeSeriesData.equipment_id, day)
            .all()
        )
        for eq, d, carbon, energy, load, temp, cnt in raw:
            rows.append({
                'equipment_id': eq, 'day': d,
                'carbon': float(carbon or 0.0), 'energy': float(energy or 0.0),
                'load': load, 'temp': temp, 'samples': int(cnt or 0),
            })

    # 历史归档段：读 day 桶
    a_end = min(end, cutoff)
    if start < a_end:
        arch = (
            db.query(TimeSeriesArchive)
            .filter(
                TimeSeriesArchive.granularity == 'day',
                TimeSeriesArchive.bucket_start >= start,
                TimeSeriesArchive.bucket_start < a_end,
            )
            .all()
        )
        for r in arch:
            rows.append({
                'equipment_id': r.equipment_id, 'day': r.bucket_start.strftime('%Y-%m-%d'),
                'carbon': float(r.carbon_sum or 0.0), 'energy': float(r.energy_sum or 0.0),
                'load': r.load_rate_avg, 'temp': r.temperature_avg,
                'samples': int(r.sample_count or 0),
            })

    return rows


def _aggregate_daily_by_equipment(daily: List[dict]) -> dict:
    """把 _collect_daily 结果按设备聚合：累计碳排/能耗，负载率/温度按采样数加权平均"""
    acc: dict = defaultdict(
        lambda: {'carbon': 0.0, 'energy': 0.0, 'load_w': 0.0, 'temp_w': 0.0, 'samples': 0}
    )
    for r in daily:
        d = acc[r['equipment_id']]
        d['carbon'] += r['carbon']
        d['energy'] += r['energy']
        s = r['samples']
        d['samples'] += s
        if s and r['load'] is not None:
            d['load_w'] += float(r['load']) * s
        if s and r['temp'] is not None:
            d['temp_w'] += float(r['temp']) * s

    out: dict = {}
    for eid, d in acc.items():
        out[eid] = {
            'carbon': d['carbon'],
            'energy': d['energy'],
            'load': (d['load_w'] / d['samples']) if d['samples'] else None,
            'temp': (d['temp_w'] / d['samples']) if d['samples'] else None,
            'samples': d['samples'],
        }
    return out


# ============================================================
# ① 月度碳排报告
# ============================================================
def monthly_report(db: Session, year: int, month: int) -> dict:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    # 归档感知：一次性取「设备 × 日」聚合，透明跨原始表 + 归档表
    daily_rows = _collect_daily(db, start, end)
    eq_map = {e.equipment_id: e for e in db.query(Equipment).all()}

    alarm_count = db.query(func.count(AlarmRecord.id)).filter(
        (AlarmRecord.alarm_time >= start) & (AlarmRecord.alarm_time < end)
    ).scalar() or 0

    ws_carbon: dict = {}
    ws_energy: dict = {}
    eq_carbon: dict = {}
    eq_energy: dict = {}
    day_carbon: dict = {}
    day_energy: dict = {}
    for r in daily_rows:
        eid = r['equipment_id']
        eq = eq_map.get(eid)
        ws = eq.workshop_id if eq else eid
        ws_carbon[ws] = ws_carbon.get(ws, 0.0) + r['carbon']
        ws_energy[ws] = ws_energy.get(ws, 0.0) + r['energy']
        eq_carbon[eid] = eq_carbon.get(eid, 0.0) + r['carbon']
        eq_energy[eid] = eq_energy.get(eid, 0.0) + r['energy']
        day_carbon[r['day']] = day_carbon.get(r['day'], 0.0) + r['carbon']
        day_energy[r['day']] = day_energy.get(r['day'], 0.0) + r['energy']

    total_carbon = sum(r['carbon'] for r in daily_rows)
    total_energy = sum(r['energy'] for r in daily_rows)
    eq_count = len(eq_carbon)

    # 分车间 / 高碳排设备 Top10（降序）/ 每日趋势（升序）
    by_workshop = sorted(
        [(ws, ws_carbon[ws], ws_energy[ws]) for ws in ws_carbon],
        key=lambda x: x[1], reverse=True,
    )
    by_equipment = sorted(
        [(eid, eq_carbon[eid], eq_energy[eid]) for eid in eq_carbon],
        key=lambda x: x[1], reverse=True,
    )[:10]
    day_keys = sorted(day_carbon.keys())

    sections: List[dict] = []

    sections.append({
        'heading': '一、总体概况',
        'tables': [_table(
            ['指标', '数值'],
            [
                ['统计周期', f'{year} 年 {month} 月'],
                ['总碳排 (kgCO₂)', _fnum(total_carbon)],
                ['总能耗 (kWh)', _fnum(total_energy)],
                ['覆盖设备数 (台)', str(eq_count)],
                ['告警次数', str(int(alarm_count))],
            ],
        )],
    })

    sections.append({
        'heading': '二、车间碳排分布',
        'tables': [_table(
            ['车间', '碳排 (kgCO₂)', '能耗 (kWh)'],
            [
                [_workshop_name(ws), _fnum(carbon), _fnum(energy)]
                for ws, carbon, energy in by_workshop
            ],
        )],
    })

    sections.append({
        'heading': '三、高碳排设备 Top10',
        'tables': [_table(
            ['设备编号', '设备名称', '设备类型', '碳排 (kgCO₂)', '能耗 (kWh)'],
            [
                [eid, (eq_map[eid].name if eid in eq_map else eid),
                 (_type_name(eq_map[eid].equipment_type) if eid in eq_map else ''),
                 _fnum(carbon), _fnum(energy)]
                for eid, carbon, energy in by_equipment
            ],
        )],
    })

    sections.append({
        'heading': '四、每日碳排趋势',
        'tables': [_table(
            ['日期', '碳排 (kgCO₂)', '能耗 (kWh)'],
            [[d, _fnum(day_carbon[d]), _fnum(day_energy[d])] for d in day_keys],
        )],
    })

    return _report('月度碳排报告', f'{year} 年 {month} 月', sections)


# ============================================================
# ② 设备溯源台账
# ============================================================
def traceability_ledger(
    db: Session,
    equipment_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    q = db.query(Equipment)
    if equipment_id:
        q = q.filter(Equipment.equipment_id == equipment_id)
    equipments = q.order_by(Equipment.equipment_id).all()

    # 归档感知时序聚合：无时间范围时默认覆盖近 retention_archive_years 年
    end = end_time or datetime.now()
    start = start_time or (end - timedelta(days=ARCHIVE_CONFIG['retention_archive_years'] * 365))
    per_eq = _aggregate_daily_by_equipment(_collect_daily(db, start, end))

    rows: List[list] = []
    for eq in equipments:
        d = per_eq.get(eq.equipment_id)
        carbon = d['carbon'] if d else 0.0
        energy = d['energy'] if d else 0.0
        avg_load = d['load'] if d else None
        avg_temp = d['temp'] if d else None
        sample_count = d['samples'] if d else 0

        # 告警单独查（非归档对象），保持原有时间过滤语义
        al_q = db.query(AlarmRecord).filter(AlarmRecord.equipment_id == eq.equipment_id)
        if start_time is not None:
            al_q = al_q.filter(AlarmRecord.alarm_time >= start_time)
        if end_time is not None:
            al_q = al_q.filter(AlarmRecord.alarm_time <= end_time)

        alarms = al_q.order_by(AlarmRecord.alarm_time.desc()).all()
        alarm_count = len(alarms)
        top_severity = '—'
        if alarms:
            top_severity = max((a.severity for a in alarms), key=lambda s: SEVERITY_ORDER.get(s, 0))
        latest_root_cause = alarms[0].root_cause if alarms else ''

        health_score = _health_score(alarm_count, avg_load)
        suggestion = latest_root_cause or _default_suggestion(sample_count, avg_load)

        rows.append([
            eq.equipment_id,
            eq.name,
            _type_name(eq.equipment_type),
            _workshop_name(eq.workshop_id),
            _team_name(eq.team_id),
            _fnum(carbon),
            _fnum(energy),
            (_fnum(avg_load * 100, 1) + '%') if avg_load is not None else '—',
            _fnum(avg_temp, 1),
            str(sample_count),
            str(alarm_count),
            SEVERITY_LABELS.get(top_severity, top_severity),
            health_score,
            suggestion,
        ])

    sections = [{
        'heading': '设备溯源台账明细',
        'tables': [_table(
            [
                '设备编号', '设备名称', '设备类型', '车间', '班组',
                '碳排 (kgCO₂)', '能耗 (kWh)', '平均负载率', '平均温度 (℃)',
                '采样数', '告警次数', '最高告警', '健康评分', '根因 / 改进建议',
            ],
            rows,
        )],
    }]

    subtitle = f'覆盖 {len(equipments)} 台设备'
    if start_time or end_time:
        s = start_time.strftime('%Y-%m-%d %H:%M') if start_time else '起始'
        e = end_time.strftime('%Y-%m-%d %H:%M') if end_time else '至今'
        subtitle += f'（{s} ~ {e}）'
    else:
        subtitle += f'（近 {ARCHIVE_CONFIG["retention_archive_years"]} 年）'
    return _report('设备溯源台账', subtitle, sections)


def _health_score(alarm_count: int, avg_load: float) -> int:
    """简单健康评分：告警越多越低，低负载再扣分"""
    score = 95 if alarm_count == 0 else max(40, 100 - alarm_count * 10)
    if avg_load and avg_load < 0.4:
        score -= 10
    return max(0, min(100, score))


def _default_suggestion(sample_count: int, avg_load: float) -> str:
    if sample_count == 0:
        return '暂无运行数据，建议接入采集'
    if avg_load and avg_load < 0.4:
        return '设备低负载运行，建议合并负载或错峰排产'
    return '运行正常，保持当前工况'


# ============================================================
# ③ 降碳成效对比表（方案台账式）
# ============================================================
def savings_comparison(equipment_ids: Optional[List[str]] = None) -> dict:
    from carbon_strategy.strategy_engine import CarbonStrategyEngine

    if equipment_ids is None:
        # 默认取实时扫描的代表设备（高耗能重点设备），避免 78 台全量展开
        equipment_ids = ALERT_CONFIG.get('scan_equipment', [])

    engine = CarbonStrategyEngine()
    rows: List[list] = []
    for eq_id in equipment_ids:
        info = EQUIPMENT_LIST.get(eq_id, {})
        try:
            strategies = engine.generate_strategies(eq_id)
        except Exception:
            strategies = []
        for s in strategies:
            rows.append([
                eq_id,
                info.get('name', eq_id),
                STRATEGY_TYPE_LABELS.get(s.get('strategy_type'), s.get('strategy_type', '')),
                s.get('title', ''),
                s.get('estimated_energy_saving', '—'),
                s.get('estimated_carbon_reduction', '—'),
                s.get('investment', '—'),
                s.get('payback_period', '—'),
                PRIORITY_LABELS.get(s.get('priority'), s.get('priority', '')),
            ])

    # 按优先级排序：高 > 中 > 低
    prio_rank = {'高': 0, '中': 1, '低': 2}
    rows.sort(key=lambda r: prio_rank.get(r[8], 9))

    high_count = sum(1 for r in rows if r[8] == '高')
    sections = [
        {
            'heading': '一、方案汇总',
            'tables': [_table(
                ['指标', '数值'],
                [
                    ['涉及设备数', str(len(equipment_ids))],
                    ['方案总数', str(len(rows))],
                    ['高优先级方案', str(high_count)],
                ],
            )],
        },
        {
            'heading': '二、降碳方案明细',
            'tables': [_table(
                [
                    '设备编号', '设备名称', '方案类型', '方案标题',
                    '节能比例', '预计减碳', '投资额', '回收期', '优先级',
                ],
                rows,
            )],
        },
    ]
    return _report('降碳成效对比表', f'共 {len(equipment_ids)} 台设备', sections)


# ============================================================
# ④ MRV 碳排放核查报告（监测-报告-核查闭环）
# ============================================================
# 范围划分（GHG Protocol / ISO 14064-1）：
#   范围1 直接排放   —— 厂内化石燃料燃烧（本项目设备均为电力驱动，无该排放，记 0）
#   范围2 外购间接   —— 外购电力/热力（本项目主体，等于全部设备碳排汇总）
#   范围3 其他间接   —— 供应链/运输等（本期未核算，标 N/A）
_MRV_METHODOLOGY = 'GHG Protocol / ISO 14064-1 排放因子法'

# 排放因子清单：数值来自 config.settings.CARBON_FACTORS
_FACTOR_META = [
    ('electricity', '电力', 'kgCO₂/kWh', '中国南方电网区域平均排放因子'),
    ('natural_gas', '天然气', 'kgCO₂/m³', 'IPCC 2006 缺省值'),
    ('coal', '煤炭', 'kgCO₂/kg', 'IPCC 2006 缺省值'),
    ('diesel', '柴油', 'kgCO₂/L', 'IPCC 2006 缺省值'),
    ('compressed_air', '压缩空气', 'kgCO₂/m³', '按空压机耗电折算的估算值'),
]


def mrv_metrics(db: Session, year: int, month: int) -> dict:
    """计算 MRV 核算指标：范围1/2/3 排放、数据质量评分、覆盖率等。

    排放均来自 time_series_data.carbon_emission（已按 power/60 × 因子算好入库），
    本项目设备全部为电力驱动，故范围2 = 全部碳排，范围1 = 0，范围3 不适用。
    """
    start = datetime(year, month, 1)
    end = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)

    daily_rows = _collect_daily(db, start, end)
    eq_map = {e.equipment_id: e for e in db.query(Equipment).all()}

    total_carbon = sum(r['carbon'] for r in daily_rows)
    total_energy = sum(r['energy'] for r in daily_rows)
    total_samples = sum(r['samples'] for r in daily_rows)

    active = {r['equipment_id'] for r in daily_rows}
    registered = len(eq_map) or 1
    coverage = len(active) / registered
    score = round(coverage * 100, 1)

    ws_carbon: dict = {}
    for r in daily_rows:
        eq = eq_map.get(r['equipment_id'])
        ws = eq.workshop_id if eq else r['equipment_id']
        ws_carbon[ws] = ws_carbon.get(ws, 0.0) + r['carbon']
    by_workshop = sorted(ws_carbon.items(), key=lambda x: x[1], reverse=True)

    return {
        'period': f'{year:04d}-{month:02d}',
        'scope1': 0.0,
        'scope2': total_carbon,
        'scope3': None,
        'total_carbon': total_carbon,
        'total_energy': total_energy,
        'total_samples': total_samples,
        'active_count': len(active),
        'registered': registered,
        'coverage': coverage,
        'data_quality_score': score,
        'by_workshop': by_workshop,
    }


def build_mrv_report(m: dict) -> dict:
    """由 mrv_metrics 结果渲染规范化 MRV 报告结构（供 JSON/Excel/PDF 复用）"""
    sections: List[dict] = []

    sections.append({
        'heading': '一、核算边界与方法学',
        'tables': [_table(
            ['项目', '内容'],
            [
                ['报告期', m['period']],
                ['组织边界', '单体工厂（电芯制造基地）'],
                ['运营边界', '生产车间 + 物流动力区内全部在用设备（按用电核算）'],
                ['核算方法学', _MRV_METHODOLOGY],
                ['排放因子来源', 'IPCC 2006 Guidelines + 中国南方电网区域平均排放因子'],
                ['活动数据来源', '设备分钟级功率数据（time_series_data 自动采集）'],
            ],
        )],
    })

    sections.append({
        'heading': '二、温室气体排放汇总（范围 1 / 2 / 3）',
        'tables': [_table(
            ['范围', '类别', '排放量 (kgCO₂)'],
            [
                ['范围 1', '直接排放（化石燃料燃烧）', _fnum(m['scope1'])],
                ['范围 2', '外购电力间接排放', _fnum(m['scope2'])],
                ['范围 3', '其他间接排放', '不适用（本期未核算）'],
                ['合计', '范围 1 + 范围 2', _fnum(m['total_carbon'])],
            ],
        )],
    })

    sections.append({
        'heading': '三、分车间排放明细（范围 2）',
        'tables': [_table(
            ['车间', '碳排 (kgCO₂)'],
            [[_workshop_name(ws), _fnum(c)] for ws, c in m['by_workshop']],
        )],
    })

    factor_rows = [
        [code, name, _fnum(CARBON_FACTORS.get(code)), unit, source]
        for code, name, unit, source in _FACTOR_META
    ]
    sections.append({
        'heading': '四、排放因子清单',
        'tables': [_table(
            ['因子代码', '能源类型', '因子值', '单位', '来源'],
            factor_rows,
        )],
    })

    uncertainty = (
        f'本期覆盖 {m["active_count"]}/{m["registered"]} 台在册设备，'
        f'共 {m["total_samples"]} 条分钟级采样记录；数据质量评分受设备覆盖率主导。'
    )
    sections.append({
        'heading': '五、数据质量与不确定性分析',
        'tables': [_table(
            ['指标', '数值'],
            [
                ['在册设备数', str(m['registered'])],
                ['有数据设备数', str(m['active_count'])],
                ['设备覆盖率', f"{m['coverage'] * 100:.1f}%"],
                ['分钟级采样记录数', str(m['total_samples'])],
                ['数据质量评分', f"{m['data_quality_score']} / 100"],
                ['不确定性说明', uncertainty],
            ],
        )],
    })

    sections.append({
        'heading': '六、核查声明',
        'tables': [_table(
            ['项目', '内容'],
            [
                ['核查状态', '待核查（draft）'],
                ['核查人', '——（第三方核查后签署）'],
                ['核查结论', '——'],
                ['说明', '本报告由系统自动核算生成，排放因子与方法学需第三方核查确认后方可用于对外申报。'],
            ],
        )],
    })

    return _report('MRV 碳排放核查报告', m['period'], sections)


def mrv_workbook(db: Session, year: int, month: int) -> dict:
    """核算底稿：逐设备 × 逐日 的活动数据与碳排放明细，供第三方核查逐条追溯。

    复用 _collect_daily（跨原始表 + 归档表），一行 = 一台设备一天的核算依据。
    """
    start = datetime(year, month, 1)
    end = datetime(year, month + 1, 1) if month < 12 else datetime(year + 1, 1, 1)

    daily_rows = _collect_daily(db, start, end)
    eq_map = {e.equipment_id: e for e in db.query(Equipment).all()}
    daily_rows.sort(key=lambda r: (r['equipment_id'], r['day']))

    rows = []
    for r in daily_rows:
        eq = eq_map.get(r['equipment_id'])
        rows.append([
            r['equipment_id'],
            eq.equipment_name if eq else r['equipment_id'],
            eq.workshop_id if eq else '—',
            r['day'],
            _fnum(r['carbon']),
            _fnum(r['energy']),
            (_fnum(float(r['load']) * 100, 1) + '%') if r['load'] is not None else '—',
            _fnum(float(r['temp']), 1) if r['temp'] is not None else '—',
            str(r['samples']),
        ])

    sections = [{
        'heading': '活动数据与排放明细（逐设备 × 逐日）',
        'tables': [_table(
            ['设备ID', '设备名称', '车间', '日期', '碳排(kgCO₂)', '能耗(kWh)',
             '平均负载率', '平均温度(℃)', '采样数'],
            rows,
        )],
    }]

    return _report('MRV 核算底稿', f'{year:04d}-{month:02d} · 共 {len(rows)} 条记录', sections)