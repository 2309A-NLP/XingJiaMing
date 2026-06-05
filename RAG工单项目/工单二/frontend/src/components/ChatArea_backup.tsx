import { useEffect, useRef, useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message, QueryAnalysis, CompareResult } from '../api'
import { queryCompare } from '../api'

interface Props {
  messages: Message[]
  loading: boolean
  onHintClick?: (text: string) => void
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

export default function ChatArea({ messages, loading, onHintClick }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

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

      {messages.map(msg => (
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
                  {msg.query_analysis && msg.query_analysis.intent !== "greeting" && (
                    <QueryAnalysisCard analysis={msg.query_analysis} />
                  )}
                  {msg.sources && msg.sources.length > 0 && msg.content.length > 30 && msg.query_analysis?.intent !== 'greeting' && (
                    <SourceTags sources={msg.sources} />
                  )}
                                    {msg.role === "assistant" && msg.responseTime !== undefined && (
                    <div className="response-time">⏱ 响应时间 {msg.responseTime}s</div>
                  )}
                  {msg.role === "assistant" && msg.query_analysis && msg.query_analysis.intent !== "greeting" && (
                    <CompareButton question={messages.find((_m, i) => messages[i+1]?.id === msg.id)?.content || ""} />
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      ))}

      <div ref={bottomRef} />
    </div>
  )
}

function QueryAnalysisCard({ analysis }: { analysis: QueryAnalysis }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="query-analysis">
      <button className="analysis-toggle" onClick={() => setExpanded(v => !v)}>
        <span>问题分析</span>
        <span className="confidence">{INTENT_LABELS[analysis.intent] || analysis.intent} · {(analysis.confidence * 100).toFixed(0)}%</span>
      </button>
      {expanded && (
        <div className="analysis-details">
          <div className="analysis-item">
            <span className="label">意图类型</span>
            <span className="value">{INTENT_LABELS[analysis.intent] || analysis.intent}</span>
          </div>
          <div className="analysis-item">
            <span className="label">意图描述</span>
            <span className="value">{analysis.intent_description}</span>
          </div>
          {analysis.disambiguated_query !== analysis.sub_queries[0] && (
            <div className="analysis-item">
              <span className="label">消歧后</span>
              <span className="value">{analysis.disambiguated_query}</span>
            </div>
          )}
          {analysis.sub_queries.length > 1 && (
            <div className="analysis-item">
              <span className="label">子问题</span>
              <ul className="sub-queries">
                {analysis.sub_queries.map((sq, i) => (
                  <li key={i}>{sq}</li>
                ))}
              </ul>
            </div>
          )}
          {analysis.keywords.length > 0 && (
            <div className="analysis-item">
              <span className="label">关键词</span>
              <div className="keywords">
                {analysis.keywords.map((kw, i) => (
                  <span key={i} className="keyword">{kw}</span>
                ))}
              </div>
            </div>
          )}
        </div>
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



