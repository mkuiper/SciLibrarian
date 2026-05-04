import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectsApi, librarianApi } from '../api/client'
import { Settings as SettingsIcon, Save, Loader2, RotateCcw, ChevronDown } from 'lucide-react'
import toast from 'react-hot-toast'

const DEFAULT_PROMPT = `You are Alexandria, an expert AI research librarian.
Your role is to help researchers find, understand, and synthesise information from the reference library.

When answering questions:
- Search the library for relevant references before answering
- Cite specific papers/documents by their exact titles
- Synthesise information across multiple sources when helpful
- Flag gaps where the library lacks coverage on a topic
- Be precise about what comes from the library vs your training knowledge
- Keep responses focused and actionable for researchers`

function ModelSelect({ label, value, onChange, models }) {
  const [open, setOpen] = useState(false)
  const allModels = Object.entries(models).flatMap(([provider, ms]) =>
    ms.map(m => ({ ...m, provider }))
  )
  const selected = allModels.find(m => m.value === value)

  return (
    <div>
      <label className="label">{label}</label>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          className="input flex items-center justify-between text-left"
        >
          <span>{selected?.label || value || 'Select model'}</span>
          <ChevronDown size={14} className="text-gray-400 flex-shrink-0" />
        </button>
        {open && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg z-50 max-h-72 overflow-y-auto">
            {Object.entries(models).map(([provider, ms]) => (
              <div key={provider}>
                <div className="px-3 py-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider bg-gray-50 sticky top-0">
                  {provider}
                </div>
                {ms.map(m => (
                  <button
                    key={m.value}
                    type="button"
                    onClick={() => { onChange(m.value); setOpen(false) }}
                    className={`w-full text-left px-3 py-2.5 text-sm transition-colors ${
                      value === m.value
                        ? 'bg-alexandria-50 text-alexandria-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-50'
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
    </div>
  )
}

export default function Settings() {
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })
  const { data: modelGroups = {} } = useQuery({
    queryKey: ['librarian-models'],
    queryFn: () => librarianApi.models().then(r => r.data),
  })

  const project = projects[0]
  const projectSettings = project?.settings || {}

  const [form, setForm] = useState({
    librarian_model: 'claude-sonnet-4-6',
    ingestion_model: 'claude-sonnet-4-6',
    librarian_system_prompt: DEFAULT_PROMPT,
    ollama_base_url: 'http://localhost:11434',
  })

  useEffect(() => {
    if (projectSettings) {
      setForm(f => ({
        ...f,
        librarian_model: projectSettings.librarian_model || f.librarian_model,
        ingestion_model: projectSettings.ingestion_model || f.ingestion_model,
        librarian_system_prompt: projectSettings.librarian_system_prompt || f.librarian_system_prompt,
        ollama_base_url: projectSettings.ollama_base_url || f.ollama_base_url,
      }))
    }
  }, [project?.id])

  const save = async (e) => {
    e.preventDefault()
    if (!project) { toast.error('No project selected'); return }
    setSaving(true)
    try {
      await projectsApi.updateSettings(project.id, form)
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Settings saved')
    } catch {
      toast.error('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const resetPrompt = () => setForm(f => ({ ...f, librarian_system_prompt: DEFAULT_PROMPT }))

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <div className="flex items-center gap-3 mb-8">
        <div className="w-10 h-10 rounded-xl bg-gray-100 flex items-center justify-center">
          <SettingsIcon size={18} className="text-gray-600" />
        </div>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Project Settings</h1>
          {project && <p className="text-sm text-gray-500">{project.name}</p>}
        </div>
      </div>

      {!project ? (
        <div className="card p-6 text-center text-gray-400">
          Create a project first to configure settings.
        </div>
      ) : (
        <form onSubmit={save} className="space-y-8">
          {/* AI Models */}
          <div className="card p-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">AI Models</h2>
            <p className="text-xs text-gray-400 mb-5">
              Choose which model powers each function. Different models have different costs and capabilities.
              Ollama models run locally — no API key needed.
            </p>
            <div className="space-y-4">
              <ModelSelect
                label="Librarian (chat with Alexandria)"
                value={form.librarian_model}
                onChange={v => setForm(f => ({ ...f, librarian_model: v }))}
                models={modelGroups}
              />
              <ModelSelect
                label="Ingestion (PDF/URL metadata extraction)"
                value={form.ingestion_model}
                onChange={v => setForm(f => ({ ...f, ingestion_model: v }))}
                models={modelGroups}
              />
            </div>

            <div className="mt-5 p-4 bg-blue-50 rounded-xl border border-blue-100">
              <p className="text-xs font-semibold text-blue-700 mb-1">Using Ollama (local models)</p>
              <p className="text-xs text-blue-600 mb-3">
                Install Ollama, run <code className="bg-blue-100 px-1 rounded">ollama pull llama3.2</code>, then select an Ollama model above.
              </p>
              <div>
                <label className="label text-blue-700">Ollama base URL</label>
                <input
                  className="input text-xs"
                  value={form.ollama_base_url}
                  onChange={e => setForm(f => ({ ...f, ollama_base_url: e.target.value }))}
                  placeholder="http://localhost:11434"
                />
              </div>
            </div>
          </div>

          {/* System prompt */}
          <div className="card p-6">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-sm font-semibold text-gray-700">Alexandria's Instructions</h2>
              <button type="button" onClick={resetPrompt} className="btn-ghost text-xs gap-1">
                <RotateCcw size={11} />
                Reset to default
              </button>
            </div>
            <p className="text-xs text-gray-400 mb-4">
              Customise how Alexandria behaves — her focus areas, tone, citation style, what to prioritise.
              This system prompt is sent with every chat message.
            </p>
            <textarea
              className="input font-mono text-xs leading-relaxed"
              rows={12}
              value={form.librarian_system_prompt}
              onChange={e => setForm(f => ({ ...f, librarian_system_prompt: e.target.value }))}
            />
            <p className="text-xs text-gray-400 mt-2">
              Tip: mention specific focus areas, preferred citation styles, or how to handle gaps.
              E.g. "Focus particularly on Australian government policy and regulatory frameworks."
            </p>
          </div>

          {/* API keys info */}
          <div className="card p-6">
            <h2 className="text-sm font-semibold text-gray-700 mb-1">API Keys</h2>
            <p className="text-xs text-gray-400 mb-4">
              API keys are configured via environment variables in <code className="bg-gray-100 px-1 rounded">.env</code> — not stored in the database.
              This keeps them secure and out of the web interface.
            </p>
            <div className="space-y-2 text-xs">
              {[
                ['ANTHROPIC_API_KEY', 'Claude (Sonnet, Opus, Haiku)', 'console.anthropic.com'],
                ['OPENAI_API_KEY', 'GPT-4o, GPT-4-turbo', 'platform.openai.com'],
                ['GEMINI_API_KEY', 'Gemini 1.5 Pro/Flash', 'aistudio.google.com'],
                ['SEMANTIC_SCHOLAR_API_KEY', 'Semantic Scholar (optional, increases rate limit)', 'semanticscholar.org/product/api'],
                ['OPENALEX_EMAIL', 'OpenAlex (optional, polite pool)', 'docs.openalex.org'],
              ].map(([key, desc, link]) => (
                <div key={key} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
                  <code className="bg-gray-100 px-1.5 py-0.5 rounded text-gray-600 flex-shrink-0">{key}</code>
                  <span className="text-gray-500">{desc}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <button type="submit" disabled={saving} className="btn-primary">
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              Save settings
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
