"""StateManager - 状态管理器，实现断点续传

核心功能:
  1. 将每页的处理状态持久化到 storage/*_status.json 文件
  2. 程序启动时加载状态，已完成的页面跳过
  3. 每处理一页立即保存状态，防止中途崩溃丢失进度

状态文件格式: BatchState (Pydantic 模型)
  存储在 storage/{pdf文件名}_status.json
"""

from __future__ import annotations
import json  # JSON 序列化
import logging
from pathlib import Path
from typing import Dict, List, Optional
from scripts.models.models import BatchState, PageProcessState, PageProcessStatus

logger = logging.getLogger(__name__)


class StateManager:
    """管理文档解析的状态持久化与恢复。
    
    每个 PDF 文件对应一个状态文件，存储在 storage/ 目录下。
    """

    def __init__(self, storage_dir: str | Path = "./storage"):
        """
        Args:
            storage_dir: 状态文件存放目录，默认 ./storage。
        """
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)  # 目录不存在则创建

    def load(self, pdf_name: str) -> Optional[BatchState]:
        """加载已存在的状态文件，实现断点续传。
        
        Args:
            pdf_name: PDF 文件名（用作状态文件标识）。
        
        Returns:
            如果存在有效状态文件则返回 BatchState，否则返回 None。
        """
        state_path = self._get_path(pdf_name)  # 计算状态文件路径
        if not state_path.exists():
            return None  # 没有状态文件，首次运行
        
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = BatchState(**data)  # 反序列化为 Pydantic 模型
            completed = len(state.completed_batches)
            logger.info("加载状态文件: %s (已完成 %d 批)", state_path.name, completed)
            return state
        except Exception as e:
            # 状态文件损坏时，自动重新开始
            logger.warning("状态文件加载失败，将重新开始: %s", e)
            return None

    def init_state(
        self, pdf_name: str, total_pages: int, batch_size: int = 50
    ) -> BatchState:
        """初始化新状态（所有页标记为 PENDING 待处理）。
        
        Args:
            pdf_name: PDF 文件名。
            total_pages: 总页数。
            batch_size: 每批页数。
        
        Returns:
            初始化的 BatchState 对象（已保存到文件）。
        """
        # 创建每页的状态对象，默认 PENDING
        pages: Dict[int, PageProcessState] = {
            pn: PageProcessState(page_no=pn)
            for pn in range(1, total_pages + 1)
        }
        state = BatchState(
            pdf_name=pdf_name,
            total_pages=total_pages,
            batch_size=batch_size,
            pages=pages,
        )
        self.save(state)  # 立即写入磁盘
        logger.info("初始化状态: %s %d 页", pdf_name, total_pages)
        return state

    def save(self, state: BatchState) -> None:
        """保存状态到 JSON 文件。
        
        Args:
            state: 当前批处理状态快照。
        """
        path = self._get_path(state.pdf_name)
        with open(path, "w", encoding="utf-8") as f:
            # model_dump() 是 Pydantic v2 的序列化方法
            json.dump(state.model_dump(), f, ensure_ascii=False, indent=2)

    def mark_page_done(
        self, state: BatchState, page_no: int, engines_used: List[str]
    ) -> None:
        """标记页面处理完成。
        
        Args:
            state: 当前状态（会被修改并自动保存）。
            page_no: 已完成的页码。
            engines_used: 使用的引擎名称列表。
        """
        if page_no in state.pages:
            state.pages[page_no].status = PageProcessStatus.ENHANCED  # 完成状态
            state.pages[page_no].engines_used = engines_used  # 记录引擎
        self.save(state)  # 立即持久化

    def mark_page_failed(
        self, state: BatchState, page_no: int, error: str
    ) -> None:
        """标记页面处理失败。
        
        Args:
            state: 当前状态。
            page_no: 失败的页码。
            error: 错误描述。
        """
        if page_no in state.pages:
            state.pages[page_no].status = PageProcessStatus.FAILED  # 失败状态
            state.pages[page_no].error = error  # 记录错误信息
            state.pages[page_no].retry_count += 1  # 增加重试计数
        self.save(state)

    def mark_batch_completed(self, state: BatchState, batch_no: int) -> None:
        """标记一个批次处理完成。
        
        Args:
            state: 当前状态。
            batch_no: 已完成的批次号。
        """
        if batch_no not in state.completed_batches:
            state.completed_batches.append(batch_no)  # 记录已完成批次
        state.current_batch = batch_no  # 更新当前批次指针
        self.save(state)

    def get_remaining(self, state: BatchState) -> List[int]:
        """获取所有待处理（含失败）的页码。
        
        Args:
            state: 当前状态。
        
        Returns:
            PENDING 或 FAILED 状态的页码列表。
        """
        return [
            pn for pn, p in state.pages.items()
            if p.status in (PageProcessStatus.PENDING, PageProcessStatus.FAILED)
        ]

    def _get_path(self, pdf_name: str) -> Path:
        """计算状态文件的完整路径。
        
        Args:
            pdf_name: PDF 文件名，如 "招股说明书1.pdf"。
        
        Returns:
            状态文件路径，如 "storage/招股说明书1_status.json"。
        """
        safe_name = Path(pdf_name).stem.replace(" ", "_")  # 文件名中的空格替换为下划线
        return self._storage_dir / f"{safe_name}_status.json"