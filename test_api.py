"""
test_api —— 算法接口自动化验证脚本（阶段1 · Step 1A）

对应执行计划（share.traecontent.cn/artifact/Z-9PF74AJERLYM）：
    Step 1A 要求「跑现成测试脚本验证 anomaly/detect 和 heatmap」，
    本脚本为该交付物，且额外覆盖全部 8 个端点 + 实际响应字段核对。

【使用方式】
    1. 先启动算法服务（项目根目录执行）：
        python main.py                    # 监听 0.0.0.0:8000
    2. 另开终端运行本脚本：
        python test_api.py
        python test_api.py --base http://localhost:8000   # 自定义地址

【输出内容】
    - 每个接口的 HTTP 状态 / 业务 code / 实际返回字段清单
    - 末尾汇总 PASS/FAIL
    - 「实际响应 vs 文档」差异核对提示（详见 docs/algorithm_interface.md 第九章）

【设计说明】
    只依赖 Python 标准库 urllib，不引入第三方包——联调机无需装额外依赖即可跑。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_BASE = 'http://localhost:8000'
TIMEOUT = 20

# 模拟数据的时间范围（data/generate_sample_data.py 生成的是 2026-08-15 ~ 2026-08-21）
DATA_START = '2026-08-15T00:00:00'
DATA_END = '2026-08-22T00:00:00'

# 各接口期望出现的顶层 data 字段（用于「实际 vs 文档」粗核对）
# 维护约定：接口字段变更时同步更新这里 + docs/algorithm_interface.md 第九章
EXPECTED_FIELDS: Dict[str, set] = {
    '/health': {'status'},
    '/carbon/overview': {
        'total_emission', 'total_energy', 'by_workshop',
        'by_team', 'by_equipment_top', 'hourly_trend',
    },
    '/carbon/heatmap': {'records', 'count'},
    '/equipment/list': {'count', 'items'},
    '/equipment/realtime': {'equipment_id', 'equipment_name', 'power', 'load_rate',
                             'carbon_emission', 'temperature', 'status'},
    '/anomaly/detect': {'is_anomaly', 'reconstruction_error', 'threshold',
                         'severity', 'anomaly_score', 'equipment_id', 'should_alert'},
    '/traceability/report': {'equipment_id', 'carbon_emission', 'baseline_emission',
                              'excess_emission', 'root_causes',
                              'history_72h_summary', 'recommendation'},
    '/strategy/generate': {'strategies', 'count'},
    '/carbon/query': {'level', 'records'},
}


# ============================================================
# HTTP 工具（标准库实现，零依赖）
# ============================================================
def http_get(base: str, path: str, params: Optional[Dict] = None) -> Tuple[int, Any]:
    """GET 请求，返回 (http_status, 解析后的json)"""
    url = base + path
    if params:
        url += '?' + urlencode(params)
    req = urllib.request.Request(url, method='GET')
    return _do(req)


def http_post(base: str, path: str, payload: Dict) -> Tuple[int, Any]:
    """POST JSON 请求，返回 (http_status, 解析后的json)"""
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        base + path, data=data, method='POST',
        headers={'Content-Type': 'application/json'},
    )
    return _do(req)


def _do(req: urllib.request.Request) -> Tuple[int, Any]:
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        # 4xx/5xx 也尝试解析 body，方便看到 FastAPI 的 422 校验错误详情
        try:
            body = json.loads(exc.read().decode('utf-8'))
        except Exception:
            body = {}
        return exc.code, body
    except Exception as exc:
        return 0, {'error': f'连接失败: {exc}'}


def flatten_fields(obj: Any, prefix: str = '', depth: int = 0) -> List[str]:
    """
    提取响应数据的字段路径清单（递归 2 层），用于打印「实际返回字段」。
    例：by_workshop[].workshop_id
    """
    fields: List[str] = []
    if depth > 2:
        return fields
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f'{prefix}.{key}' if prefix else key
            fields.append(path)
            fields.extend(flatten_fields(val, path, depth + 1))
    elif isinstance(obj, list) and obj:
        # 只取第一个元素做代表
        fields.extend(flatten_fields(obj[0], f'{prefix}[0]', depth + 1))
    return fields


def make_random_sequence() -> List[List[float]]:
    """生成 60×8 随机序列（fallback 模式下直接可用，无需归一化）"""
    return [[round(random.uniform(0.1, 0.9), 4) for _ in range(8)] for _ in range(60)]


# ============================================================
# 各接口检查项
# ============================================================
def check_health(base) -> Tuple[str, bool, str]:
    status, body = http_get(base, '/health')
    ok = status == 200 and body.get('status') == 'healthy'
    return 'GET /health', ok, f'HTTP {status} → {body}'


def check_overview(base) -> Tuple[str, bool, str]:
    status, body = http_get(base, '/api/v1/carbon/overview')
    data = body.get('data') or {}
    ok = status == 200 and body.get('code') == 200 and bool(data.get('by_workshop'))
    detail = f'HTTP {status}, code={body.get("code")}, total_emission={data.get("total_emission")}'
    return 'GET /carbon/overview', ok, detail


def check_heatmap(base) -> Tuple[str, bool, str]:
    status, body = http_get(
        base, '/api/v1/carbon/heatmap',
        params={'start_time': DATA_START, 'end_time': DATA_END},
    )
    data = body.get('data') or {}
    ok = status == 200 and body.get('code') == 200 and data.get('count', 0) > 0
    detail = f'HTTP {status}, code={body.get("code")}, count={data.get("count")}'
    return 'GET /carbon/heatmap', ok, detail


def check_equipment_list(base) -> Tuple[str, bool, str]:
    status, body = http_get(
        base, '/api/v1/equipment/list', params={'workshop_id': 'WS-01'},
    )
    data = body.get('data') or {}
    ok = status == 200 and data.get('count') == 17  # WS-01 固定 17 台
    detail = f'HTTP {status}, count={data.get("count")} (期望17)'
    return 'GET /equipment/list?workshop_id=WS-01', ok, detail


def check_realtime(base) -> Tuple[str, bool, str]:
    status, body = http_get(base, '/api/v1/equipment/realtime/I-9-01')
    data = body.get('data') or {}
    ok = status == 200 and body.get('code') == 200 and data.get('equipment_id') == 'I-9-01'
    detail = (
        f'HTTP {status}, power={data.get("power")}, '
        f'load_rate={data.get("load_rate")}, status={data.get("status")}'
    )
    return 'GET /equipment/realtime/I-9-01', ok, detail


def check_anomaly(base) -> Tuple[str, bool, str]:
    payload = {'equipment_id': 'I-9-01', 'sequence_data': make_random_sequence()}
    status, body = http_post(base, '/api/v1/anomaly/detect', payload)
    data = body.get('data') or {}
    ok = status == 200 and body.get('code') == 200 and 'is_anomaly' in data
    # 注意 threshold_type：未训练时是 fallback（统计偏离度），训练后是 lstm
    detail = (
        f'HTTP {status}, is_anomaly={data.get("is_anomaly")}, '
        f'severity={data.get("severity")}, threshold_type={data.get("threshold_type")}'
    )
    return 'POST /anomaly/detect', ok, detail


def check_traceability(base) -> Tuple[str, bool, str]:
    payload = {
        'equipment_id': 'I-9-01',
        'anomaly_time': '2026-08-21T14:30:00',
        'hours': 72,
    }
    status, body = http_post(base, '/api/v1/traceability/report', payload)
    data = body.get('data') or {}
    ok = (
        status == 200 and body.get('code') == 200
        and bool(data.get('root_causes'))
        and 'history_72h_summary' in data
    )
    detail = (
        f'HTTP {status}, carbon={data.get("carbon_emission")}, '
        f'baseline={data.get("baseline_emission")}, '
        f'excess={data.get("excess_emission")}, '
        f'root_causes={len(data.get("root_causes") or [])}条'
    )
    return 'POST /traceability/report', ok, detail


def check_strategy(base) -> Tuple[str, bool, str]:
    payload = {'equipment_id': 'I-9-01'}
    status, body = http_post(base, '/api/v1/strategy/generate', payload)
    data = body.get('data') or {}
    types = [s.get('strategy_type') for s in (data.get('strategies') or [])]
    ok = (
        status == 200 and data.get('count') == 3
        and set(types) == {'equipment_maintenance', 'production_scheduling', 'process_optimization'}
    )
    detail = f'HTTP {status}, count={data.get("count")}, types={types}'
    return 'POST /strategy/generate', ok, detail


def check_carbon_query(base) -> Tuple[str, bool, str]:
    payload = {
        'level': 'workshop',
        'node_id': 'WS-01',
        'start_time': DATA_START,
        'end_time': DATA_END,
    }
    status, body = http_post(base, '/api/v1/carbon/query', payload)
    data = body.get('data') or {}
    ok = status == 200 and body.get('code') == 200 and bool(data.get('records'))
    detail = f'HTTP {status}, records={len(data.get("records") or [])}'
    return 'POST /carbon/query', ok, detail


# ============================================================
# 主流程
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='算法接口自动化验证（阶段1 Step 1A）')
    parser.add_argument('--base', default=DEFAULT_BASE, help=f'算法服务地址，默认 {DEFAULT_BASE}')
    args = parser.parse_args()
    base = args.base.rstrip('/')

    print('=' * 70)
    print(f'算法接口验证 · 目标服务: {base}')
    print('=' * 70)

    checks = [
        check_health,
        check_overview,
        check_heatmap,
        check_equipment_list,
        check_realtime,
        check_anomaly,
        check_traceability,
        check_strategy,
        check_carbon_query,
    ]

    results: List[Tuple[str, bool, str]] = []
    for fn in checks:
        name, ok, detail = fn(base)
        mark = 'PASS' if ok else 'FAIL'
        results.append((name, ok, detail))
        print(f'[{mark}] {name}')
        print(f'       {detail}')

    # ---------- 汇总 ----------
    passed = sum(1 for _, ok, _ in results if ok)
    print('=' * 70)
    print(f'汇总: {passed}/{len(results)} 通过')
    if passed < len(results):
        print('排查提示：')
        print('  1. 确认算法服务已启动: python main.py（监听 8000）')
        print('  2. 确认 data/raw_data/sample_equipment_data.csv 已生成:')
        print('     python data/generate_sample_data.py')
        sys.exit(1)

    # ---------- 字段核对（验收标准第3条：实际响应字段已记录）----------
    print()
    print('-' * 70)
    print('实际响应字段核对（与 docs/algorithm_interface.md 第九章对照）：')
    probes = [
        ('/carbon/overview', http_get(base, '/api/v1/carbon/overview')[1].get('data') or {}),
        ('/carbon/heatmap', http_get(base, '/api/v1/carbon/heatmap',
                                     params={'start_time': DATA_START, 'end_time': DATA_END})[1].get('data') or {}),
        ('/anomaly/detect', http_post(base, '/api/v1/anomaly/detect',
                                      {'equipment_id': 'I-9-01', 'sequence_data': make_random_sequence()})[1].get('data') or {}),
        ('/traceability/report', http_post(base, '/api/v1/traceability/report',
                                           {'equipment_id': 'I-9-01', 'anomaly_time': '2026-08-21T14:30:00'})[1].get('data') or {}),
        ('/strategy/generate', http_post(base, '/api/v1/strategy/generate',
                                         {'equipment_id': 'I-9-01'})[1].get('data') or {}),
        ('/carbon/query', http_post(base, '/api/v1/carbon/query',
                                    {'level': 'workshop', 'node_id': 'WS-01',
                                     'start_time': DATA_START, 'end_time': DATA_END})[1].get('data') or {}),
    ]
    for name, data in probes:
        expected = EXPECTED_FIELDS.get(name, set())
        # 顶层字段比对
        actual_top = set(data.keys())
        missing = expected - actual_top
        extra = actual_top - expected
        line = f'  {name}: 顶层字段 {sorted(actual_top)}'
        if missing:
            line += f' | 文档有但实际缺失: {sorted(missing)}'
        if extra:
            line += f' | 实际多出: {sorted(extra)}'
        if not missing and not extra:
            line += ' | 与文档一致'
        print(line)

    print()
    print('已知差异说明（后端按实际字段开发，详见文档第九章）：')
    print('  1. /anomaly/detect 实际多返回 equipment_name / should_alert / threshold_type')
    print('     threshold_type 取值: lstm(已训练) / fallback(未训练兜底，联调期正常)')
    print('  2. /traceability/report 实际多返回 team_id / health_score')
    print('  3. /strategy/generate 的方案 target 字段实为 target_equipment / target_workshop')
    print('  4. scaler 文件名: 仅在设备训练后存在 scaler_{equipment_id}.pkl；')
    print('     当前未训练 → /anomaly/detect 自动走 fallback，可正常联调')
    print('  5. /equipment/realtime 和 /carbon/query 无数据时返回占位结构 + message 字段')


if __name__ == '__main__':
    main()
