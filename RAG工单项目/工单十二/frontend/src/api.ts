const API_BASE = '/api'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  translation?: string  // 翻译内容
  sources?: { chunk_id: string; section_title: string; content: string }[]
  responseTime?: number
  search_config?: { search_mode: string; reranker_type: string; rerank_enabled: boolean; match_mode: string; embedding_model: string }
  timestamp: number
}

export interface Chat {
  id: string
  title: string
  messages: Message[]
  createdAt: number
}


// 查询 RAG

// 检索策略配置
export interface SearchConfig {
  search_mode: 'vector' | 'bm25' | 'hybrid'
  vector_weight: number
  bm25_weight: number
  rerank_enabled: boolean
  reranker_type: 'bge' | 'llm' | 'tfidf' | 'adaptive'
  match_mode: 'standard' | 'boolean' | 'phrase' | 'fuzzy' | 'auto'
  embedding_model: string
  top_k: number
}

export const DEFAULT_SEARCH_CONFIG: SearchConfig = {
  search_mode: 'hybrid',
  vector_weight: 1.0,
  bm25_weight: 1.5,
  rerank_enabled: true,
  reranker_type: 'bge',
  match_mode: 'standard',
  embedding_model: '',
  top_k: 5
}

export async function query(question: string, topK = 5, language = "zh") {
  const resp = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK, language }),
  })
  if (!resp.ok) throw new Error(`请求失败: ${resp.status}`)
  return resp.json()
}


export interface CompareResult {
  rag_answer: string
  rag_sources: { chunk_id: string; section_title: string; content: string }[]
  llm_answer: string
  response_time_ms: number
}

export async function queryCompare(question: string, topK = 5, language = "zh"): Promise<CompareResult> {
  const resp = await fetch(`${API_BASE}/query/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK, language }),
  })
  if (!resp.ok) throw new Error(`请求失败: ${resp.status}`)
  return resp.json()
}
// 分析 Query
export async function analyzeQuery(question: string) {
  const resp = await fetch(`${API_BASE}/query/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!resp.ok) throw new Error(`分析失败: ${resp.status}`)
  return resp.json()
}

// 上传文档
export async function ingest(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await fetch(`${API_BASE}/ingest`, {
    method: 'POST',
    body: formData,
  })
  if (!resp.ok) throw new Error(`上传失败: ${resp.status}`)
  return resp.json()
}

// 获取所有对话列表
export async function fetchChats() {
  const resp = await fetch(`${API_BASE}/chats`)
  if (!resp.ok) throw new Error(`获取对话列表失败`)
  return resp.json()
}

// 创建新对话
export async function createChatAPI(chatId: string, title: string) {
  await fetch(`${API_BASE}/chats`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, title }),
  })
}

// 获取某个对话的消息
export async function fetchMessages(chatId: string) {
  const resp = await fetch(`${API_BASE}/chats/${chatId}/messages`)
  if (!resp.ok) throw new Error(`获取消息失败`)
  return resp.json()
}

// 保存一条消息到后端
export async function saveMessage(chatId: string, msg: Message) {
  await fetch(`${API_BASE}/chats/${chatId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      msg_id: msg.id,
      role: msg.role,
      content: msg.content,
      sources: msg.sources || [],
      response_time: msg.responseTime || null,
      search_config: msg.search_config || null,
      timestamp: msg.timestamp,
    }),
  })
}

// 更新对话标题
export async function updateChatTitle(chatId: string, title: string) {
  await fetch(`${API_BASE}/chats/${chatId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, title }),
  })
}

// 删除对话
export async function deleteChatAPI(chatId: string) {
  await fetch(`${API_BASE}/chats/${chatId}`, {
    method: 'DELETE',
  })
}

// 流式查询 RAG
export async function queryStream(
  question: string,
  topK: number,
  language: string = "zh",
  chatId: string | null = null,
  onToken: (token: string) => void,
  onSources: (sources: any[]) => void,
  searchConfig?: SearchConfig,
  onConfig?: (config: any) => void,
  onQueryAnalysis?: (analysis: any) => void,
  onLightRAGResult?: (result: { answer: string; error?: string }) => void,
  onDone?: () => void,
) {
  const config = searchConfig || DEFAULT_SEARCH_CONFIG
  const resp = await fetch(`${API_BASE}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ 
      question, 
      top_k: config.top_k || topK, 
      language, 
      chat_id: chatId,
      search_mode: config.search_mode,
      vector_weight: config.vector_weight,
      bm25_weight: config.bm25_weight,
      rerank_enabled: config.rerank_enabled,
      reranker_type: config.reranker_type,
      match_mode: config.match_mode,
      embedding_model: config.embedding_model
    }),
  })
  if (!resp.ok) throw new Error(`请求失败: ${resp.status}`)

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === "config" && onConfig) {
          onConfig(data.data)
        } else if (data.type === 'query_analysis' && onQueryAnalysis) {
          onQueryAnalysis(data.data)
        } else if (data.type === 'sources') {
          onSources(data.data)
        } else if (data.type === 'token') {
          onToken(data.data)
        } else if (data.type === 'done') {
          onDone?.()
        } else if (data.type === 'lightrag_result') {
          onLightRAGResult?.(data.data)
        }
      } catch (e) {
        // 忽略解析错误
      }
    }
  }
}

// 健康检查
export async function checkHealth() {
  const resp = await fetch(`${API_BASE}/health`, { cache: 'no-store' })
  if (!resp.ok) throw new Error(`健康检查失败: ${resp.status}`)
  return resp.json()
}

// 获取可用的嵌入模型
export async function fetchEmbeddingModels(): Promise<{models: {name: string, path: string}[], current: string}> {
  const resp = await fetch(`${API_BASE}/embedding/models`)
  if (!resp.ok) throw new Error('获取模型列表失败')
  return resp.json()
}

// 运行 RAG 评估
export async function runEvaluation(config?: {top_k?: number, search_mode?: string}): Promise<any> {
  const resp = await fetch(`${API_BASE}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config || {}),
  })
  if (!resp.ok) throw new Error('评估失败')
  return resp.json()
}





// 翻译文本
export async function translateText(text: string, sourceLang: string = 'zh', targetLang: string = 'en'): Promise<string> {
  const resp = await fetch(`${API_BASE}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang }),
  })
  if (!resp.ok) throw new Error(`翻译失败: ${resp.status}`)
  const data = await resp.json()
  return data.translated
}

// Bug 自检系统
export interface BugCheckResult {
  bug_id: string
  description: string
  status: 'ok' | 'error'
  message: string
}

export interface SelfCheckResponse {
  total: number
  passed: number
  failed: number
  results: BugCheckResult[]
}

// 启动时自检
export async function selfCheck(): Promise<SelfCheckResponse> {
  const resp = await fetch(`${API_BASE}/self-check`)
  if (!resp.ok) throw new Error('自检失败')
  return resp.json()
}

// 报告新 bug
export async function reportBug(bugData: {
  type: string
  description: string
  check_method: string
  severity: string
}): Promise<{ status: string; bug_id: string }> {
  const resp = await fetch(`${API_BASE}/bug-report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...bugData, created_at: new Date().toISOString().split('T')[0] }),
  })
  if (!resp.ok) throw new Error('报告失败')
  return resp.json()
}

// LightRAG 对比查询
export interface LightRAGCompareResult {
  question: string
  lightrag: { answer: string; error: string | null; time_ms?: number }
  traditional_rag: { answer: string; error: string | null; time_ms?: number; sources?: any[] }
  total_time_ms?: number
}

export async function queryLightRAGCompare(question: string): Promise<LightRAGCompareResult> {
  const resp = await fetch(`${API_BASE}/lightrag/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!resp.ok) throw new Error(`对比查询失败: ${resp.status}`)
  return resp.json()
}

// LightRAG 流式查询（SSE）
export async function queryLightRAGStream(
  question: string,
  mode: string = 'hybrid',
  onToken: (token: string) => void,
  onDone?: () => void,
  onError?: (error: string) => void,
) {
  const resp = await fetch(`${API_BASE}/lightrag/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, mode }),
  })
  if (!resp.ok) throw new Error(`LightRAG流式查询失败: ${resp.status}`)

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'token') {
          onToken(data.data)
        } else if (data.type === 'done') {
          onDone?.()
          return
        } else if (data.type === 'error') {
          onError?.(data.data)
          return
        }
      } catch (e) {
        // 忽略解析错误
      }
    }
  }
  onDone?.()
}

// 混合回答融合流式查询
export async function queryMergeStream(
  question: string,
  ragAnswer: string,
  lightragAnswer: string,
  onToken: (token: string) => void,
  onDone?: () => void,
) {
  const resp = await fetch(`${API_BASE}/lightrag/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, rag_answer: ragAnswer, lightrag_answer: lightragAnswer }),
  })
  if (!resp.ok) throw new Error(`融合查询失败: ${resp.status}`)

  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'token') {
          onToken(data.data)
        } else if (data.type === 'done') {
          onDone?.()
          return
        }
      } catch (e) {
        // 忽略解析错误
      }
    }
  }
  onDone?.()
}

// LightRAG 状态
export async function fetchLightRAGStatus(): Promise<{ status: string; working_dir?: string; has_knowledge_graph?: boolean; error?: string }> {
  const resp = await fetch(`${API_BASE}/lightrag/status`)
  if (!resp.ok) throw new Error('获取LightRAG状态失败')
  return resp.json()
}

// 文档解析进度
export interface IngestProgress {
  active: boolean
  filename: string
  total_pages: number
  completed_pages: number
  current_batch: number
  total_batches: number
  stage: string
  elapsed_seconds: number
  eta_seconds: number
  progress_percent: number
}

export async function fetchIngestProgress(): Promise<IngestProgress> {
  const resp = await fetch(`${API_BASE}/ingest/progress`, { cache: 'no-store' })
  if (!resp.ok) throw new Error('获取进度失败')
  return resp.json()
}


// 文档任务状态
export interface DocumentTask {
  task_id: string
  filename: string
  status: 'waiting' | 'processing' | 'completed' | 'failed'
  total_pages: number
  completed_pages: number
  current_batch: number
  total_batches: number
  stage: string
  error: string | null
  progress_percent: number
  eta_seconds: number
  elapsed_seconds: number
}

// 队列状态
export interface QueueStatus {
  processing: boolean
  paused: boolean
  current: DocumentTask | null
  queue_length: number
  tasks: DocumentTask[]
}

// 上传多个文件
export async function ingestMultiple(files: File[]): Promise<any> {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))
  const resp = await fetch(`${API_BASE}/ingest`, {
    method: 'POST',
    body: formData,
  })
  if (!resp.ok) throw new Error(`上传失败: ${resp.status}`)
  return resp.json()
}

// 获取队列状态
export async function fetchQueueStatus(): Promise<QueueStatus> {
  const resp = await fetch(`${API_BASE}/ingest/queue`, { cache: 'no-store' })
  if (!resp.ok) throw new Error('获取队列状态失败')
  return resp.json()
}

// 暂停解析
export async function pauseIngest(): Promise<void> {
  const resp = await fetch(`${API_BASE}/ingest/pause`, { method: 'POST' })
  if (!resp.ok) throw new Error('暂停失败')
}

// 继续解析
export async function resumeIngest(): Promise<void> {
  const resp = await fetch(`${API_BASE}/ingest/resume`, { method: 'POST' })
  if (!resp.ok) throw new Error('继续失败')
}

// SSE 订阅进度
export function subscribeProgress(onUpdate: (status: QueueStatus) => void): () => void {
  const eventSource = new EventSource(`${API_BASE}/ingest/stream`)
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      onUpdate(data)
    } catch (e) {
      // 忽略解析错误
    }
  }

  eventSource.onerror = () => {
    // 重连
    setTimeout(() => {
      eventSource.close()
    }, 5000)
  }

  return () => eventSource.close()
}









