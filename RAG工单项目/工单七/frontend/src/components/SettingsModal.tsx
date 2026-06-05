import { useState, useEffect } from 'react'
import { fetchEmbeddingModels } from '../api'

interface SearchConfig {
  search_mode: 'vector' | 'bm25' | 'hybrid'
  vector_weight: number
  bm25_weight: number
  rerank_enabled: boolean
  reranker_type: 'bge' | 'llm' | 'tfidf' | 'adaptive'
  match_mode: 'standard' | 'boolean' | 'phrase' | 'fuzzy' | 'auto'
  embedding_model: string
  top_k: number
}

interface Props {
  visible: boolean
  onClose: () => void
  config: SearchConfig
  onSave: (config: SearchConfig) => void
}

const DEFAULT_CONFIG: SearchConfig = {
  search_mode: 'hybrid',
  vector_weight: 1.0,
  bm25_weight: 1.5,
  rerank_enabled: true,
  reranker_type: 'bge',
  match_mode: 'standard',
  embedding_model: '',
  top_k: 5
}

export default function SettingsModal({ visible, onClose, config, onSave }: Props) {
  const [localConfig, setLocalConfig] = useState<SearchConfig>(config)
  const [models, setModels] = useState<{name: string, path: string}[]>([])


  useEffect(() => {
    setLocalConfig(config)
  }, [config])

  // 获取可用的嵌入模型
  useEffect(() => {
    fetchEmbeddingModels()
      .then(data => setModels(data.models))
      .catch(() => {})
  }, [])

  if (!visible) return null

  const handleSave = () => {
    onSave(localConfig)
    onClose()
  }

  const handleReset = () => {
    setLocalConfig(DEFAULT_CONFIG)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>检索策略设置</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {/* 检索模式选择 */}
          <div className="setting-group">
            <label className="setting-label">检索模式</label>
            <div className="mode-buttons">
              <button
                className={`mode-btn ${localConfig.search_mode === 'vector' ? 'active' : ''}`}
                onClick={() => setLocalConfig({ ...localConfig, search_mode: 'vector' })}
              >
                向量检索
              </button>
              <button
                className={`mode-btn ${localConfig.search_mode === 'bm25' ? 'active' : ''}`}
                onClick={() => setLocalConfig({ ...localConfig, search_mode: 'bm25' })}
              >
                全文检索
              </button>
              <button
                className={`mode-btn ${localConfig.search_mode === 'hybrid' ? 'active' : ''}`}
                onClick={() => setLocalConfig({ ...localConfig, search_mode: 'hybrid' })}
              >
                混合检索
              </button>
            </div>
            <p className="setting-hint">
              {localConfig.search_mode === 'vector' && '向量检索：通过语义相似度匹配，适合理解用户意图'}
              {localConfig.search_mode === 'bm25' && '全文检索：基于关键词匹配，适合精确查找特定术语'}
              {localConfig.search_mode === 'hybrid' && '混合检索：结合向量和全文检索，提供更全面的结果'}
            </p>
          </div>

          {/* 权重调整（仅混合模式显示） */}
          {localConfig.search_mode === 'hybrid' && (
            <div className="setting-group">
              <label className="setting-label">权重调整</label>
              <div className="weight-sliders">
                <div className="slider-item">
                  <span className="slider-label">向量权重: {localConfig.vector_weight.toFixed(1)}</span>
                  <input
                    type="range"
                    min="0"
                    max="3"
                    step="0.1"
                    value={localConfig.vector_weight}
                    onChange={e => setLocalConfig({ ...localConfig, vector_weight: parseFloat(e.target.value) })}
                    className="slider"
                  />
                </div>
                <div className="slider-item">
                  <span className="slider-label">全文权重: {localConfig.bm25_weight.toFixed(1)}</span>
                  <input
                    type="range"
                    min="0"
                    max="3"
                    step="0.1"
                    value={localConfig.bm25_weight}
                    onChange={e => setLocalConfig({ ...localConfig, bm25_weight: parseFloat(e.target.value) })}
                    className="slider"
                  />
                </div>
              </div>
              <p className="setting-hint">调整两种检索方式的权重比例，数值越大权重越高</p>
            </div>
          )}

          {/* Rerank 开关 */}
          <div className="setting-group">
            <label className="setting-label">
              <input
                type="checkbox"
                checked={localConfig.rerank_enabled}
                onChange={e => setLocalConfig({ ...localConfig, rerank_enabled: e.target.checked })}
              />
              启用 Rerank 重排
            </label>
            <p className="setting-hint">Rerank 可以提高检索精度，但会增加响应时间</p>
          </div>

          {/* 重排算法选择（仅 Rerank 启用时显示） */}
          {localConfig.rerank_enabled && (
            <div className="setting-group">
              <label className="setting-label">重排算法</label>
              <div className="mode-buttons">
                <button
                  className={`mode-btn ${localConfig.reranker_type === 'bge' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, reranker_type: 'bge' })}
                >
                  BGE
                </button>
                <button
                  className={`mode-btn ${localConfig.reranker_type === 'llm' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, reranker_type: 'llm' })}
                >
                  LLM
                </button>
                <button
                  className={`mode-btn ${localConfig.reranker_type === 'tfidf' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, reranker_type: 'tfidf' })}
                >
                  TF-IDF
                </button>
                <button
                  className={`mode-btn ${localConfig.reranker_type === 'adaptive' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, reranker_type: 'adaptive' })}
                >
                  自适应
                </button>
              </div>
              <p className="setting-hint">
                {localConfig.reranker_type === 'bge' && 'BGE：基于深度学习，准确率高，需要 GPU'}
                {localConfig.reranker_type === 'llm' && 'LLM：基于大语言模型，最准确但最慢'}
                {localConfig.reranker_type === 'tfidf' && 'TF-IDF：基于关键词相似度，速度最快'}
                {localConfig.reranker_type === 'adaptive' && '自适应：根据查询长度自动选择最合适的算法'}
              </p>
            </div>
          )}

          {/* 匹配模式选择（仅全文检索或混合检索时显示） */}
          {(localConfig.search_mode === 'bm25' || localConfig.search_mode === 'hybrid') && (
            <div className="setting-group">
              <label className="setting-label">匹配模式</label>
              <div className="mode-buttons">
                <button
                  className={`mode-btn ${localConfig.match_mode === 'standard' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, match_mode: 'standard' })}
                >
                  标准匹配
                </button>
                <button
                  className={`mode-btn ${localConfig.match_mode === 'boolean' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, match_mode: 'boolean' })}
                >
                  布尔查询
                </button>
                <button
                  className={`mode-btn ${localConfig.match_mode === 'phrase' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, match_mode: 'phrase' })}
                >
                  短语匹配
                </button>
                <button
                  className={`mode-btn ${localConfig.match_mode === 'fuzzy' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, match_mode: 'fuzzy' })}
                >
                  模糊匹配
                </button>
                <button
                  className={`mode-btn ${localConfig.match_mode === 'auto' ? 'active' : ''}`}
                  onClick={() => setLocalConfig({ ...localConfig, match_mode: 'auto' })}
                >
                  自动检测
                </button>
              </div>
              <p className="setting-hint">
                {localConfig.match_mode === 'standard' && '标准匹配：基于 BM25 算法的关键词匹配'}
                {localConfig.match_mode === 'boolean' && '布尔查询：支持 AND/OR/NOT 组合条件，如 "人工智能 AND 机器学习"'}
                {localConfig.match_mode === 'phrase' && '短语匹配：引号内内容必须完整出现，如 "招股说明书"'}
                {localConfig.match_mode === 'fuzzy' && '模糊匹配：容忍拼写错误，基于编辑距离匹配相似词'}
                {localConfig.match_mode === 'auto' && '自动检测：根据查询内容自动选择最合适的匹配模式'}
              </p>
            </div>
          )}

          {/* 嵌入模型选择 */}
          {models.length > 0 && (
            <div className="setting-group">
              <label className="setting-label">嵌入模型</label>
              <div className="mode-buttons">
                {models.map(m => (
                  <button
                    key={m.name}
                    className={`mode-btn ${localConfig.embedding_model === m.name ? 'active' : ''}`}
                    onClick={() => setLocalConfig({ ...localConfig, embedding_model: m.name })}
                  >
                    {m.name}
                  </button>
                ))}
              </div>
              <p className="setting-hint">
                {models.find(m => m.name === localConfig.embedding_model)?.path || '选择不同的嵌入模型会影响向量检索的效果'}
              </p>
            </div>
          )}

          {/* Top-K 设置 */}
          <div className="setting-group">
            <label className="setting-label">返回结果数量 (Top-K): {localConfig.top_k}</label>
            <input
              type="range"
              min="1"
              max="10"
              step="1"
              value={localConfig.top_k}
              onChange={e => setLocalConfig({ ...localConfig, top_k: parseInt(e.target.value) })}
              className="slider"
            />
            <p className="setting-hint">返回最相关的 N 条结果</p>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-reset" onClick={handleReset}>恢复默认</button>
          <div className="modal-actions">
            <button className="btn-cancel" onClick={onClose}>取消</button>
            <button className="btn-save" onClick={handleSave}>保存</button>
          </div>
        </div>
      </div>
    </div>
  )
}




