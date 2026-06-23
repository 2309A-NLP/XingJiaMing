import { useState } from 'react'
import { queryLightRAGCompare, type LightRAGCompareResult } from '../api'

interface Props {
  visible: boolean
  onClose: () => void
}

const SAMPLE_QUESTIONS = [
  '武汉力源信息技术股份有限公司本次发行股数是多少？',
  '武汉兴图新科电子股份有限公司参与制定了哪个技术标准？',
  '武汉力源信息技术股份有限公司本次募集资金拟投资哪些项目？',
  '武汉兴图新科电子股份有限公司注册资本是多少？',
  '与武汉力源信息技术股份有限公司存在控制关系的关联方是谁？',
]

export default function CompareModal({ visible, onClose }: Props) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<LightRAGCompareResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!visible) return null

  const handleCompare = async (q?: string) => {
    const query = q || question
    if (!query.trim()) return
    setQuestion(query)
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await queryLightRAGCompare(query)
      setResult(res)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content compare-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>🔍 RAG vs LightRAG 对比</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        <div className="compare-input">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleCompare()}
            placeholder="输入问题进行对比查询..."
            disabled={loading}
          />
          <button onClick={() => handleCompare()} disabled={loading || !question.trim()}>
            {loading ? '查询中...' : '对比查询'}
          </button>
        </div>

        <div className="sample-questions">
          <span className="sample-label">示例问题：</span>
          {SAMPLE_QUESTIONS.map((q, i) => (
            <button key={i} className="sample-btn" onClick={() => handleCompare(q)} disabled={loading}>
              {q.length > 20 ? q.slice(0, 20) + '...' : q}
            </button>
          ))}
        </div>

        {error && <div className="compare-error">❌ {error}</div>}

        {result && (
          <div className="compare-results">
            <div className="compare-question">📋 {result.question}</div>
            <div className="compare-columns">
              <div className="compare-card rag-card">
                <div className="compare-card-header">
                  <span className="compare-tag rag-tag">传统 RAG</span>
                  <span className="compare-method">向量 + BM25 + Rerank</span>
                </div>
                <div className="compare-card-body">
                  {result.traditional_rag.error
                    ? <div className="compare-card-error">⚠️ {result.traditional_rag.error}</div>
                    : <div className="compare-answer">{result.traditional_rag.answer}</div>
                  }
                </div>
              </div>
              <div className="compare-card lightrag-card">
                <div className="compare-card-header">
                  <span className="compare-tag lightrag-tag">LightRAG</span>
                  <span className="compare-method">知识图谱 + 混合检索</span>
                </div>
                <div className="compare-card-body">
                  {result.lightrag.error
                    ? <div className="compare-card-error">⚠️ {result.lightrag.error}</div>
                    : <div className="compare-answer">{result.lightrag.answer}</div>
                  }
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
