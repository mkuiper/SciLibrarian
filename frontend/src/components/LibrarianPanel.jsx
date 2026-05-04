import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { librarianApi } from '../api/client'
import { Send, Loader2, BookOpen } from 'lucide-react'
import toast from 'react-hot-toast'

const MODELS = [
  { value: 'claude-sonnet-4-6', label: 'Sonnet 4.6' },
  { value: 'claude-opus-4-7', label: 'Opus 4.7' },
  { value: 'claude-haiku-4-5-20251001', label: 'Haiku 4.5' },
]

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 mt-0.5">
          A
        </div>
      )}
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? 'bg-alexandria-600 text-white rounded-tr-sm'
            : 'bg-gray-50 text-gray-800 rounded-tl-sm border border-gray-100'
        }`}
      >
        {isUser ? (
          <p className="text-sm">{msg.content}</p>
        ) : (
          <div className="prose-alexandria">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}

export default function LibrarianPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState('')
  const [model, setModel] = useState('claude-sonnet-4-6')
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const send = async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg = { role: 'user', content: text }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setLoading('...')

    const apiMessages = newMessages.map(m => ({
      role: m.role,
      content: m.content,
    }))

    try {
      await librarianApi.chat(apiMessages, model, (_, full) => {
        setLoading(full)
      })
      const finalText = loading
      setMessages(prev => [...prev, { role: 'assistant', content: finalText || loading }])
    } catch (err) {
      toast.error('Alexandria is unavailable. Check your API key.')
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading('')
      inputRef.current?.focus()
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {messages.length === 0 && !loading && (
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <div className="w-12 h-12 rounded-full bg-alexandria-50 flex items-center justify-center mb-3">
            <BookOpen size={22} className="text-alexandria-600" />
          </div>
          <p className="text-gray-700 font-medium text-sm mb-1">Ask Alexandria</p>
          <p className="text-gray-400 text-xs leading-relaxed">
            Search for papers, get summaries, explore connections, or ask what's missing from your library.
          </p>
          <div className="mt-4 space-y-2 w-full">
            {[
              "What papers do we have on AI alignment?",
              "Summarise our coverage of model evaluation",
              "What are the key gaps in our library?",
            ].map(s => (
              <button
                key={s}
                onClick={() => setInput(s)}
                className="w-full text-left text-xs text-gray-500 bg-gray-50 hover:bg-gray-100 px-3 py-2 rounded-lg transition-colors border border-gray-100"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {(messages.length > 0 || loading) && (
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {messages.map((msg, i) => <Message key={i} msg={msg} />)}
          {loading && (
            <div className="flex justify-start mb-4">
              <div className="w-6 h-6 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 mt-0.5">A</div>
              <div className="max-w-[85%] bg-gray-50 border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
                {loading === '...' ? (
                  <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                ) : (
                  <div className="prose-alexandria">
                    <ReactMarkdown>{loading}</ReactMarkdown>
                  </div>
                )}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      <div className="border-t border-gray-100 px-3 py-3 space-y-2">
        <select
          value={model}
          onChange={e => setModel(e.target.value)}
          className="w-full text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 focus:outline-none focus:ring-1 focus:ring-alexandria-400"
        >
          {MODELS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask Alexandria anything..."
            rows={2}
            className="flex-1 text-sm border border-gray-200 rounded-xl px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-alexandria-400 focus:border-transparent"
          />
          <button
            onClick={send}
            disabled={!input.trim() || !!loading}
            className="self-end w-9 h-9 bg-alexandria-600 text-white rounded-xl flex items-center justify-center hover:bg-alexandria-700 transition-colors disabled:opacity-40"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </div>
      </div>
    </div>
  )
}
