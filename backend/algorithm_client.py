"""
algorithm_client —— 算法服务 HTTP 客户端（后端调用算法的唯一出口）

【设计要点】
    1. 统一 base_url / 超时 / 错误处理 —— 业务路由层不需要关心 URL 拼接和异常捕获
    2. 算法返回统一结构 {code, message, data}，本客户端**原样透传**不加工
    3. 算法服务挂掉/超时时，返回 code=503 的统一错误结构而不是抛异常，
       路由层可以直接把返回值 return 给前端，前端按 code != 200 处理
    4. 仅依赖 Python 标准库（urllib），后端同学 clone 下来无需额外 pip install

【扩展指引】（后端同学）
    - 需要鉴权时：在 call_algo 里给 headers 加 token，或在 FastAPI middleware 统一拦截
    - 需要重试时：在 _do_request 外包一层 tenacity / 自写 retry
    - 需要改算法地址时：设环境变量 ALGO_BASE（默认 http://localhost:8000/api/v1）
    - 想换 httpx/aiohttp 也可以：接口签名保持 call_algo(path, method, params, json_body) 不变
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

# 算法服务地址：可用环境变量覆盖（部署时后端容器里配 ALGO_BASE 指向算法容器）
ALGO_BASE = os.environ.get('ALGO_BASE', 'http://localhost:8000/api/v1')

# 统一超时：算法接口实测 <100ms（LSTM 推理）/ <1s（聚合查询），15s 足够宽裕
TIMEOUT = 15.0


def call_algo(
    path: str,
    method: str = 'GET',
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    统一调用算法接口。

    Parameters
    ----------
    path      : 算法接口路径（不含 /api/v1 前缀），如 '/carbon/overview'
    method    : 'GET' 或 'POST'
    params    : GET query 参数，如 {'workshop_id': 'WS-01'}
    json_body : POST JSON body，原样透传给算法

    Returns
    -------
    dict —— 算法的 {code, message, data} 结构原样透传；
           算法不可达时返回 {code: 503, message: 错误信息, data: None}

    Usage
    -----
    >>> call_algo('/carbon/overview')                       # GET 无参
    >>> call_algo('/equipment/list', params={'workshop_id': 'WS-01'})
    >>> call_algo('/strategy/generate', method='POST',
    ...           json_body={'equipment_id': 'I-9-01'})
    """
    url = f'{ALGO_BASE}{path}'
    if params:
        url = f'{url}?{urllib.parse.urlencode(params)}'

    data = None
    headers = {'Accept': 'application/json'}
    if json_body is not None:
        data = json.dumps(json_body).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        # 算法侧即使 4xx/5xx 也返回 JSON 结构（{code, message, data}），直接透传
        try:
            return json.loads(exc.read().decode('utf-8'))
        except Exception:
            return {
                'code': exc.code,
                'message': f'算法返回 HTTP {exc.code}: {method} {url}',
                'data': None,
            }
    except urllib.error.URLError as exc:
        reason = getattr(exc, 'reason', exc)
        if isinstance(reason, TimeoutError) or 'timed out' in str(reason).lower():
            return {
                'code': 503,
                'message': f'算法服务响应超时(>{TIMEOUT}s): {method} {path}',
                'data': None,
            }
        # 连接拒绝 / DNS 失败等
        return {
            'code': 503,
            'message': f'算法服务不可达: {reason} ({method} {url})',
            'data': None,
        }
    except TimeoutError:
        return {
            'code': 503,
            'message': f'算法服务响应超时(>{TIMEOUT}s): {method} {path}',
            'data': None,
        }
    except Exception as exc:  # 兜底：JSON 解析失败等未知错误
        return {
            'code': 502,
            'message': f'算法响应解析失败: {exc} ({method} {url})',
            'data': None,
        }
