import { useState } from 'react'
import { runEvaluation } from '../api'

interface Props {
  visible: boolean
  onClose: () => void
}

interface EvalResult {
  total_questions: number
  avg_precision: number
  avg_recall: number
  avg_response_time_ms: number
  precision_at_90: number
  recall_at_95: number
  response_time_under_3s: number
  p50_response_time_ms: number
  p95_response_time_ms: number
  p99_response_time_ms: number
  under_3s_rate: number
  category_scores: Record<string, { precision: number; recall: number; time: number }>
  details: { question: string; precision: number; recall: number; response_time_ms: number; keyword_hits: number; keyword_total: number }[]
}

const CATEGORY_LABELS: Record<string, string> = {
  business: '📋 业务',
  risk: '⚠️ 风险',
  financial: '💰 财务',
  structure: '🏢 结构',
  hr: '👥 人力',
  general: '📌 通用',
}

// 达标判定
const pass = (value: number, target: number) => value >= target

export default function EvalModal({ visible, onClose }: Props) {
  const [result, setResult] = useState<EvalResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [searchMode, setSearchMode] = useState<string>('hybrid')

  if (!visible) return null

  const handleRun = async () => {
    setLoading(true)
    setResult(null)
    try {
      const data = await runEvaluation({ search_mode: searchMode, top_k: 5 })
      setResult(data)
    } catch (e: any) {
      alert('评估失败: ' + e.message)
    }
    setLoading(false)
  }

  const fmtTime = (ms: number) => ms < 1000 ? `${ms.toFixed(0)}ms` : `${(ms / 1000).toFixed(1)}s`

  // 计算总评
  const getGrade = (r: EvalResult) => {
    const p = pass(r.avg_precision, 0.9) ? 1 : 0
    const rc = pass(r.avg_recall, 0.95) ? 1 : 0
    const t = pass(r.avg_response_time_ms / 1000, 3) ? 0 : 1  // 响应时间是反向指标
    const score = p + rc + (1 - t)
    if (score >= 2.5) return { text: '优秀', emoji: '🎉', color: '#4CAF50' }
    if (score >= 1.5) return { text: '良好', emoji: '👍', color: '#ff9800' }
    return { text: '需优化', emoji: '🔧', color: '#f44336' }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content eval-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>📊 检索质量评估</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          <p className="eval-desc">用标准测试问题集评估当前检索策略，查看准确率、召回率和响应速度。</p>

          {/* 策略选择 + 运行按钮 */}
          <div className="eval-controls">
            <div className="eval-mode-group">
              {[
                { key: 'vector', label: '向量检索' },
                { key: 'bm25', label: '全文检索' },
                { key: 'hybrid', label: '混合检索' },
              ].map(m => (
                <button
                  key={m.key}
                  className={`eval-mode-btn ${searchMode === m.key ? 'active' : ''}`}
                  onClick={() => setSearchMode(m.key)}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <button className="eval-run-btn" onClick={handleRun} disabled={loading}>
              {loading ? '评估中...' : '开始评估'}
            </button>
          </div>

          {/* 加载动画 */}
          {loading && (
            <div className="eval-loading">
              <div className="eval-spinner" />
              <span>正在运行 8 个测试问题，请稍候...</span>
            </div>
          )}

          {/* 结果 */}
          {result && (() => {
            const grade = getGrade(result)
            return (
              <>
                {/* 总评卡片 */}
                <div className="eval-grade-card" style={{ borderColor: grade.color }}>
                  <div className="eval-grade-emoji">{grade.emoji}</div>
                  <div className="eval-grade-info">
                    <div className="eval-grade-text" style={{ color: grade.color }}>{grade.text}</div>
                    <div className="eval-grade-sub">
                      测试了 {result.total_questions} 个问题 · 响应时间 {fmtTime(result.avg_response_time_ms)}
                    </div>
                  </div>
                </div>

                {/* 三项核心指标 */}
                <div className="eval-metrics">
                  <EvalMetric
                    label="准确率"
                    value={result.avg_precision}
                    target={0.9}
                    format="percent"
                    description="回答中包含预期关键词的比例"
                  />
                  <EvalMetric
                    label="召回率"
                    value={result.avg_recall}
                    target={0.95}
                    format="percent"
                    description="相关文档被检索到的比例"
                  />
                  <EvalMetric
                    label="响应时间"
                    value={result.avg_response_time_ms / 1000}
                    target={3}
                    format="time"
                    description="从提问到返回答案的耗时"
                    reverse
                  />
                </div>

                {/* 达标率条 */}
                <div className="eval-pass-bar">
                  <EvalPassItem label="准确率≥90%" value={result.precision_at_90} />
                  <EvalPassItem label="召回率≥95%" value={result.recall_at_95} />
                  <EvalPassItem label="响应<3s" value={result.under_3s_rate} />
                </div>

                <div className="eval-categories">
                  <div className="eval-section-title">延迟分位数</div>
                  <div className="eval-cat-row">
                    <span className="eval-cat-name">P50</span>
                    <div className="eval-cat-bars">
                      <span className={result.p50_response_time_ms < 3000 ? 'eval-good' : 'eval-bad'}>{fmtTime(result.p50_response_time_ms)}</span>
                    </div>
                  </div>
                  <div className="eval-cat-row">
                    <span className="eval-cat-name">P95</span>
                    <div className="eval-cat-bars">
                      <span className={result.p95_response_time_ms < 3000 ? 'eval-good' : 'eval-bad'}>{fmtTime(result.p95_response_time_ms)}</span>
                    </div>
                  </div>
                  <div className="eval-cat-row">
                    <span className="eval-cat-name">P99</span>
                    <div className="eval-cat-bars">
                      <span className={result.p99_response_time_ms < 3000 ? 'eval-good' : 'eval-bad'}>{fmtTime(result.p99_response_time_ms)}</span>
                    </div>
                  </div>
                </div>

                {/* 分类得分 */}
                {Object.keys(result.category_scores).length > 0 && (
                  <div className="eval-categories">
                    <div className="eval-section-title">分类得分</div>
                    {Object.entries(result.category_scores).map(([cat, scores]) => (
                      <div key={cat} className="eval-cat-row">
                        <span className="eval-cat-name">{CATEGORY_LABELS[cat] || cat}</span>
                        <div className="eval-cat-bars">
                          <MiniBar value={scores.precision} target={0.9} label="准确" />
                          <MiniBar value={scores.recall} target={0.95} label="召回" />
                        </div>
                        <span className="eval-cat-time">{fmtTime(scores.time)}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* 逐题详情（可折叠） */}
                <details className="eval-details-section">
                  <summary className="eval-section-title">逐题详情 ({result.details.length})</summary>
                  <div className="eval-details">
                    {result.details.map((d, i) => (
                      <div key={i} className="eval-detail-row">
                        <div className="eval-detail-q">
                          <span className="eval-detail-num">#{i + 1}</span>
                          {d.question}
                        </div>
                        <div className="eval-detail-scores">
                          <span className={pass(d.precision, 0.9) ? 'eval-good' : 'eval-bad'}>
                            准确 {(d.precision * 100).toFixed(0)}%
                          </span>
                          <span className={pass(d.recall, 0.95) ? 'eval-good' : 'eval-bad'}>
                            召回 {(d.recall * 100).toFixed(0)}%
                          </span>
                          <span className={d.response_time_ms < 3000 ? 'eval-good' : 'eval-bad'}>
                            {fmtTime(d.response_time_ms)}
                          </span>
                          <span className="eval-detail-kw">
                            关键词 {d.keyword_hits}/{d.keyword_total}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </details>
              </>
            )
          })()}
        </div>
      </div>
    </div>
  )
}

// 单个指标卡片
function EvalMetric({ label, value, target, format, description, reverse }: {
  label: string; value: number; target: number; format: 'percent' | 'time'; description: string; reverse?: boolean
}) {
  const isGood = reverse ? value < target : value >= target
  const pct = format === 'percent' ? value * 100 : value
  const display = format === 'percent' ? `${pct.toFixed(1)}%` : `${pct.toFixed(1)}s`
  const targetDisplay = format === 'percent' ? `目标 ≥${(target * 100).toFixed(0)}%` : `目标 <${target}s`

  // 进度条宽度
  const barPct = format === 'percent'
    ? Math.min(value / target * 100, 100)
    : Math.min(target / Math.max(value, 0.1) * 100, 100)

  return (
    <div className="eval-metric">
      <div className="eval-metric-label">{label}</div>
      <div className={`eval-metric-value ${isGood ? 'eval-good' : 'eval-bad'}`}>{display}</div>
      <div className="eval-metric-bar">
        <div
          className={`eval-metric-bar-fill ${isGood ? 'eval-good-bg' : 'eval-bad-bg'}`}
          style={{ width: `${barPct}%` }}
        />
      </div>
      <div className="eval-metric-target">{targetDisplay}</div>
      <div className="eval-metric-desc">{description}</div>
    </div>
  )
}

// 达标率条目
function EvalPassItem({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100)
  return (
    <div className="eval-pass-item">
      <div className="eval-pass-label">{label}</div>
      <div className="eval-pass-bar-outer">
        <div
          className={`eval-pass-bar-inner ${pct >= 80 ? 'eval-good-bg' : pct >= 50 ? 'eval-warn-bg' : 'eval-bad-bg'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="eval-pass-pct">{pct}%</div>
    </div>
  )
}

// 迷你条形图
function MiniBar({ value, target, label }: { value: number; target: number; label: string }) {
  const pct = Math.min(value * 100, 100)
  const isGood = value >= target
  return (
    <div className="eval-mini-bar">
      <span className="eval-mini-label">{label}</span>
      <div className="eval-mini-outer">
        <div className={`eval-mini-inner ${isGood ? 'eval-good-bg' : 'eval-bad-bg'}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="eval-mini-pct">{pct.toFixed(0)}%</span>
    </div>
  )
}
