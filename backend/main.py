"""
backend.main —— 后端服务入口（阶段1脚手架）

【启动】（必须在项目根目录执行，保证 backend 包可导入）
    uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload

【验证】
    python backend/test_backend.py        # 链路测试：前端视角 → 后端 → 算法

【说明】
    - CORS 全开：前端（无论跑在哪个端口）都能直连后端 8001
    - 阶段1 无数据库、无认证，只做算法转发；阶段2 在此基础上扩展
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import router as backend_router

app = FastAPI(
    title='碳排监测系统 - 后端服务（阶段1脚手架）',
    description=(
        'HTTP 转发算法服务（8000）+ 业务组装起点。'
        '阶段1 全部为透传转发；阶段2 接数据库/认证/告警推送。'
    ),
    version='0.1.0',
)

# CORS 全开（联调期）：前端直连后端 8001 不受浏览器同源限制
# 上线前改为前端域名白名单，如 ['http://localhost:5173', 'https://your-frontend.com']
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 挂载后端路由（前缀 /api）
app.include_router(backend_router)


@app.get('/', summary='后端根信息')
async def root():
    return {
        'service': '碳排监测系统后端服务（阶段1脚手架）',
        'status': 'running',
        'docs': '/docs',
        'algorithm_base': 'http://localhost:8000/api/v1',
        'note': '所有业务接口在 /api 前缀下，见 /docs',
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('backend.main:app', host='0.0.0.0', port=8001, reload=True)
