import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputBox from './components/InputBox'
import type { Chat, Message, QueryAnalysis } from './api'
import { fetchChats, fetchMessages, createChatAPI, saveMessage, updateChatTitle, deleteChatAPI, queryStream, ingest, checkHealth, translateText, selfCheck } from './api'

export default function App() {
  const [chats, setChats] = useState<Chat[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [backendOk, setBackendOk] = useState(true)
  const [backendReady, setBackendReady] = useState(true)
    const [selfCheckResult, setSelfCheckResult] = useState<any>(null)

  const activeChat = chats.find(c => c.id === activeId) || null

  // 启动时自检
  useEffect(() => {
    const doSelfCheck = async () => {
      try {
        const result = await selfCheck()
        setSelfCheckResult(result)
        if (result.failed > 0) {
          console.warn('自检发现问题:', result.results.filter(r => r.status === 'error'))
        }
      } catch (e) {
        console.error('自检失败:', e)
      }
    }
    doSelfCheck()
  }, [])

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
      } catch (e) {
        console.error('加载对话失败:', e)
      }
    }
    load()
  }, [])

  useEffect(() => {
    let stopped = false
    const check = async () => {
      try {
        const h = await checkHealth()
        if (!stopped) { setBackendOk(true); setBackendReady(h?.initialized !== false) }
      } catch {
        if (!stopped) setBackendOk(false)
      }
    }
    check()
    const id = setInterval(check, 8000)
    return () => { stopped = true; clearInterval(id) }
  }, [])

  const createChat = () => {
    const id = Date.now().toString()
    const chat: Chat = { id, title: '新对话', messages: [], createdAt: Date.now() }
    setChats(prev => [chat, ...prev])
    setActiveId(id)
    createChatAPI(id, '新对话')
  }

  // 添加消息到前端状态（同步，不等待网络）
  const addMessageToState = (chatId: string, msg: Message) => {
    setChats(prev => prev.map(c =>
      c.id === chatId
        ? { ...c, messages: [...c.messages, msg], title: c.messages.length === 0 && msg.role === 'user' ? msg.content.slice(0, 20) : c.title }
        : c
    ))
  }

  const handleSend = async (text: string) => {
    if (!backendOk) {
      const warn: Message = { id: Date.now().toString(), role: 'assistant', content: '当前后端不可用，请先检查后端是否启动。', timestamp: Date.now() }
      const cid = activeId || Date.now().toString()
      if (!activeId) {
        const chat: Chat = { id: cid, title: '新对话', messages: [warn], createdAt: Date.now() }
        setChats(prev => [chat, ...prev])
        setActiveId(cid)
        createChatAPI(cid, '新对话').catch(() => {})
      } else {
        addMessageToState(cid, warn)
      }
      saveMessage(cid, warn).catch(() => {})
      return
    }

    // 确定当前对话ID，如果没有就创建新对话
    let cid = activeId
    if (!cid) {
      cid = Date.now().toString()
      const title = text.slice(0, 20)
      const chat: Chat = { id: cid, title, messages: [], createdAt: Date.now() }
      setChats(prev => [chat, ...prev])
      setActiveId(cid)
      createChatAPI(cid, title).catch(() => {})
    }

    // 英文模式下直接发送中文，后端会翻译
    let sendText = text
    
    // 添加用户消息
    const userMsg: Message = { 
      id: Date.now().toString(), 
      role: 'user', 
      content: text, 
      timestamp: Date.now() 
    }
    addMessageToState(cid, userMsg)
    saveMessage(cid, userMsg).catch(() => {})
    updateChatTitle(cid, text.slice(0, 20)).catch(() => {})

    // 添加 AI 占位消息
    setLoading(true)
    const aiId = (Date.now() + 1).toString()
    const aiMsg: Message = { id: aiId, role: 'assistant', content: '', sources: [], timestamp: Date.now() }
    addMessageToState(cid, aiMsg)

    let aiContent = ''
    let aiSources: any[] = []
    let aiQueryAnalysis: QueryAnalysis | undefined
    const startTime = Date.now()  // 从发送前开始计时

    try {
      // 检测用户输入的语言
    const hasChinese = /[\u4e00-\u9fff]/.test(text)
    const userLang = hasChinese ? 'zh' : 'en'
    
    await queryStream(text, 5, userLang,
        (token) => {
          aiContent += token
          setChats(prev => prev.map(c => ({
            ...c,
            messages: c.messages.map(m => m.id === aiId ? { ...m, content: aiContent } : m)
          })))
        },
        (sources) => { aiSources = sources },
        (analysis) => { aiQueryAnalysis = analysis }
      )

      const elapsed = Math.round((Date.now() - startTime) / 100) / 10
      
      setChats(prev => prev.map(c => ({
        ...c,
        messages: c.messages.map(m => m.id === aiId ? { ...m, sources: aiSources, query_analysis: aiQueryAnalysis, responseTime: elapsed } : m)
      })))
      saveMessage(cid, { ...aiMsg, content: aiContent, sources: aiSources, query_analysis: aiQueryAnalysis, responseTime: elapsed }).catch(() => {})
    } catch (e: any) {
      setChats(prev => prev.map(c => ({
        ...c,
        messages: c.messages.map(m => m.id === aiId ? { ...m, content: `错误：${e.message}` } : m)
      })))
    } finally {
      setLoading(false)
    }
  }

  const handleUpload = async (file: File) => {
    let cid = activeId
    if (!cid) {
      cid = Date.now().toString()
      const chat: Chat = { id: cid, title: '新对话', messages: [], createdAt: Date.now() }
      setChats(prev => [chat, ...prev])
      setActiveId(cid)
      createChatAPI(cid, '新对话').catch(() => {})
    }
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: `[上传了 ${file.name}]`, timestamp: Date.now() }
    addMessageToState(cid, userMsg)
    saveMessage(cid, userMsg).catch(() => {})
    setParsing(true)
    const parsingMsg: Message = { id: (Date.now() + 1).toString(), role: 'assistant', content: '正在解析文档，请稍等...', timestamp: Date.now() }
    addMessageToState(cid, parsingMsg)
    saveMessage(cid, parsingMsg).catch(() => {})
    try {
      const data = await ingest(file)
      const doneMsg: Message = { id: (Date.now() + 2).toString(), role: 'assistant', content: `文档解析完成！共 ${data.pages} 页，${data.chunks} 个文本块。可以开始提问了。`, timestamp: Date.now() }
      addMessageToState(cid, doneMsg)
      saveMessage(cid, doneMsg).catch(() => {})
    } catch (e: any) {
      const errMsg: Message = { id: (Date.now() + 2).toString(), role: 'assistant', content: `解析失败：${e.message}`, timestamp: Date.now() }
      addMessageToState(cid, errMsg)
      saveMessage(cid, errMsg).catch(() => {})
    } finally {
      setParsing(false)
    }
  }

  const deleteChat = (id: string) => {
    setChats(prev => prev.filter(c => c.id !== id))
    if (activeId === id) {
      setActiveId(chats.length > 1 ? chats.find(c => c.id !== id)!.id : null)
    }
    deleteChatAPI(id).catch(() => {})
  }

  return (
    <div className="app">
      {!backendOk && (
        <div className="backend-banner error">后端未响应或已断开，请检查后端服务是否启动</div>
      )}
      {backendOk && !backendReady && (
        <div className="backend-banner info">后端正在初始化，加载模型中，请稍候...</div>
      )}
      <Sidebar
        chats={chats}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={createChat}
        onDelete={deleteChat}
      />
      <div className="main-content">
        <ChatArea
          messages={activeChat?.messages || []}
          loading={loading}
          onHintClick={handleSend}
        />
        <InputBox
          onSend={handleSend}
          onUpload={handleUpload}
disabled={loading || parsing || !backendOk || !backendReady}
        />
      </div>
    </div>
  )
}






