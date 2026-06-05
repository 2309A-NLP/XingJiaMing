"""翻译路由"""
import logging
from fastapi import APIRouter
from api.models import TranslateRequest, TranslateResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post('/translate', response_model=TranslateResponse)
async def translate(req: TranslateRequest):
    """翻译文本"""
    from scripts.pipeline.translator import translate_text
    translated = translate_text(req.text, req.source_lang, req.target_lang)
    return TranslateResponse(translated=translated, original=req.text)