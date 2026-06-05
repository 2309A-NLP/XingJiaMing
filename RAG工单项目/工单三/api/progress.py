"""文档解析进度追踪

用内存字典记录当前解析任务的进度，前端轮询获取。
"""
import time
from typing import Optional

# 当前任务进度
_progress = {
    'active': False,
    'filename': '',
    'total_pages': 0,
    'completed_pages': 0,
    'current_batch': 0,
    'total_batches': 0,
    'stage': '',           # rendering / ocr / chunking / indexing / done
    'start_time': 0,
    'batch_times': [],     # 每批耗时，用于估算剩余时间
}


def start(filename: str, total_pages: int, total_batches: int) -> None:
    """任务开始"""
    _progress.update({
        'active': True,
        'filename': filename,
        'total_pages': total_pages,
        'completed_pages': 0,
        'current_batch': 0,
        'total_batches': total_batches,
        'stage': 'rendering',
        'start_time': time.time(),
        'batch_times': [],
    })


def update_batch(batch_no: int, pages_in_batch: int, batch_elapsed: float) -> None:
    """每批完成时更新"""
    _progress['current_batch'] = batch_no
    _progress['completed_pages'] = min(batch_no * pages_in_batch, _progress['total_pages'])
    _progress['batch_times'].append(batch_elapsed)
    _progress['stage'] = 'ocr'


def update_stage(stage: str) -> None:
    """更新当前阶段"""
    _progress['stage'] = stage


def finish() -> None:
    """任务完成"""
    _progress['active'] = False
    _progress['completed_pages'] = _progress['total_pages']
    _progress['stage'] = 'done'


def get_progress() -> dict:
    """获取当前进度（供 API 返回）"""
    p = _progress.copy()
    if not p['active']:
        return p

    # 估算剩余时间
    elapsed = time.time() - p['start_time']
    batch_times = p['batch_times']

    if batch_times and p['current_batch'] > 0:
        avg_time = sum(batch_times) / len(batch_times)
        remaining_batches = p['total_batches'] - p['current_batch']
        eta_seconds = avg_time * remaining_batches
    elif p['total_batches'] > 0:
        # 还没有批次完成，用粗略估计
        eta_seconds = 0
    else:
        eta_seconds = 0

    p['elapsed_seconds'] = round(elapsed, 1)
    p['eta_seconds'] = round(eta_seconds, 1)
    p['progress_percent'] = round(p['completed_pages'] / max(p['total_pages'], 1) * 100, 1)

    return p