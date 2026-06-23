import { useEffect, useRef, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, CompareResult, IngestProgress, QueueStatus } from '../api'
import { queryCompare, queryLightRAGCompare, queryLightRAGStream, pauseIngest, resumeIngest } from '../api'
import type { LightRAGCompareResult } from '../api'


interface Props {
  messages: Message[]
  loading: boolean
  onHintClick?: (text: string) => void
  ingestProgress?: IngestProgress | null
  queueStatus?: QueueStatus | null
}

const HINTS = [
  '这家公司的主营业务是什么？',
  '公司的主要客户群体有哪些？',
  '公司面临哪些经营风险？',
  '公司的核心竞争力是什么？',
]

const INTENT_LABELS: Record<string, string> = {
  factoid: '事实性问题',
  comparison: '比较性问题',
  summary: '总结性问题',
  explanation: '解释性问题',
  list: '列举性问题',
  definition: '定义性问题',
  temporal: '时间性问题',
  quantitative: '数量性问题',
  other: '其他类型',
  greeting: '问候/闲聊',
}

// 判断消息是否是解析进度占位消息
function isIngestPlaceholder(msg: Message): boolean {
  return msg.role === 'assistant' && msg.content === '正在解析文档，请稍候...'
}

export default function ChatArea({ messages, loading, onHintClick, ingestProgress, queueStatus }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, ingestProgress])

  return (
    <div className="chat-area">
      {messages.length === 0 && !loading && (
        <div className="welcome">
          <div className="welcome-logo">AI</div>
          <h2>有什么可以帮你的？</h2>
          <div className="welcome-hints">
            {HINTS.map((h, i) => (
              <div key={i} className="hint-card" onClick={() => onHintClick?.(h)}>
                {h}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 队列进度 - 内嵌在聊天区 */}
      {queueStatus && queueStatus.tasks.length > 0 && queueStatus.tasks.some(t => t.status === 'processing' || t.status === 'waiting') && (
        <div className="message assistant">
          <div className="message-inner">
            <div className="avatar">AI</div>
            <div className="bubble ingest-bubble">
              <QueueProgressCard queueStatus={queueStatus} />
            </div>
          </div>
        </div>
      )}

      {messages.map((msg, idx) => {
        // 解析进度占位消息 → 跳过（已用队列面板替代）
        if (isIngestPlaceholder(msg)) {
          return null
        }

        return (
          <div key={msg.id} className={`message ${msg.role}`}>
            <div className="message-inner">
              <div className="avatar">{msg.role === 'user' ? 'U' : 'AI'}</div>
              <div className="bubble">
                {msg.role === 'assistant' && !msg.content && loading ? (
                  <div className="typing">
                    <span></span><span></span><span></span>
                  </div>
                ) : (
                  <>
                    <div className="content markdown-body">
                      <AssistantMarkdown content={msg.content} />
                    </div>
                    <TranslateButton text={msg.content} />
                    {msg.translation && (
                      <div className="translation-box">
                        <AssistantMarkdown content={msg.translation} />
                      </div>
                    )}
                    {msg.sources && msg.sources.length > 0 && msg.content.length > 30 && (
                      <SourceTags sources={msg.sources} />
                    )}
                    {msg.role === "assistant" && msg.responseTime !== undefined && (
                      <div className="response-time">⏱ 响应时间 {msg.responseTime}s</div>
                    )}
                    {msg.role === "assistant" && msg.search_config && (
                      <SearchConfigInfo config={msg.search_config} />
                    )}
                    {idx > 0 && messages[idx-1]?.role === "user" && (
                      <CompareButton question={messages[idx-1].content} />
                    )}
                    {idx > 0 && messages[idx-1]?.role === "user" && (
                      <LightRAGCompareButton question={messages[idx-1].content} ragAnswer={(msg as any).rag_answer || msg.content} lightragAnswer={(msg as any).lightrag_answer || ''} />
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        )
      })}

      <div ref={bottomRef} />
    </div>
  )
}


// 检索配置信息标签
function SearchConfigInfo({ config }: { config: { search_mode: string; reranker_type: string; rerank_enabled: boolean; match_mode: string } }) {
  const modeLabels: Record<string, string> = {
    vector: '向量检索',
    bm25: '全文检索',
    hybrid: '混合检索',
  }
  const rerankerLabels: Record<string, string> = {
    bge: 'BGE',
    llm: 'LLM',
    tfidf: 'TF-IDF',
    adaptive: '自适应',
  }
  const matchLabels: Record<string, string> = {
    standard: '标准匹配',
    boolean: '布尔查询',
    phrase: '短语匹配',
    fuzzy: '模糊匹配',
    auto: '自动检测',
  }
  return (
    <div className="search-config-info">
      <span className="config-tag">模式: {modeLabels[config.search_mode] || config.search_mode}</span>
      {config.match_mode && (
        <span className="config-tag">匹配: {matchLabels[config.match_mode] || config.match_mode}</span>
      )}
      {config.rerank_enabled && (
        <span className="config-tag">重排: {rerankerLabels[config.reranker_type] || config.reranker_type}</span>
      )}
      {config.embedding_model && (
        <span className="config-tag">模型: {config.embedding_model}</span>
      )}
    </div>
  )
}
function SourceTags({ sources }: { sources: NonNullable<Message['sources']> }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="sources">
      <button className="source-toggle" onClick={() => setExpanded(v => !v)}>
        {expanded ? '收起来源 ▲' : '展开来源 ▼'}
      </button>
      {expanded && (
        <>
          <div className="source-tags">
            {sources.map((s, i) => (
              <span key={i} className="source-tag">
                {s.section_title || s.chunk_id}
              </span>
            ))}
          </div>
          <div className="source-details">
            {sources.map((s, i) => (
              <div key={i} className="source-detail-item">
                <div className="source-detail-title">{s.section_title || s.chunk_id}</div>
                <pre className="source-detail-content">{s.content}</pre>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function TranslateButton({ text }: { text: string }) {
  const [translation, setTranslation] = useState<string | null>(null)
  const [show, setShow] = useState(false)
  const [loading, setLoading] = useState(false)

  if (!text || text.length < 1) return null

  const chineseChars = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const totalChars = text.length
  const hasChinese = totalChars > 0 && (chineseChars / totalChars) > 0.3

  const handleTranslate = async () => {
    if (translation) {
      setShow(!show)
      return
    }
    setLoading(true)
    try {
      const { translateText } = await import('../api')
      const result = await translateText(text, hasChinese ? 'zh' : 'en', hasChinese ? 'en' : 'zh')
      setTranslation(result)
      setShow(true)
    } catch (e) {
      console.error('翻译失败:', e)
    }
    setLoading(false)
  }

  return (
    <>
      <button className="translate-btn" onClick={handleTranslate} disabled={loading}>
        {loading ? '翻译中...' : show ? '收起翻译' : hasChinese ? '翻译成英文' : '翻译成中文'}
      </button>
      {show && translation && (
        <div className="translation-box">
          <AssistantMarkdown content={translation} />
        </div>
      )}
    </>
  )
}

function AssistantMarkdown({ content }: { content: string }) {
  const containerRef = useRef<HTMLDivElement>(null)

  const copyTableMarkdown = useCallback((table: HTMLTableElement) => {
    const rows = Array.from(table.querySelectorAll('tr'))
    const matrix = rows.map(row => Array.from(row.querySelectorAll('th, td')).map(cell => cell.textContent?.trim() ?? ''))
    const md = matrix.map(row => '| ' + row.join(' | ') + ' |').join('\n')
    navigator.clipboard.writeText(md).catch(() => {})
  }, [])

  useEffect(() => {
    const root = containerRef.current
    if (!root) return
    const tables = root.querySelectorAll('table')
    tables.forEach(table => {
      if (table.dataset.copyReady === '1') return
      table.dataset.copyReady = '1'
      const wrapper = document.createElement('div')
      wrapper.className = 'table-copy-wrapper'
      const btn = document.createElement('button')
      btn.className = 'table-copy-btn'
      btn.textContent = '复制表格'
      btn.addEventListener('click', (e) => {
        e.stopPropagation()
        copyTableMarkdown(table)
        btn.textContent = '已复制 ✓'
        setTimeout(() => { btn.textContent = '复制表格' }, 1500)
      })
      wrapper.appendChild(btn)
      table.parentElement?.insertBefore(wrapper, table)
    })
  }, [content, copyTableMarkdown])

  return (
    <div ref={containerRef}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

function CompareButton({ question }: { question: string }) {
  const [result, setResult] = useState<CompareResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [show, setShow] = useState(false)

  const handleCompare = async () => {
    if (result) { setShow(true); return }
    setLoading(true)
    try {
      const data = await queryCompare(question)
      setResult(data)
      setShow(true)
    } catch { }
    setLoading(false)
  }

  if (!question) return null

  return (
    <>
      <div className="compare-section">
        <button className="compare-btn" onClick={handleCompare} disabled={loading}>
          {loading ? '对比中...' : 'RAG vs LLM 对比'}
        </button>
      </div>
      {show && result && (
        <div className="compare-overlay" onClick={() => setShow(false)}>
          <div className="compare-modal" onClick={e => e.stopPropagation()}>
            <div className="compare-modal-header">
              <span className="compare-modal-title">RAG vs LLM 对比分析</span>
              <button className="compare-close" onClick={() => setShow(false)}>✕</button>
            </div>
            <div className="compare-modal-body">
              <div className="compare-col">
                <div className="compare-label rag">RAG 检索回答</div>
                <div className="compare-content markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.rag_answer}</ReactMarkdown>
                </div>
              </div>
              <div className="compare-divider" />
              <div className="compare-col">
                <div className="compare-label llm">纯 LLM 回答</div>
                <div className="compare-content markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.llm_answer}</ReactMarkdown>
                </div>
              </div>
            </div>
            <div className="compare-modal-footer">
              <span className="compare-stats">耗时 {result.response_time_ms}ms · 来源 {result.rag_sources.length} 条</span>
              <button className="compare-close-btn" onClick={() => setShow(false)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}


// RAG vs LightRAG 对比按钮（流式版本）
function LightRAGCompareButton({ question, ragAnswer, lightragAnswer: initialLightragAnswer }: { question: string; ragAnswer: string; lightragAnswer?: string }) {
  const [show, setShow] = useState(false)
  const [lightragContent, setLightragContent] = useState(initialLightragAnswer || '')
  const [streaming, setStreaming] = useState(false)
  const [done, setDone] = useState(!!initialLightragAnswer)
  const [error, setError] = useState<string | null>(null)
  const [startTime, setStartTime] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  // 当外部传入 lightragAnswer 更新时，同步到内部状态
  useEffect(() => {
    if (initialLightragAnswer && !done) {
      setLightragContent(initialLightragAnswer)
      setDone(true)
      setStreaming(false)
    }
  }, [initialLightragAnswer])

  const handleOpen = async () => {
    setShow(true)
    if (streaming || done) return // 已有结果或正在流式输出

    const start = Date.now()
    setStreaming(true)
    setStartTime(start)
    setLightragContent('')
    setError(null)

    await queryLightRAGStream(
      question,
      'hybrid',
      (token) => {
        setLightragContent(prev => prev + token)
        setElapsed(Math.round((Date.now() - start) / 100) / 10)
      },
      () => {
        setDone(true)
        setStreaming(false)
        setElapsed(Math.round((Date.now() - start) / 100) / 10)
      },
      (err) => {
        setError(err)
        setStreaming(false)
        setDone(true)
      },
    )
  }

  if (!question) return null

  return (
    <>
      <div className="compare-section">
        <button className="compare-btn lightrag-compare-btn" onClick={handleOpen}>
          RAG vs LightRAG 对比
        </button>
      </div>
      {show && (
        <div className="compare-overlay" onClick={() => setShow(false)}>
          <div className="compare-modal" onClick={e => e.stopPropagation()}>
            <div className="compare-modal-header">
              <span className="compare-modal-title">RAG vs LightRAG 对比分析</span>
              <button className="compare-close" onClick={() => setShow(false)}>✕</button>
            </div>
            <div className="compare-modal-body">
              <div className="compare-col">
                <div className="compare-label rag">📄 传统 RAG 回答</div>
                <div className="compare-content markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{ragAnswer}</ReactMarkdown>
                </div>
              </div>
              <div className="compare-divider" />
              <div className="compare-col">
                <div className="compare-label llm">
                  🕸️ LightRAG 回答
                  {streaming && <span className="compare-time"> ⏱ 生成中...</span>}
                  {done && elapsed > 0 && <span className="compare-time"> ⏱ {elapsed}s</span>}
                </div>
                <div className="compare-content markdown-body">
                  {error
                    ? <div className="compare-card-error">⚠️ {error}</div>
                    : lightragContent
                      ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{lightragContent}</ReactMarkdown>
                      : streaming
                        ? <div className="typing"><span></span><span></span><span></span></div>
                        : <div style={{color: '#666'}}>等待生成...</div>
                  }
                </div>
              </div>
            </div>
            {done && !error && lightragContent && (
              <div className="compare-modal-footer">
                <AccuracyComparison ragAnswer={ragAnswer} lightragAnswer={lightragContent} question={question} />
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}

// 准确率对比组件
function AccuracyComparison({ ragAnswer, lightragAnswer, question }: { ragAnswer: string; lightragAnswer: string; question: string }) {
  const [comparison, setComparison] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleCompare = async () => {
    if (comparison) return
    setLoading(true)
    try {
      // 用后端 LLM 做对比分析
      const resp = await fetch('/api/lightrag/accuracy-compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, rag_answer: ragAnswer, lightrag_answer: lightragAnswer }),
      })
      if (resp.ok) {
        const data = await resp.json()
        setComparison(data.analysis)
      } else {
        setComparison('对比分析接口暂不可用')
      }
    } catch {
      setComparison('对比分析请求失败')
    }
    setLoading(false)
  }

  return (
    <div className="accuracy-comparison">
      {!comparison && (
        <button className="compare-btn" onClick={handleCompare} disabled={loading}>
          {loading ? '分析中...' : '📊 准确率对比分析'}
        </button>
      )}
      {comparison && (
        <div className="accuracy-result markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{comparison}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}

// 队列进度卡片（内嵌聊天区）
function QueueProgressCard({ queueStatus }: { queueStatus: QueueStatus }) {
  const { tasks, paused } = queueStatus
  const current = tasks.find(t => t.status === 'processing')
  const waiting = tasks.filter(t => t.status === 'waiting')

  const formatEta = (seconds: number) => {
    if (seconds <= 0) return ''
    if (seconds < 60) return Math.ceil(seconds) + ' 秒'
    const mins = Math.floor(seconds / 60)
    const secs = Math.ceil(seconds % 60)
    return secs > 0 ? mins + ' 分 ' + secs + ' 秒' : mins + ' 分钟'
  }

  const pct = current ? Math.min(Math.round(current.progress_percent), 100) : 0
  const eta = current ? formatEta(current.eta_seconds) : ''

  const handlePauseResume = async () => {
    try {
      if (paused) {
        await resumeIngest()
      } else {
        await pauseIngest()
      }
    } catch (e) {
      console.error('操作失败:', e)
    }
  }

  return (
    <div className="queue-card">
      {/* 当前解析文件 */}
      <div className="queue-card-header">
        <span className={`queue-card-icon ${paused ? 'paused' : ''}`}>
          {paused ? '⏸' : '🔄'}
        </span>
        <span className="queue-card-title">
          {paused ? '已暂停' : '当前解析：'} 
          <strong>{current?.filename || '准备中...'}</strong>
        </span>
        <button className="queue-pause-btn" onClick={handlePauseResume}>
          {paused ? '▶ 继续' : '⏸ 暂停'}
        </button>
      </div>

      {/* 进度条 */}
      {current && (
        <div className="queue-card-progress">
          <div className="queue-card-bar">
            <div 
              className={`queue-card-bar-fill ${paused ? 'paused' : ''}`} 
              style={{ width: pct + '%' }} 
            />
          </div>
          <div className="queue-card-meta">
            <span>{pct}% · {current.completed_pages}/{current.total_pages} 页</span>
            {eta && !paused && <span className="queue-card-eta">预计还需 {eta}</span>}
          </div>
        </div>
      )}

      {/* 剩余待解析文档 */}
      {waiting.length > 0 && (
        <div className="queue-card-waiting">
          <div className="queue-card-waiting-title">剩余待解析文档</div>
          {waiting.map((t, i) => (
            <div key={t.task_id} className="queue-card-waiting-item">
              <span className="queue-card-waiting-icon">⏳</span>
              <span className="queue-card-waiting-name">{t.filename}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


