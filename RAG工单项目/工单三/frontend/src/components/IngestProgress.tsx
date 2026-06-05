import type { IngestProgress } from '../api'

interface Props {
  progress: IngestProgress
}

// 各阶段的图标和中文标签
const STAGE_INFO: Record<string, { icon: string; label: string }> = {
  rendering: { icon: '📄', label: '正在渲染页面图片' },
  ocr: { icon: '🔍', label: '正在OCR识别文字' },
  merging: { icon: '📝', label: '正在合并输出' },
  chunking: { icon: '✂️', label: '正在切分文本块' },
  indexing: { icon: '📐', label: '正在建立索引' },
  done: { icon: '✅', label: '解析完成' },
}

function formatEta(seconds: number): string {
  if (seconds <= 0) return ''
  if (seconds < 60) return Math.ceil(seconds) + '秒'
  const mins = Math.floor(seconds / 60)
  const secs = Math.ceil(seconds % 60)
  return secs > 0 ? mins + '分' + secs + '秒' : mins + '分钟'
}

export default function IngestProgressCard({ progress }: Props) {
  const stage = STAGE_INFO[progress.stage] || { icon: '⏳', label: '正在处理' }
  const pct = Math.min(Math.round(progress.progress_percent), 100)
  const eta = formatEta(progress.eta_seconds)

  return (
    <div className='ingest-progress-card'>
      <div className='ingest-file-info'>
        <span className='ingest-file-icon'>{stage.icon}</span>
        <span className='ingest-filename'>{progress.filename}</span>
      </div>

      <div className='ingest-stage'>
        <span className='ingest-stage-icon'>{stage.icon}</span>
        <span className='ingest-stage-label'>{stage.label}</span>
      </div>

      <div className='ingest-bar-wrapper'>
        <div className='ingest-bar-track'>
          <div
            className='ingest-bar-fill'
            style={{ width: pct + '%' }}
          />
        </div>
        <span className='ingest-pct'>{pct}%</span>
      </div>

      <div className='ingest-meta'>
        <span className='ingest-batch'>
          {'第 ' + progress.current_batch + ' / ' + progress.total_batches + ' 批'}
          {' · '}
          {progress.completed_pages + ' / ' + progress.total_pages + ' 页'}
        </span>
        {eta && <span className='ingest-eta'>{'预计还需 ' + eta}</span>}
      </div>
    </div>
  )
}
