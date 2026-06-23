"""嵌入模型管理路由"""
import logging
from fastapi import APIRouter
from api.init import get_components

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/embedding/models")
async def list_embedding_models():
    """获取所有可用的嵌入模型"""
    comp = get_components()
    embedder = comp.get('embedder')
    if not embedder:
        return {"models": [], "current": None}

    return {
        "models": [
            {"name": name, "path": path}
            for name, path in embedder.available_models.items()
        ],
        "current": embedder.current_model
    }


@router.post("/embedding/switch")
async def switch_embedding_model(model_name: str):
    """切换嵌入模型"""
    comp = get_components()
    embedder = comp.get('embedder')
    if not embedder:
        return {"status": "error", "message": "嵌入模型未初始化"}

    success = embedder.switch_model(model_name)
    if success:
        return {"status": "ok", "current": embedder.current_model, "dim": embedder.dim}
    else:
        return {"status": "error", "message": f"模型 {model_name} 不可用"}
