"""
test_backend —— 后端→算法链路验证脚本（阶段1 Step 1B/1C 验收用）

【用途】
    模拟"前端视角"请求后端 8001，验证后端是否正确转发到算法 8000。
    这是「前端→后端→算法」整条链路的自动化验收。

【使用方式】
    1. 启动算法服务（项目根目录）：
        python main.py                                   # 8000
    2. 启动后端服务（项目根目录，另开终端）：
        uvicorn backend.main:app --port 8001             # 8001
    3. 再开一个终端运行：
        python backend/test_backend.py

【零依赖】只用 Python 标准库 urllib，联调机开箱即用。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from urllib.parse import urlencode
from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timedelta

DEFAULT_BASE = 'http://localhost:8001'   # 后端地址（不是算法的 8000！）
TIMEOUT = 20

# 数据窗口 = 最近 7 天（与 data/generate_sample_data.py 的相对窗口保持一致）
# 动态计算，避免样本数据改为相对时间后固定日期失效
_DATA_END = datetime.now()
_DATA_START = _DATA_END - timedelta(days=7)
DATA_START = _DATA_START.replace(microsecond=0).isoformat()
DATA_END = _DATA_END.replace(microsecond=0).isoformat()


def http_get(base: str, path: str, params: Optional[Dict] = None) -> Tuple[int, Any]:
    url = base + path
    if params:
        url += '?' + urlencode(params)
    req = urllib.request.Request(url, method='GET')
    return _do(req)


def http_post(base: str, path: str, payload: Dict) -> Tuple[int, Any]:
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
        try:
            body = json.loads(exc.read().decode('utf-8'))
        except Exception:
            body = {}
        return exc.code, body
    except Exception as exc:
        return 0, {'error': f'连接失败: {exc}'}


def make_random_sequence() -> list:
    return [[round(random.uniform(0.1, 0.9), 4) for _ in range(8)] for _ in range(60)]


def main():
    parser = argparse.ArgumentParser(description='后端→算法链路验证（阶段1验收）')
    parser.add_argument('--base', default=DEFAULT_BASE, help=f'后端地址，默认 {DEFAULT_BASE}')
    args = parser.parse_args()
    base = args.base.rstrip('/')

    print('=' * 70)
    print(f'后端链路验证 · 目标后端: {base}（后端应转发至算法 8000）')
    print('=' * 70)

    checks = []

    # 1. 后端探活（同时探测算法可达性）
    status, body = http_get(base, '/api/health')
    algo_ok = isinstance(body, dict) and body.get('algorithm') == 'ok'
    checks.append(('GET /api/health（含算法可达性探测）', algo_ok, f'{body}'))

    # 2. Step 1B 三个核心 GET
    status, body = http_get(base, '/api/carbon/overview')
    data = body.get('data') or {}
    ok = status == 200 and bool(data.get('by_workshop'))
    checks.append(('GET /api/carbon/overview', ok,
                   f'total_emission={data.get("total_emission")}'))

    status, body = http_get(base, '/api/carbon/heatmap',
                            params={'start_time': DATA_START, 'end_time': DATA_END})
    data = body.get('data') or {}
    ok = status == 200 and data.get('count', 0) > 0
    checks.append(('GET /api/carbon/heatmap', ok, f'count={data.get("count")}'))

    status, body = http_get(base, '/api/equipment/realtime/I-9-01')
    data = body.get('data') or {}
    ok = status == 200 and data.get('equipment_id') == 'I-9-01'
    checks.append(('GET /api/equipment/realtime/I-9-01', ok,
                   f'power={data.get("power")}'))

    # 3. Step 1C 剩余接口
    status, body = http_get(base, '/api/equipment/list',
                            params={'workshop_id': 'WS-01'})
    data = body.get('data') or {}
    ok = status == 200 and data.get('count') == 17
    checks.append(('GET /api/equipment/list?workshop_id=WS-01', ok,
                   f'count={data.get("count")}(期望17)'))

    status, body = http_get(base, '/api/anomaly/equipment/I-9-01')
    data = body.get('data') or {}
    ok = status == 200 and 'is_anomaly' in data
    checks.append(('GET /api/anomaly/equipment/I-9-01', ok,
                   f'is_anomaly={data.get("is_anomaly")}'))

    status, body = http_post(base, '/api/anomaly/detect', {
        'equipment_id': 'I-9-01', 'sequence_data': make_random_sequence(),
    })
    data = body.get('data') or {}
    ok = status == 200 and 'is_anomaly' in data
    checks.append(('POST /api/anomaly/detect', ok,
                   f'severity={data.get("severity")}, '
                   f'threshold_type={data.get("threshold_type")}'))

    status, body = http_post(base, '/api/carbon/query', {
        'level': 'workshop', 'node_id': 'WS-01',
        'start_time': DATA_START, 'end_time': DATA_END,
    })
    data = body.get('data') or {}
    ok = status == 200 and bool(data.get('records'))
    checks.append(('POST /api/carbon/query', ok,
                   f'records={len(data.get("records") or [])}'))

    status, body = http_post(base, '/api/traceability/report', {
        'equipment_id': 'I-9-01',
        'anomaly_time': _DATA_END.replace(microsecond=0).isoformat(),
        'hours': 72,
    })
    data = body.get('data') or {}
    ok = status == 200 and bool(data.get('root_causes'))
    checks.append(('POST /api/traceability/report', ok,
                   f'excess={data.get("excess_emission")}kgCO2/h'))

    status, body = http_post(base, '/api/strategy/generate', {'equipment_id': 'I-9-01'})
    data = body.get('data') or {}
    ok = status == 200 and data.get('count') == 3
    checks.append(('POST /api/strategy/generate', ok,
                   f'count={data.get("count")}类方案'))

    # 汇总
    passed = sum(1 for _, ok, _ in checks if ok)
    for name, ok, detail in checks:
        print(f'[{"PASS" if ok else "FAIL"}] {name}')
        print(f'       {detail}')
    print('=' * 70)
    print(f'汇总: {passed}/{len(checks)} 通过')

    if passed == len(checks):
        print()
        print('阶段1链路验收通过：前端→后端(8001)→算法(8000) 整条链路可用。')
        print('下一步：前端 3 个页面（总览/热力图/设备实时）对接后端 /api 接口即可。')
    else:
        print()
        print('排查顺序：')
        print('  1. 算法服务起了吗？  python main.py           (8000)')
        print('  2. 后端服务起了吗？  uvicorn backend.main:app --port 8001  (项目根目录执行)')
        print('  3. 先单独验证算法:   python test_api.py')
        sys.exit(1)


if __name__ == '__main__':
    main()
