"""
main —— FastAPI 应用入口

启动命令：
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
或直接：
    python main.py

启动后访问：
    http://localhost:8000/docs          Swagger UI（在线测试所有接口）
    http://localhost:8000/health        健康检查
    http://localhost:8000/api/v1/...    算法接口

后端同学：本服务监听 8000 端口，后端通过 HTTP 调用。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_server.routes import router as api_router
from config.settings import API_CONFIG


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

# 跨域配置（前端联调需要）
app.add_middleware(
    CORSMiddleware,
    # 开发阶段全开，生产部署建议改为前端域名白名单如 ['http://your-frontend.com']
    allow_origins=['*'],
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


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        'main:app',
        host=API_CONFIG['host'],
        port=API_CONFIG['port'],
        reload=API_CONFIG['reload'],
    )
