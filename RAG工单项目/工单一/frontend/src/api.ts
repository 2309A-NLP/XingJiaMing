const API_BASE = '/api'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: { chunk_id: string; section_title: string; content: string }[]
  query_analysis?: QueryAnalysis
  responseTime?: number
  timestamp: number
}

export interface Chat {
  id: string
  title: string
  messages: Message[]
  createdAt: number
}

export interface QueryAnalysis {
  intent: string
  intent_description: string
  disambiguated_query: string
  sub_queries: string[]
  keywords: string[]
  confidence: number
}

// 查询 RAG
export async function query(question: string, topK = 5) {
  const resp = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
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

export async function queryCompare(question: string, topK = 5): Promise<CompareResult> {
  const resp = await fetch(`${API_BASE}/query/compare`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
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
      query_analysis: msg.query_analysis || null,
      response_time: msg.responseTime || null,
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
  onToken: (token: string) => void,
  onSources: (sources: any[]) => void,
  onQueryAnalysis?: (analysis: QueryAnalysis) => void
) {
  const resp = await fetch(`${API_BASE}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, top_k: topK }),
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
        if (data.type === 'query_analysis' && onQueryAnalysis) {
          onQueryAnalysis(data.data)
        } else if (data.type === 'sources') {
          onSources(data.data)
        } else if (data.type === 'token') {
          onToken(data.data)
        } else if (data.type === 'done') {
          return
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




