"""
ai_agent_routes —— AI 助手路由

POST /api/agent/chat    对话（需登录），body: {"messages":[{"role":"user","content":"..."}]}
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.ai_agent import chat, stream_chat
from backend.security import get_current_user
from database.models import User

router = APIRouter(prefix='/api/agent', tags=['AI 助手'])


class ChatMessage(BaseModel):
    role: str = Field(..., description='角色：user / assistant')
    content: str = Field(..., description='消息内容')


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description='对话历史，最后一条为当前提问')


class ChatResponse(BaseModel):
    role: str = Field('assistant', description='固定 assistant')
    reply: str = Field(..., description='AI 回答')


@router.post('/chat', summary='AI 助手对话')
async def chat_endpoint(req: ChatRequest, _: User = Depends(get_current_user)):
    msgs = [{'role': m.role, 'content': m.content} for m in req.messages]
    reply = chat(msgs)
    return ChatResponse(reply=reply)


@router.post('/chat/stream', summary='AI 助手对话（SSE 流式，打字机效果）')
async def chat_stream(req: ChatRequest, _: User = Depends(get_current_user)):
    """返回 text/event-stream：
    data: {"type":"delta","content":"..."}  文本块
    data: {"type":"status","content":"..."}  工具调用进度
    data: {"type":"done"}
    """
    msgs = [{'role': m.role, 'content': m.content} for m in req.messages]
    return StreamingResponse(
        stream_chat(msgs),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            # nginx 反代时避免缓冲导致"一次性吐出"
            'X-Accel-Buffering': 'no',
        },
    )