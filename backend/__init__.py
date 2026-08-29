"""
backend —— 后端联调脚手架（阶段1 Step 1B / 1C 交付）

【这是什么】
    一个最小可运行的 FastAPI 后端骨架，职责 = 「HTTP 转发算法服务 + 业务组装起点」。
    后端同学可以在此基础上扩展：数据库、认证、告警推送、报表导出等。

【端口约定】（重要，避免联调时端口撞车）
    算法服务: 8000   ← 本项目根目录 main.py
    后端服务: 8001   ← 本目录 backend/main.py
    前端只对接后端 8001，后端再调算法 8000。

【启动方式】（必须在本项目根目录执行，包导入依赖项目根在 sys.path）
    uvicorn backend.main:app --host 0.0.0.0 --port 8001 --reload

【在线文档】
    http://localhost:8001/docs （后端自己的 Swagger）
    http://localhost:8000/docs （算法服务的 Swagger，排查转发问题时用）

【目录内文件】
    algorithm_client.py  算法服务 HTTP 客户端（唯一出口，统一超时/错误处理）
    routes.py            后端路由 = 转发算法的 8 个端点
    main.py              FastAPI 入口（CORS 已开，前端可直接调）
    test_backend.py      链路验证脚本：前端视角打后端 → 后端转发算法

【阶段1验收对应关系】
    Step 1B：本目录 + 3 个 GET 转发（overview / heatmap / realtime）
    Step 1C：剩余 5 个端点转发（anomaly/detect、traceability、strategy、
             equipment/list、carbon/query、anomaly/equipment/{id}）
"""

from backend.routes import router as backend_router

__all__ = ['backend_router']
