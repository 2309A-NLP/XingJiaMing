import type { QueueStatus, DocumentTask } from '../api'

interface Props {
  queueStatus: QueueStatus | null
}

// 各阶段的图标和中文标签
const STAGE_INFO: Record<string, { icon: string; label: string }> = {
  rendering: { icon: '📄', label: '正在渲染页面图片' },
  ocr: { icon: '🔍', label: '正在OCR识别文字' },
  merging: { icon: '📝', label: '正在合并输出' },
  chunking: { icon: '✂️', label: '正在切分文本块' },
  indexing: { icon: '📐', label: '正在建立索引' },
  done: { icon: '✅', label: '解析完成' },
  vision: { icon: '👁️', label: '正在解析图片语义' },
}

// 任务状态图标
const STATUS_ICON: Record<string, string> = {
  waiting: '⏳',
  processing: '🔄',
  completed: '✅',
  failed: '❌',
}

function formatEta(seconds: number): string {
  if (seconds <= 0) return ''
  if (seconds < 60) return Math.ceil(seconds) + '秒'
  const mins = Math.floor(seconds / 60)
  const secs = Math.ceil(seconds % 60)
  return secs > 0 ? mins + '分' + secs + '秒' : mins + '分钟'
}

function TaskItem({ task }: { task: DocumentTask }) {
  const stage = STAGE_INFO[task.stage] || { icon: '⏳', label: '等待中' }
  const statusIcon = STATUS_ICON[task.status] || '⏳'
  const pct = Math.min(Math.round(task.progress_percent), 100)
  const eta = formatEta(task.eta_seconds)

  return (
    <div className={`queue-task queue-task-${task.status}`}>
      <div className="queue-task-header">
        <span className="queue-task-icon">{statusIcon}</span>
        <span className="queue-task-name">{task.filename}</span>
        {task.status === 'processing' && (
          <span className="queue-task-pct">{pct}%</span>
        )}
      </div>

      {task.status === 'processing' && (
        <>
          <div className="queue-task-stage">
            <span>{stage.icon}</span>
            <span>{stage.label}</span>
          </div>

          <div className="queue-task-bar">
            <div
              className="queue-task-bar-fill"
              style={{ width: pct + '%' }}
            />
          </div>

          <div className="queue-task-meta">
            <span>
              {task.completed_pages}/{task.total_pages} 页
              {' · '}
              第 {task.current_batch}/{task.total_batches} 批
            </span>
            {eta && <span className="queue-task-eta">还需 {eta}</span>}
          </div>
        </>
      )}

      {task.status === 'failed' && task.error && (
        <div className="queue-task-error">{task.error}</div>
      )}

      {task.status === 'completed' && (
        <div className="queue-task-done">
          解析完成 · {task.total_pages} 页 · {formatEta(task.elapsed_seconds)}
        </div>
      )}
    </div>
  )
}

export default function IngestProgressCard({ queueStatus }: Props) {
  if (!queueStatus || queueStatus.tasks.length === 0) {
    return null
  }

  const { tasks, queue_length } = queueStatus
  const processing = tasks.find(t => t.status === 'processing')
  const waiting = tasks.filter(t => t.status === 'waiting')
  const completed = tasks.filter(t => t.status === 'completed')

  return (
    <div className="queue-panel">
      <div className="queue-header">
        <span className="queue-title">📋 文档解析队列</span>
        {queue_length > 0 && (
          <span className="queue-count">剩余 {queue_length} 个</span>
        )}
      </div>

      <div className="queue-list">
        {tasks.map(task => (
          <TaskItem key={task.task_id} task={task} />
        ))}
      </div>
    </div>
  )
}