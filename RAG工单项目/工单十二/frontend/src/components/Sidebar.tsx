import type { Chat } from '../api'

interface Props {
  chats: Chat[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onSettings?: () => void
  onEval?: () => void
}

export default function Sidebar({ chats, activeId, onSelect, onNew, onDelete, onSettings, onEval }: Props) {
  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <button className="new-chat-btn" onClick={onNew}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新建对话
        </button>
      </div>

      <div className="chat-list">
        {chats.map(chat => (
          <div
            key={chat.id}
            className={`chat-item ${chat.id === activeId ? 'active' : ''}`}
            onClick={() => onSelect(chat.id)}
          >
            <span className="chat-item-title">{chat.title}</span>
            <button
              className="chat-item-delete"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(chat.id)
              }}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
              </svg>
            </button>
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-footer-content">
          <div className="user-avatar">U</div>
          <span className="user-name">用户</span>
          <button 
            className="user-more-btn"
            onClick={onSettings}
            title="检索设置"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18">
              <circle cx="12" cy="5" r="2" />
              <circle cx="12" cy="12" r="2" />
              <circle cx="12" cy="19" r="2" />
            </svg>
          </button>
            <button
              className="user-eval-btn"
              onClick={onEval}
              title="检索评估"
            >
              📊
            </button>

        </div>
      </div>
    </div>
  )
}
