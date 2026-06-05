import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputBox from './components/InputBox'
import type { Chat, Message, QueryAnalysis, IngestProgress } from './api'
import { fetchChats, fetchMessages, createChatAPI, saveMessage, updateChatTitle, deleteChatAPI, queryStream, ingest, checkHealth, selfCheck, fetchIngestProgress } from './api'

export default function App() {
  const [chats, setChats] = useState<Chat[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [ingestProgress, setIngestProgress] = useState<IngestProgress | null>(null)
  const [backendOk, setBackendOk] = useState(true)
  const [backendReady, setBackendReady] = useState(true)

  const activeChat = chats.find(c => c.id === activeId) || null

  useEffect(() => { selfCheck().catch(e => console.error('self-check failed:', e)) }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const list = await fetchChats()
        const loaded: Chat[] = []
        for (const c of list) {
          const msgs = await fetchMessages(c.id)
          loaded.push({ id: c.id, title: c.title, messages: msgs, createdAt: c.created_at })
        }
        setChats(loaded)
        if (loaded.length > 0) setActiveId(loaded[0].id)
      } catch (e) { console.error('load chats failed:', e) }
    }
    load()
  }, [])

  useEffect(() => {
    let stopped = false
    const check = async () => {
      try {
        const h = await checkHealth()
        if (!stopped) { setBackendOk(true); setBackendReady(h?.initialized !== false) }
      } catch { if (!stopped) setBackendOk(false) }
    }
    check()
    const id = setInterval(check, 8000)
    return () => { stopped = true; clearInterval(id) }
  }, [])

  // 轮询解析进度（每1.5秒），进度数据直接传给 ChatArea 渲染卡片
  useEffect(() => {
    if (!parsing) { setIngestProgress(null); return }
    const id = setInterval(async () => {
      try { const p = await fetchIngestProgress(); setIngestProgress(p) } catch {}
    }, 1500)
    return () => clearInterval(id)
  }, [parsing])

  const createChat = () => {
    const id = Date.now().toString()
    setChats(prev => [{ id, title: '新对话', messages: [], createdAt: Date.now() }, ...prev])
    setActiveId(id)
    createChatAPI(id, '新对话')
  }

  const addMessageToState = (chatId: string, msg: Message) => {
    setChats(prev => prev.map(c => c.id === chatId ? { ...c, messages: [...c.messages, msg], title: c.messages.length === 0 && msg.role === 'user' ? msg.content.slice(0, 20) : c.title } : c))
  }

  const handleSend = async (text: string) => {
    if (!backendOk) {
      const warn: Message = { id: Date.now().toString(), role: 'assistant', content: '当前后端不可用，请先检查后端是否启动。', timestamp: Date.now() }
      const cid = activeId || Date.now().toString()
      if (!activeId) { setChats(prev => [{ id: cid, title: '新对话', messages: [warn], createdAt: Date.now() }, ...prev]); setActiveId(cid); createChatAPI(cid, '新对话').catch(() => {}) } else { addMessageToState(cid, warn) }
      saveMessage(cid, warn).catch(() => {})
      return
    }
    let cid = activeId
    if (!cid) { cid = Date.now().toString(); setChats(prev => [{ id: cid!, title: text.slice(0, 20), messages: [], createdAt: Date.now() }, ...prev]); setActiveId(cid); createChatAPI(cid, text.slice(0, 20)).catch(() => {}) }
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: text, timestamp: Date.now() }
    addMessageToState(cid, userMsg); saveMessage(cid, userMsg).catch(() => {}); updateChatTitle(cid, text.slice(0, 20)).catch(() => {})
    setLoading(true)
    const aiId = (Date.now() + 1).toString()
    addMessageToState(cid, { id: aiId, role: 'assistant', content: '', sources: [], timestamp: Date.now() })
    let aiContent = '', aiSources: any[] = [], aiQueryAnalysis: QueryAnalysis | undefined
    const startTime = Date.now()
    try {
      const hasChinese = /[\u4e00-\u9fff]/.test(text)
      await queryStream(text, 5, hasChinese ? 'zh' : 'en',
        (token) => { aiContent += token; setChats(prev => prev.map(c => ({ ...c, messages: c.messages.map(m => m.id === aiId ? { ...m, content: aiContent } : m) }))) },
        (sources) => { aiSources = sources },
        (analysis) => { aiQueryAnalysis = analysis }
      )
      const elapsed = Math.round((Date.now() - startTime) / 100) / 10
      setChats(prev => prev.map(c => ({ ...c, messages: c.messages.map(m => m.id === aiId ? { ...m, sources: aiSources, query_analysis: aiQueryAnalysis, responseTime: elapsed } : m) })))
      saveMessage(cid, { id: aiId, role: 'assistant', content: aiContent, sources: aiSources, query_analysis: aiQueryAnalysis, responseTime: elapsed, timestamp: Date.now() }).catch(() => {})
    } catch (e: any) {
      setChats(prev => prev.map(c => ({ ...c, messages: c.messages.map(m => m.id === aiId ? { ...m, content: '错误: ' + e.message } : m) })))
    } finally { setLoading(false) }
  }

  const handleUpload = async (file: File) => {
    let cid = activeId
    if (!cid) { cid = Date.now().toString(); setChats(prev => [{ id: cid!, title: '新对话', messages: [], createdAt: Date.now() }, ...prev]); setActiveId(cid); createChatAPI(cid, '新对话').catch(() => {}) }
    addMessageToState(cid, { id: Date.now().toString(), role: 'user', content: '[上传了 ' + file.name + ']', timestamp: Date.now() })
    setParsing(true)
    // 添加标记消息：ChatArea 会识别这个消息并替换为进度卡片
    addMessageToState(cid, { id: (Date.now() + 1).toString(), role: 'assistant', content: '正在解析文档，请稍候...', timestamp: Date.now() })
    try {
      const data = await ingest(file)
      // 解析完成后，把进度标记消息替换为完成消息
      const doneId = (Date.now() + 2).toString()
      setChats(prev => prev.map(c => ({
        ...c,
        messages: c.messages.map(m => m.role === 'assistant' && m.content === '正在解析文档，请稍候...'
          ? { ...m, id: doneId, content: '文档解析完成！共 ' + data.pages + ' 页，' + data.chunks + ' 个文本块。可以开始提问了。' }
          : m
        )
      })))
      saveMessage(cid, { id: doneId, role: 'assistant', content: '文档解析完成！共 ' + data.pages + ' 页，' + data.chunks + ' 个文本块。可以开始提问了。', timestamp: Date.now() }).catch(() => {})
    } catch (e: any) {
      setChats(prev => prev.map(c => ({
        ...c,
        messages: c.messages.map(m => m.role === 'assistant' && m.content === '正在解析文档，请稍候...'
          ? { ...m, content: '解析失败: ' + e.message }
          : m
        )
      })))
    } finally { setParsing(false) }
  }

  const deleteChat = (id: string) => {
    setChats(prev => prev.filter(c => c.id !== id))
    if (activeId === id) setActiveId(chats.length > 1 ? chats.find(c => c.id !== id)!.id : null)
    deleteChatAPI(id).catch(() => {})
  }

  return (
    <div className="app">
      {!backendOk && <div className="backend-banner error">后端未响应或已断开，请检查后端服务是否启动</div>}
      {backendOk && !backendReady && <div className="backend-banner info">后端正在初始化，加载模型中，请稍候...</div>}
      <Sidebar chats={chats} activeId={activeId} onSelect={setActiveId} onNew={createChat} onDelete={deleteChat} />
      <div className="main-content">
        <ChatArea messages={activeChat?.messages || []} loading={loading} onHintClick={handleSend} ingestProgress={ingestProgress} />
        <InputBox onSend={handleSend} onUpload={handleUpload} disabled={loading || parsing || !backendOk || !backendReady} />
      </div>
    </div>
  )
}
