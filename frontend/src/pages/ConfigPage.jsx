import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { configApi, librarianApi, projectsApi } from '../api/client'
import { CheckCircle, XCircle, Loader2, RefreshCw, Server, Cpu, Mail, Search, Save, Plus, X } from 'lucide-react'
import toast from 'react-hot-toast'

const DEFAULT_PROMPT = `You are Alexandria, an expert AI research librarian.
Your role is to help researchers find, understand, and synthesise information from the reference library.

When answering questions:
- Search the library for relevant references before answering
- Cite specific papers/documents by their exact titles
- Synthesise information across multiple sources when helpful
- Flag gaps where the library lacks coverage on a topic
- Keep responses focused and actionable for researchers`

function StatusDot({ ok }) {
  return ok
    ? <CheckCircle size={15} className="text-emerald-500 flex-shrink-0" />
    : <XCircle size={15} className="text-red-400 flex-shrink-0" />
}

function Section({ title, children }) {
  return (
    <div className="card p-6">
      <h2 className="text-sm font-semibold text-gray-800 mb-4">{title}</h2>
      {children}
    </div>
  )
}

export default function ConfigPage() {
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)

  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery({
    queryKey: ['config-status'],
    queryFn: () => configApi.status().then(r => r.data),
    refetchInterval: false,
  })

  const { data: ollamaInfo, refetch: refetchOllama } = useQuery({
    queryKey: ['ollama-models'],
    queryFn: () => configApi.ollamaModels().then(r => r.data),
    refetchInterval: false,
  })

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const project = projects[0]
  const ps = project?.settings || {}

  const [form, setForm] = useState({
    librarian_model: ps.librarian_model || 'claude-sonnet-4-6',
    ingestion_model: ps.ingestion_model || 'claude-sonnet-4-6',
    digest_model: ps.digest_model || 'claude-sonnet-4-6',
    librarian_system_prompt: ps.librarian_system_prompt || DEFAULT_PROMPT,
    digest_recipients: (ps.digest_recipients || []).join('\n'),
  })

  // Sync form when project loads
  useState(() => {
    if (ps.librarian_model) setForm(f => ({ ...f, ...ps, digest_recipients: (ps.digest_recipients || []).join('\n') }))
  }, [project?.id])

  const save = async () => {
    if (!project) { toast.error('No project found'); return }
    setSaving(true)
    try {
      const recipients = form.digest_recipients.split('\n').map(s => s.trim()).filter(Boolean)
      await projectsApi.updateSettings(project.id, {
        librarian_model: form.librarian_model,
        ingestion_model: form.ingestion_model,
        digest_model: form.digest_model,
        librarian_system_prompt: form.librarian_system_prompt,
        digest_recipients: recipients,
      })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Configuration saved')
    } catch {
      toast.error('Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const allOllamaModels = ollamaInfo?.models || []

  const MODEL_GROUPS = [
    { label: 'Anthropic Claude', models: [
      { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
      { value: 'claude-opus-4-7', label: 'Claude Opus 4.7' },
      { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
    ]},
    { label: 'OpenAI', models: [
      { value: 'gpt-4o', label: 'GPT-4o' },
      { value: 'gpt-4o-mini', label: 'GPT-4o mini' },
    ]},
    { label: 'Google Gemini', models: [
      { value: 'gemini/gemini-1.5-pro', label: 'Gemini 1.5 Pro' },
      { value: 'gemini/gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
    ]},
    ...(allOllamaModels.length > 0 ? [{
      label: 'Ollama (local — installed)',
      models: allOllamaModels.map(m => ({
        value: m.value,
        label: m.label || `${m.name} (local)`,
      })),
    }] : [{
      label: 'Ollama (not connected — see below)',
      models: [{ value: 'ollama/gemma4:latest', label: 'gemma4:latest (start Ollama first)' }],
    }]),
  ]

  const ModelSelect = ({ label, field, help }) => (
    <div>
      <label className="label">{label}</label>
      <select
        className="input"
        value={form[field]}
        onChange={e => setForm(f => ({ ...f, [field]: e.target.value }))}
      >
        {MODEL_GROUPS.map(g => (
          <optgroup key={g.label} label={g.label}>
            {g.models.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </optgroup>
        ))}
      </select>
      {help && <p className="text-xs text-gray-400 mt-1">{help}</p>}
    </div>
  )

  return (
    <div className="p-8 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Configuration</h1>
        <p className="text-sm text-gray-500 mt-1">AI providers, model assignments, and system settings</p>
      </div>

      {/* Provider status */}
      <Section title="AI Provider Status">
        {statusLoading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm"><Loader2 size={14} className="animate-spin" /> Checking...</div>
        ) : status ? (
          <div className="space-y-2">
            {[
              ['Anthropic (Claude)', status.providers?.anthropic, 'ANTHROPIC_API_KEY'],
              ['OpenAI (GPT-4o)', status.providers?.openai, 'OPENAI_API_KEY'],
              ['Google (Gemini)', status.providers?.google, 'GEMINI_API_KEY'],
              ['Ollama (local)', status.providers?.ollama, null],
            ].map(([name, ok, envKey]) => (
              <div key={name} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                <div className="flex items-center gap-2">
                  <StatusDot ok={ok} />
                  <span className="text-sm text-gray-700">{name}</span>
                  {envKey && !ok && <span className="text-xs text-gray-400">set {envKey} in .env</span>}
                </div>
                {name === 'Ollama (local)' && (
                  <span className="text-xs text-gray-400">{status.ollama_base_url}</span>
                )}
              </div>
            ))}
          </div>
        ) : null}
        <button onClick={() => refetchStatus()} className="btn-ghost text-xs mt-3 gap-1.5">
          <RefreshCw size={11} />Refresh status
        </button>
      </Section>

      {/* Ollama panel */}
      <Section title="Ollama (Local Models)">
        <div className="flex items-center gap-2 mb-4">
          <Server size={16} className={ollamaInfo?.connected ? 'text-emerald-500' : 'text-red-400'} />
          <span className="text-sm font-medium">
            {ollamaInfo?.connected ? `Connected — ${ollamaInfo.models?.length || 0} model(s) installed` : 'Not connected'}
          </span>
          <button onClick={() => refetchOllama()} className="ml-auto btn-ghost text-xs gap-1">
            <RefreshCw size={11} />Test
          </button>
        </div>

        {ollamaInfo?.connected && allOllamaModels.length > 0 && (
          <div className="bg-gray-50 rounded-xl p-3 mb-4">
            <p className="text-xs font-medium text-gray-500 mb-2">Installed models</p>
            <div className="flex flex-wrap gap-1.5">
              {allOllamaModels.map(m => (
                <span key={m.name} className="badge bg-emerald-50 text-emerald-700 text-xs">{m.name}</span>
              ))}
            </div>
          </div>
        )}

        {!ollamaInfo?.connected && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm space-y-3">
            <p className="font-medium text-amber-800">Ollama not reachable from Docker</p>
            <p className="text-amber-700 text-xs leading-relaxed">
              Ollama is probably running but bound to <code className="bg-amber-100 px-1 rounded">127.0.0.1</code> only.
              Docker containers can't reach it. You need to restart Ollama bound to all interfaces:
            </p>
            <pre className="bg-amber-100 rounded px-3 py-2 text-xs font-mono text-amber-900 whitespace-pre-wrap">
{`# Stop current Ollama, then restart with:
OLLAMA_HOST=0.0.0.0 ollama serve

# Or set permanently in your shell profile:
echo 'export OLLAMA_HOST=0.0.0.0' >> ~/.bashrc`}
            </pre>
            <p className="text-amber-700 text-xs">
              Current URL: <code className="bg-amber-100 px-1 rounded">{ollamaInfo?.base_url || 'http://host.docker.internal:11434'}</code>
            </p>
            <p className="text-amber-600 text-xs">
              After restarting Ollama, click <strong>Test</strong> above to verify.
            </p>
          </div>
        )}
      </Section>

      {/* Per-agent model assignment */}
      <Section title="Agent Model Assignment">
        <p className="text-xs text-gray-400 mb-4">
          Assign different models to each task. Use a fast local model for ingestion, a smarter model for the librarian chat.
        </p>
        <div className="space-y-4">
          <ModelSelect
            label="Alexandria (librarian chat)"
            field="librarian_model"
            help="Handles all chat queries. Benefits most from a capable model."
          />
          <ModelSelect
            label="Ingestion (PDF & URL processing)"
            field="ingestion_model"
            help="Generates metadata, summaries, and tags. A faster model is fine here."
          />
          <ModelSelect
            label="Digest generation"
            field="digest_model"
            help="Writes monthly synthesis reports. Use a model with a large context window."
          />
        </div>
      </Section>

      {/* System prompt */}
      <Section title="Alexandria's Instructions">
        <p className="text-xs text-gray-400 mb-3">
          Customise how Alexandria behaves. Add domain-specific focus, citation styles, or priorities.
          E.g. <em>"Focus on Australian government policy. Always note publication dates."</em>
        </p>
        <textarea
          className="input font-mono text-xs leading-relaxed"
          rows={10}
          value={form.librarian_system_prompt}
          onChange={e => setForm(f => ({ ...f, librarian_system_prompt: e.target.value }))}
        />
        <button
          onClick={() => setForm(f => ({ ...f, librarian_system_prompt: DEFAULT_PROMPT }))}
          className="btn-ghost text-xs mt-2"
        >
          Reset to default
        </button>
      </Section>

      {/* Per-project API key overrides */}
      <Section title="API Key Overrides">
        <p className="text-xs text-gray-400 mb-4">
          Override the system API keys (set in <code className="bg-gray-100 px-1 rounded">.env</code>) with project-specific keys.
          Useful if team members have their own frontier API accounts.
          Keys are stored in the project settings — only enter keys you're comfortable storing in the database.
        </p>
        <div className="space-y-3">
          {[
            ['anthropic_api_key', 'Anthropic API key', 'sk-ant-...'],
            ['openai_api_key', 'OpenAI API key', 'sk-...'],
            ['gemini_api_key', 'Google Gemini API key', 'AI...'],
          ].map(([field, label, placeholder]) => (
            <div key={field}>
              <label className="label">{label} <span className="text-gray-400 font-normal">(optional override)</span></label>
              <input
                type="password"
                className="input font-mono text-xs"
                placeholder={placeholder}
                value={form[field] || ''}
                onChange={e => setForm(f => ({ ...f, [field]: e.target.value }))}
                autoComplete="off"
              />
            </div>
          ))}
        </div>
      </Section>

      {/* Digest mailing list */}
      <Section title="Digest Mailing List">
        <div className="flex items-center gap-2 mb-3">
          <Mail size={15} className={status?.email_configured ? 'text-emerald-500' : 'text-gray-300'} />
          <span className="text-sm text-gray-600">
            {status?.email_configured ? 'SMTP configured' : 'SMTP not configured — set SMTP_HOST in .env'}
          </span>
        </div>
        <label className="label">Recipients (one per line)</label>
        <textarea
          className="input font-mono text-xs"
          rows={4}
          placeholder={'alice\nbob\ncharlie'}
          value={form.digest_recipients}
          onChange={e => setForm(f => ({ ...f, digest_recipients: e.target.value }))}
        />
        <p className="text-xs text-gray-400 mt-1">
          Digests are sent when you click "Send email" on the Digest page.
          {!status?.email_configured && ' Configure SMTP in .env to enable.'}
        </p>
      </Section>

      {/* Email ingestion */}
      <Section title="Email Ingestion — Submit PDFs & Links by Email">
        <div className="bg-alexandria-50 border border-alexandria-200 rounded-xl p-4 mb-4">
          <p className="text-sm text-alexandria-800 leading-relaxed">
            <strong>How it works:</strong> Create a dedicated inbox (e.g. <code className="bg-alexandria-100 px-1 rounded">ingest@yourdomain.com</code>
            {' '}or a Gmail alias). Any team member can email PDFs or paste URLs to that address.
            Alexandria checks it every 10 minutes, processes attachments and links, and files them into the library.
            She replies to the sender with a confirmation.
          </p>
        </div>

        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mb-5 text-xs text-amber-800">
          <strong>API keys &amp; "Pro" accounts:</strong> Claude.ai Pro, ChatGPT Plus, and Gemini Advanced are
          consumer subscriptions — they don't expose API access. SciLibrarian uses the developer APIs (Anthropic API,
          OpenAI API, Google AI API) which have separate billing. To use your own key, enter it in the
          API Key Overrides section above. Your team can share one key set in <code>.env</code>, or each
          project can override with its own.
        </div>

        <p className="text-xs text-gray-500 mb-4">
          Enable in <code className="bg-gray-100 px-1 rounded">.env</code> — set{' '}
          <code className="bg-gray-100 px-1 rounded">INGEST_EMAIL_ENABLED=true</code> and your IMAP credentials.
          Works with Gmail, Outlook, Fastmail, or any IMAP provider.
        </p>

        <div className="bg-gray-800 rounded-xl p-4 text-xs font-mono text-green-400 space-y-0.5">
          <p>INGEST_EMAIL_ENABLED=true</p>
          <p>INGEST_IMAP_HOST=imap.gmail.com</p>
          <p>INGEST_IMAP_PORT=993</p>
          <p>INGEST_IMAP_USERNAME=ingest@yourdomain.com</p>
          <p>INGEST_IMAP_PASSWORD=your-app-password</p>
          <p>INGEST_DEFAULT_PROJECT_ID=1</p>
          <p>INGEST_CHECK_INTERVAL_MINUTES=10</p>
        </div>

        <p className="text-xs text-gray-400 mt-3">
          <strong>Gmail tip:</strong> Use an App Password (not your regular password) — enable 2FA then generate
          one at myaccount.google.com/apppasswords. Set INGEST_IMAP_HOST=imap.gmail.com.
        </p>
      </Section>

      {/* Search sources */}
      <Section title="Search Sources">
        <p className="text-xs text-gray-400 mb-3">All sources are free — API keys only improve rate limits.</p>
        <div className="space-y-2">
          {[
            ['arXiv', true, 'AI/ML preprints — no key needed'],
            ['Semantic Scholar', true, `200M+ papers${status?.search_sources?.semantic_scholar_key ? ' (API key set ✓)' : ' — set SEMANTIC_SCHOLAR_API_KEY for higher rate limit'}`],
            ['OpenAlex', true, `250M+ works${status?.search_sources?.openalex_email ? ' (email set ✓)' : ' — set OPENALEX_EMAIL for polite pool'}`],
            ['Web (DuckDuckGo)', true, 'Government sites, news, reports — no key needed'],
          ].map(([name, ok, note]) => (
            <div key={name} className="flex items-start gap-2 py-1.5 border-b border-gray-50 last:border-0">
              <StatusDot ok={ok} />
              <div>
                <span className="text-sm text-gray-700">{name}</span>
                <p className="text-xs text-gray-400">{note}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <div className="flex justify-end pb-8">
        <button onClick={save} disabled={saving || !project} className="btn-primary">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Save configuration
        </button>
      </div>
    </div>
  )
}
