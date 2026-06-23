from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.api.routes.quality_inspection import router as quality_inspection_router
from src.core.exceptions import ApplicationError
from src.core.logging_utils import setup_logging
from src.core.settings import get_settings


settings = get_settings()
setup_logging(settings.log_level)

app = FastAPI(title="工单十八 - 文档质量评估 Skill", version="1.0.0")
app.include_router(quality_inspection_router)


@app.exception_handler(ApplicationError)
async def handle_application_error(_, exc: ApplicationError):
    """统一项目级错误响应。"""

    return JSONResponse(
        status_code=400,
        content={"error": str(exc), "type": exc.__class__.__name__},
    )

