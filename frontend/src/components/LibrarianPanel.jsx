import { useState, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { librarianApi, projectsApi } from '../api/client'
import { Send, Loader2, BookOpen, Settings } from 'lucide-react'
import toast from 'react-hot-toast'

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      {!isUser && (
        <div className="w-6 h-6 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 mt-0.5">A</div>
      )}
      <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
        isUser
          ? 'bg-alexandria-600 text-white rounded-tr-sm'
          : 'bg-gray-50 text-gray-800 rounded-tl-sm border border-gray-100'
      }`}>
        {isUser ? (
          <p className="text-sm">{msg.content}</p>
        ) : (
          <div className="prose-alexandria"><ReactMarkdown>{msg.content}</ReactMarkdown></div>
        )}
      </div>
    </div>
  )
}

export default function LibrarianPanel({ projectId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState('')
  const [model, setModel] = useState('claude-sonnet-4-6')
  const [showModelPicker, setShowModelPicker] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  const { data: modelGroups = {} } = useQuery({
    queryKey: ['librarian-models'],
    queryFn: () => librarianApi.models().then(r => r.data),
  })

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const currentProject = projects[0]
  const activeProjectId = projectId || currentProject?.id

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streaming])

  const send = async () => {
    const text = input.trim()
    if (!text || streaming) return

    const userMsg = { role: 'user', content: text }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setStreaming('...')

    let finalText = ''
    try {
      finalText = await librarianApi.chat(
        newMessages.map(m => ({ role: m.role, content: m.content })),
        model,
        activeProjectId,
        (_, full) => setStreaming(full),
      )
      setMessages(prev => [...prev, { role: 'assistant', content: finalText }])
    } catch {
      toast.error('Alexandria is unavailable. Check your API key and model settings.')
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setStreaming('')
      inputRef.current?.focus()
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const allModels = Object.entries(modelGroups).flatMap(([provider, models]) =>
    models.map(m => ({ ...m, provider }))
  )

  const selectedLabel = allModels.find(m => m.value === model)?.label || model

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {messages.length === 0 && !streaming && (
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
              "Find anything on AI governance frameworks",
            ].map(s => (
              <button key={s} onClick={() => setInput(s)}
                className="w-full text-left text-xs text-gray-500 bg-gray-50 hover:bg-gray-100 px-3 py-2 rounded-lg transition-colors border border-gray-100">
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {(messages.length > 0 || streaming) && (
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {messages.map((msg, i) => <Message key={i} msg={msg} />)}
          {streaming && (
            <div className="flex justify-start mb-4">
              <div className="w-6 h-6 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold mr-2 flex-shrink-0 mt-0.5">A</div>
              <div className="max-w-[85%] bg-gray-50 border border-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
                {streaming === '...' ? (
                  <div className="flex items-center gap-1.5">
                    {[0, 150, 300].map(d => (
                      <span key={d} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: `${d}ms` }} />
                    ))}
                  </div>
                ) : (
                  <div className="prose-alexandria"><ReactMarkdown>{streaming}</ReactMarkdown></div>
                )}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      <div className="border-t border-gray-100 px-3 py-3 space-y-2">
        {/* Model selector */}
        <div className="relative">
          <button
            onClick={() => setShowModelPicker(v => !v)}
            className="w-full flex items-center justify-between text-xs border border-gray-200 rounded-lg px-2 py-1.5 text-gray-600 hover:border-gray-300 transition-colors"
          >
            <span className="truncate">{selectedLabel}</span>
            <Settings size={11} className="flex-shrink-0 ml-1 text-gray-400" />
          </button>

          {showModelPicker && (
            <div className="absolute bottom-full left-0 right-0 mb-1 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-50 max-h-64 overflow-y-auto">
              {Object.entries(modelGroups).map(([provider, models]) => (
                <div key={provider}>
                  <div className="px-3 py-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider bg-gray-50 sticky top-0">
                    {provider}
                  </div>
                  {models.map(m => (
                    <button
                      key={m.value}
                      onClick={() => { setModel(m.value); setShowModelPicker(false) }}
                      className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                        model === m.value ? 'bg-alexandria-50 text-alexandria-700 font-medium' : 'text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

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
            disabled={!input.trim() || !!streaming}
            className="self-end w-9 h-9 bg-alexandria-600 text-white rounded-xl flex items-center justify-center hover:bg-alexandria-700 transition-colors disabled:opacity-40"
          >
            {streaming ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          </button>
        </div>
      </div>
    </div>
  )
}
