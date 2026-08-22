"""
api_server —— 算法 API 服务层

本包是算法侧与后端联调的"对外契约"层：
    schemas  : Pydantic 请求/响应数据模型（前后端对接的核心契约）
    services : 业务逻辑层（调用算法模块 + 组装返回数据）
    routes   : FastAPI 路由定义（所有 HTTP 端点）

启动入口：main.py（统一挂载 router 到 FastAPI app）
联调地址：http://<算法服务器IP>:8000/docs （Swagger UI 在线测试）
"""

from api_server.routes import router as api_router

__all__ = ['api_router']
