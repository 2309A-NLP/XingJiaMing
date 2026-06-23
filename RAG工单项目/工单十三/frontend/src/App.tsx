import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import ChatArea from './components/ChatArea'
import InputBox from './components/InputBox'

import SettingsModal from './components/SettingsModal'
import EvalModal from './components/EvalModal'
import type { Chat, DoneMetrics, Message, QueueStatus, SearchConfig } from './api'
import { DEFAULT_SEARCH_CONFIG, fetchChats, fetchMessages, createChatAPI, saveMessage, updateChatTitle, deleteChatAPI, queryStream, ingestMultiple, checkHealth, selfCheck, subscribeProgress } from './api'

// 从 localStorage 加载配置
function loadSearchConfig(): SearchConfig {
  try {
    const saved = localStorage.getItem('searchConfig')
    if (saved) return { ...DEFAULT_SEARCH_CONFIG, ...JSON.parse(saved) }
  } catch {}
  return DEFAULT_SEARCH_CONFIG
}

export default function App() {
  const [chats, setChats] = useState<Chat[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null)
  const [backendOk, setBackendOk] = useState(true)
  const [backendReady, setBackendReady] = useState(true)
  const [showSettings, setShowSettings] = useState(false)
  const [showEval, setShowEval] = useState(false)

  const [searchConfig, setSearchConfig] = useState<SearchConfig>(loadSearchConfig)

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

  // SSE 订阅队列进度（实时更新）
  useEffect(() => {
    if (!parsing) {
      setQueueStatus(null)
      return
    }

    const unsubscribe = subscribeProgress((status) => {
      setQueueStatus(status)
      
      // 检查是否所有任务都完成了
      const allDone = status.tasks.every(t => 
        t.status === 'completed' || t.status === 'failed'
      )
      if (allDone && status.tasks.length > 0) {
        setParsing(false)
      }
    })

    return () => unsubscribe()
  }, [parsing])

  // 保存配置到 localStorage
  const handleSaveConfig = (config: SearchConfig) => {
    setSearchConfig(config)
    localStorage.setItem('searchConfig', JSON.stringify(config))
  }

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
    let aiContent = '', aiSources: any[] = [], aiQueryAnalysis: any = undefined
    let aiMetrics: DoneMetrics | null = null
    const startTime = Date.now()
    try {
      const hasChinese = /[\u4e00-\u9fff]/.test(text)
      let aiSearchConfig: any = null
      await queryStream(text, searchConfig.top_k, hasChinese ? 'zh' : 'en', cid,
        (token) => { aiContent += token; setChats(prev => prev.map(c => ({ ...c, messages: c.messages.map(m => m.id === aiId ? { ...m, content: aiContent } : m) }))) },
        (sources) => { aiSources = sources },
        searchConfig,
        (config) => { aiSearchConfig = config },
        (analysis) => { aiQueryAnalysis = analysis },
        (metrics) => {
          aiMetrics = metrics
          const elapsed = Math.round(metrics.total_time_ms / 100) / 10
          setChats(prev => prev.map(c => ({ ...c, messages: c.messages.map(m => m.id === aiId ? { ...m, sources: aiSources, query_analysis: aiQueryAnalysis, responseTime: elapsed, search_config: aiSearchConfig, metrics } : m) })))
          saveMessage(cid, { id: aiId, role: 'assistant', content: aiContent, sources: aiSources, query_analysis: aiQueryAnalysis, responseTime: elapsed, search_config: aiSearchConfig, metrics, timestamp: Date.now() }).catch(() => {})
          setLoading(false)
        }
      )
      if (!aiMetrics) {
        const fallbackElapsed = Math.round((Date.now() - startTime) / 100) / 10
        setChats(prev => prev.map(c => ({ ...c, messages: c.messages.map(m => m.id === aiId ? { ...m, sources: aiSources, query_analysis: aiQueryAnalysis, responseTime: fallbackElapsed, search_config: aiSearchConfig } : m) })))
      }
    } catch (e: any) {
      setChats(prev => prev.map(c => ({ ...c, messages: c.messages.map(m => m.id === aiId ? { ...m, content: '错误: ' + e.message } : m) })))
    } finally { setLoading(false) }
  }

  const handleUpload = async (files: File[]) => {
    if (files.length === 0) return

    let cid = activeId
    if (!cid) { 
      cid = Date.now().toString()
      setChats(prev => [{ id: cid!, title: '新对话', messages: [], createdAt: Date.now() }, ...prev])
      setActiveId(cid)
      createChatAPI(cid, '新对话').catch(() => {})
    }

    // 用户消息：显示已上传的文档列表
    const totalLen = files.reduce((sum, f) => sum + f.name.length, 0)
    const displayNames = totalLen > 40 
      ? files.slice(0, 2).map(f => f.name).join('、') + '…'
      : files.map(f => f.name).join('、')
    
    addMessageToState(cid, { 
      id: Date.now().toString(), 
      role: 'user', 
      content: `📄 已上传 ${files.length} 个文档\n${displayNames}`, 
      timestamp: Date.now() 
    })

    setParsing(true)

    try {
      await ingestMultiple(files)
    } catch (e: any) {
      addMessageToState(cid, { 
        id: (Date.now() + 1).toString(), 
        role: 'assistant', 
        content: '上传失败: ' + e.message, 
        timestamp: Date.now() 
      })
      setParsing(false)
    }
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
      <Sidebar 
        chats={chats} 
        activeId={activeId} 
        onSelect={setActiveId} 
        onNew={createChat} 
        onDelete={deleteChat}
        onSettings={() => setShowSettings(true)}
        onEval={() => setShowEval(true)}
      />
      <div className="main-content">
        <ChatArea messages={activeChat?.messages || []} loading={loading} onHintClick={handleSend} ingestProgress={null} queueStatus={parsing ? queueStatus : null} />
        <InputBox onSend={handleSend} onUpload={handleUpload} disabled={loading || !backendOk || !backendReady} />
      </div>
      <EvalModal
        visible={showEval}
        onClose={() => setShowEval(false)}
      />


      <SettingsModal
        visible={showSettings}
        onClose={() => setShowSettings(false)}
        config={searchConfig}
        onSave={handleSaveConfig}
      />
    </div>
  )
}
