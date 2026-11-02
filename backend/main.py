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

from config.settings import CORS_ORIGINS

from backend.routes import router as backend_router
from backend.ingestion import router as ingestion_router
from backend.auth import router as auth_router
from backend.websocket import router as websocket_router
from backend.alarm_routes import router as alarm_router
from backend.report_routes import router as report_router
from backend.history_routes import router as history_router
from backend.ai_agent_routes import router as ai_agent_router
from backend import archive_loop, detection_loop

app = FastAPI(
    title='碳排监测系统 - 后端服务',
    description=(
        'HTTP 转发算法服务（8000）+ 数据采集 + 认证 + WebSocket 实时告警推送。'
    ),
    version='0.2.0',
)

# CORS 白名单（config.settings.CORS_ORIGINS）：默认放行 Vue 开发服务器(5173) 与
# 前端静态站(8002)，可用环境变量 CORS_ORIGINS 覆盖为实际前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# 挂载后端路由（前缀 /api）
app.include_router(backend_router)
# 挂载数据采集路由（MES/EMS/PLC 入站 + 模拟采集）
app.include_router(ingestion_router)
# 挂载认证与角色管理路由（登录 / 权限 / 用户管理）
app.include_router(auth_router)
# 挂载告警管理路由（历史查询 / 处理状态 / 手动扫描）
app.include_router(alarm_router)
# 挂载报表中心路由（月度碳排报告 / 溯源台账 / 降碳成效对比，导出 PDF/Excel）
app.include_router(report_router)
# 挂载历史时序路由（单设备时序查询 / 手动归档）
app.include_router(history_router)
# 挂载 AI 助手路由（DeepSeek 大模型 + 工具调用）
app.include_router(ai_agent_router)
# 挂载 WebSocket 实时推送端点（/ws/alerts）
app.include_router(websocket_router)


# 启动后台告警检测循环 / 历史归档调度 / 停止时优雅退出
@app.on_event('startup')
async def on_startup():
    await detection_loop.start()
    await archive_loop.start()


@app.on_event('shutdown')
async def on_shutdown():
    await detection_loop.stop()
    await archive_loop.stop()


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
