"""
main —— 算法服务应用入口 + 全站一键启动

【单独启动算法服务】
    uvicorn main:app --host 0.0.0.0 --port 8000
    访问：http://localhost:8000/docs

【一键启动整个网站】（算法 8000 + 后端 8001 + 前端静态站 8002）
    在项目根目录执行：
        python main.py
    推荐用项目虚拟环境运行（避免系统 Python 缺依赖）：
        ./env/Scripts/python.exe main.py
    启动后访问：
        http://localhost:8002/              前端页面
        http://localhost:8001/docs         后端接口文档
        http://localhost:8000/docs         算法接口文档

后端同学：算法服务监听 8000 端口，后端通过 HTTP 调用。
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_server.routes import router as api_router
from config.settings import API_CONFIG, CORS_ORIGINS


app = FastAPI(
    title='数字孪生锂电工厂碳排AI监测系统 - 算法服务',
    description=(
        '提供碳排核算（IPCC 因子法 + 四级聚合）、LSTM 异常检测（自编码器 + 自适应阈值）、'
        '溯源分析（72h 历史 + 根因定位）、AI 降碳方案生成（运维/排班/工艺优化三类）'
        '等算法接口。'
    ),
    version='1.0.0',
    contact={
        'name': '算法负责人',
        'role': '队长（算法）',
    },
)

# 跨域配置（前端联调需要）：显式白名单，避免 allow_origins=['*'] 与 credentials 冲突
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 挂载算法路由（前缀 /api/v1）
app.include_router(api_router)


@app.get('/', summary='服务根信息')
async def root():
    return {
        'service': '碳排AI监测算法服务',
        'version': '1.0.0',
        'status': 'running',
        'docs': '/docs',
        'endpoints_prefix': '/api/v1',
    }


@app.get('/health', summary='健康检查')
async def health_check():
    return {'status': 'healthy'}


@app.on_event('startup')
async def _ensure_sample_data():
    """启动时兜底：样本数据缺失或过期(>24h)则自动重新生成，避免近 7 天接口返回空数据"""
    from data.generate_sample_data import ensure_sample_data
    await asyncio.to_thread(ensure_sample_data)


if __name__ == '__main__':
    # ============================================================
    # 一键启动整个网站：算法服务(8000) + 后端服务(8001) + 前端静态站(8002)
    # 在项目根目录执行：  python main.py
    # 推荐：              ./env/Scripts/python.exe main.py
    # 单独启动算法服务仍可用：  uvicorn main:app --port 8000
    # ============================================================
    import signal
    import subprocess
    import sys
    import time
    from pathlib import Path

    _BASE = Path(__file__).resolve().parent
    _ENV_PY = _BASE / 'env' / 'Scripts' / 'python.exe'
    PY = str(_ENV_PY) if _ENV_PY.exists() else sys.executable

    # (名称, 启动命令) —— 端口集中在此修改
    SERVICES = [
        ('算法服务(8000)', [PY, '-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8000']),
        ('后端服务(8001)', [PY, '-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', '8001']),
        ('前端站点(8002)', [PY, '-m', 'http.server', '8002', '--directory', 'web/dist']),
    ]

    _procs = []

    def _stop(*_args):
        print('\n正在停止全部服务……')
        for _p in _procs:
            try:
                _p.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    try:
        signal.signal(signal.SIGTERM, _stop)
    except Exception:
        pass

    print('=' * 62)
    print('  数字孪生锂电工厂 · 碳排AI监测系统 —— 一键启动')
    print('=' * 62)
    for _name, _cmd in SERVICES:
        print(f'  [启动] {_name}')
        _procs.append(subprocess.Popen(_cmd, cwd=str(_BASE)))
        time.sleep(0.6)

    print('-' * 62)
    print('  前端页面   http://localhost:8002/')
    print('  后端接口   http://localhost:8001/docs')
    print('  算法接口   http://localhost:8000/docs')
    print('  按 Ctrl+C 停止全部服务')
    print('=' * 62)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _stop()
