"""对话管理路由"""
import os
import logging
from fastapi import APIRouter
from scripts.memory.chat_store import ChatStore
from scripts.memory.session_memory import SessionMemory
from api.models import ChatCreate, MessageCreate

logger = logging.getLogger(__name__)
router = APIRouter()

# 初始化存储
chat_store = ChatStore(db_path=os.path.join(os.path.dirname(__file__), '..', '..', 'storage', 'chats.db'))
session_mem = SessionMemory()


@router.get("/chats")
async def list_chats():
    """获取对话列表"""
    return chat_store.get_chats()


@router.post("/chats")
async def create_chat(req: ChatCreate):
    """创建新对话"""
    return chat_store.create_chat(req.chat_id, req.title)


@router.get("/chats/{chat_id}/messages")
async def get_messages(chat_id: str):
    """获取对话消息"""
    return chat_store.get_messages(chat_id)


@router.post("/chats/{chat_id}/messages")
async def add_message(chat_id: str, req: MessageCreate):
    """添加消息"""
    chat_store.add_message(
        chat_id, req.msg_id, req.role, req.content,
        req.sources, req.timestamp, req.query_analysis, req.response_time
    )
    session_mem.add(chat_id, req.role, req.content)
    return {"status": "ok"}


@router.put("/chats/{chat_id}")
async def update_chat(chat_id: str, req: ChatCreate):
    """更新对话标题"""
    chat_store.update_chat_title(chat_id, req.title)
    return {"status": "ok"}


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """删除对话"""
    chat_store.delete_chat(chat_id)
    session_mem.clear(chat_id)
    return {"status": "ok"}