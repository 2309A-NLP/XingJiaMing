"""Pydantic 数据模型定义"""
from typing import Optional, List
from pydantic import BaseModel


# ========== 请求模型 ==========

class QueryRequest(BaseModel):
    """问答请求"""
    question: str
    top_k: int = 5
    page_filter: Optional[list] = None
    language: str = "zh"

    def check_input(self) -> None:
        """输入校验"""
        q = self.question.strip()
        if not q:
            raise ValueError("question cannot be empty")
        if len(q) > 500:
            raise ValueError("question too long (max 500)")
        if self.top_k < 1 or self.top_k > 20:
            raise ValueError("top_k must be 1-20")
        if self.language not in ("zh", "en"):
            raise ValueError("language must be zh or en")


class TranslateRequest(BaseModel):
    """翻译请求"""
    text: str
    source_lang: str = "zh"
    target_lang: str = "en"


class ChatCreate(BaseModel):
    """创建/更新对话"""
    chat_id: str
    title: str = "新对话"


class MessageCreate(BaseModel):
    """添加消息"""
    msg_id: str
    role: str
    content: str
    sources: list = []
    query_analysis: Optional[dict] = None
    response_time: Optional[float] = None
    timestamp: Optional[float] = None


# ========== 响应模型 ==========

class QueryResponse(BaseModel):
    """问答响应"""
    answer: str
    sources: list
    query_analysis: dict


class QueryAnalysisResponse(BaseModel):
    """Query 分析响应"""
    original_query: str
    intent: str
    intent_description: str
    disambiguated_query: str
    sub_queries: List[str]
    keywords: List[str]
    confidence: float


class TranslateResponse(BaseModel):
    """翻译响应"""
    translated: str
    original: str


class CompareResponse(BaseModel):
    """RAG vs LLM 对比结果"""
    rag_answer: str
    rag_sources: list
    llm_answer: str
    response_time_ms: int


class BugCheckResult(BaseModel):
    """Bug 检查结果"""
    bug_id: str
    description: str
    status: str  # "ok" or "error"
    message: str


class SelfCheckResponse(BaseModel):
    """自检响应"""
    total: int
    passed: int
    failed: int
    results: list