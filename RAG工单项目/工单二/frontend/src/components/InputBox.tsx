import { useState, useRef } from 'react'

interface Props {
  onSend: (text: string) => void
  onUpload: (file: File) => void
  disabled?: boolean
}

export default function InputBox({ onSend, onUpload, disabled }: Props) {
  const [text, setText] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const handleSend = () => {
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      onUpload(file)
      e.target.value = ''
    }
  }

  return (
    <div className="input-wrapper">
      <div className="input-box">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />
        <button
          className="upload-btn"
          onClick={() => fileRef.current?.click()}
          disabled={disabled}
          title="上传PDF文档"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
          </svg>
        </button>
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入你的问题..."
          disabled={disabled}
          rows={1}
        />

        <button
          className="send-btn"
          onClick={handleSend}
          disabled={!text.trim() || disabled}
          title="发送"
        >
          <svg className="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  )
}