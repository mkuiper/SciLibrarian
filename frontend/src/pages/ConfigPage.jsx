import { useState, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { configApi, librarianApi, projectsApi } from '../api/client'
import {
  CheckCircle, XCircle, Loader2, RefreshCw, Server, Mail, Save,
  Database, HardDrive, Clock, Play, Pause, Zap, AlertCircle, X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow, format } from 'date-fns'

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

// ── API Key Test Button ───────────────────────────────────────────────────────

function KeyTestButton({ provider, keyValue }) {
  const [state, setState] = useState(null) // null | 'loading' | {ok, model, latency_ms, error}

  const run = async () => {
    setState('loading')
    try {
      const { data } = await configApi.testKey(provider, keyValue)
      setState(data)
    } catch {
      setState({ ok: false, error: 'Request failed' })
    }
  }

  if (state === 'loading') {
    return (
      <button disabled className="btn-ghost text-xs gap-1 opacity-60">
        <Loader2 size={11} className="animate-spin" />Testing…
      </button>
    )
  }

  if (state?.ok) {
    return (
      <span className="flex items-center gap-1 text-xs text-emerald-600">
        <CheckCircle size={12} />
        {state.model?.split('/').pop() ?? 'OK'} · {state.latency_ms}ms
      </span>
    )
  }

  if (state?.ok === false) {
    return (
      <span className="flex items-center gap-1 text-xs text-red-500" title={state.error}>
        <XCircle size={12} />
        {state.error?.slice(0, 40) ?? 'Failed'}
      </span>
    )
  }

  return (
    <button onClick={run} className="btn-ghost text-xs gap-1">
      <Zap size={11} />Test
    </button>
  )
}

// ── System Status Panel ───────────────────────────────────────────────────────

function SystemStatusPanel() {
  const queryClient = useQueryClient()
  const [schedulerBusy, setSchedulerBusy] = useState(false)

  const { data: sys, isLoading, refetch } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => configApi.systemStatus().then(r => r.data),
    refetchInterval: false,
    staleTime: 30_000,
  })

  const toggleScheduler = async () => {
    if (!sys) return
    const isPaused = sys.scheduler?.paused
    const action = isPaused ? 'resume' : 'pause'
    setSchedulerBusy(true)
    try {
      await configApi.schedulerControl(action)
      toast.success(`Scheduler ${isPaused ? 'resumed' : 'paused'}`)
      queryClient.invalidateQueries({ queryKey: ['system-status'] })
      refetch()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Scheduler control failed')
    } finally {
      setSchedulerBusy(false)
    }
  }

  const nextRunLabel = (isoStr) => {
    if (!isoStr) return 'not scheduled'
    try {
      const d = new Date(isoStr)
      return `${formatDistanceToNow(d, { addSuffix: true })} (${format(d, 'd MMM HH:mm')} UTC)`
    } catch { return isoStr }
  }

  const jobMap = {}
  for (const j of sys?.scheduler?.jobs || []) jobMap[j.id] = j

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 text-sm py-2">
        <Loader2 size={14} className="animate-spin" />Loading system status…
      </div>
    )
  }

  if (!sys) return null

  const rows = [
    {
      icon: Database,
      label: 'Database',
      ok: sys.database?.ok,
      detail: sys.database?.ok
        ? `${sys.database.reference_count} references · ${sys.database.pending_queue} pending review`
        : 'Cannot connect',
    },
    {
      icon: HardDrive,
      label: 'Upload storage',
      ok: true,
      detail: `${sys.storage?.count ?? 0} file${sys.storage?.count !== 1 ? 's' : ''} · ${sys.storage?.total_mb ?? 0} MB  (${sys.storage?.upload_dir})`,
    },
    {
      icon: Clock,
      label: 'Scheduler',
      ok: sys.scheduler?.running && !sys.scheduler?.paused,
      detail: !sys.scheduler?.running
        ? 'Not running'
        : sys.scheduler?.paused
        ? 'Paused'
        : `Running · monitors: ${nextRunLabel(jobMap['run_monitors']?.next_run)} · digest: ${nextRunLabel(jobMap['monthly_digest']?.next_run)}`,
      action: sys.scheduler?.running ? (
        <button
          onClick={toggleScheduler}
          disabled={schedulerBusy}
          className="btn-ghost text-xs gap-1 ml-2"
          title={sys.scheduler?.paused ? 'Resume scheduler' : 'Pause scheduler'}
        >
          {schedulerBusy
            ? <Loader2 size={11} className="animate-spin" />
            : sys.scheduler?.paused ? <Play size={11} /> : <Pause size={11} />
          }
          {sys.scheduler?.paused ? 'Resume' : 'Pause'}
        </button>
      ) : null,
    },
  ]

  return (
    <div className="space-y-2">
      {rows.map(({ icon: Icon, label, ok, detail, action }) => (
        <div key={label} className="flex items-start gap-3 py-2 border-b border-gray-50 last:border-0">
          <Icon size={15} className={ok ? 'text-emerald-500 mt-0.5 flex-shrink-0' : 'text-red-400 mt-0.5 flex-shrink-0'} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1">
              <span className="text-sm font-medium text-gray-700">{label}</span>
              {action}
            </div>
            <p className="text-xs text-gray-400 mt-0.5 break-all">{detail}</p>
          </div>
        </div>
      ))}
      <button onClick={() => refetch()} className="btn-ghost text-xs mt-1 gap-1.5">
        <RefreshCw size={11} />Refresh
      </button>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

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

  const { data: overrides, refetch: refetchOverrides } = useQuery({
    queryKey: ['config-overrides'],
    queryFn: () => configApi.getOverrides().then(r => r.data),
  })

  const [overrideModel, setOverrideModel] = useState('')
  useEffect(() => {
    setOverrideModel(overrides?.model_override || '')
  }, [overrides?.model_override])

  const [overrideBusy, setOverrideBusy] = useState(false)
  const [diagnostics, setDiagnostics] = useState(null)
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false)
  const runOllamaDiagnostics = async () => {
    setDiagnosticsLoading(true)
    try {
      const { data } = await configApi.ollamaDiagnostics()
      setDiagnostics(data)
    } catch {
      toast.error('Diagnostics failed')
    } finally {
      setDiagnosticsLoading(false)
    }
  }
  const applyOverride = async () => {
    setOverrideBusy(true)
    try {
      await configApi.setModelOverride(overrideModel || null)
      await refetchOverrides()
      toast.success(overrideModel ? `All agents → ${overrideModel}` : 'Override cleared')
    } catch {
      toast.error('Failed to update override')
    } finally {
      setOverrideBusy(false)
    }
  }
  const clearOverride = async () => {
    setOverrideBusy(true)
    try {
      await configApi.setModelOverride(null)
      setOverrideModel('')
      await refetchOverrides()
      toast.success('Override cleared')
    } catch {
      toast.error('Failed to clear override')
    } finally {
      setOverrideBusy(false)
    }
  }

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const project = projects[0]
  const ps = project?.settings || {}

  const DEFAULT_MODEL = 'ollama/gemma4:latest'

  const [form, setForm] = useState({
    librarian_model: DEFAULT_MODEL,
    ingestion_model: DEFAULT_MODEL,
    digest_model: DEFAULT_MODEL,
    librarian_system_prompt: DEFAULT_PROMPT,
    digest_recipients: '',
    anthropic_api_key: '',
    openai_api_key: '',
    gemini_api_key: '',
  })

  useEffect(() => {
    if (!project) return
    const s = project.settings || {}
    setForm({
      librarian_model:         s.librarian_model         || DEFAULT_MODEL,
      ingestion_model:         s.ingestion_model         || DEFAULT_MODEL,
      digest_model:            s.digest_model            || DEFAULT_MODEL,
      librarian_system_prompt: s.librarian_system_prompt || DEFAULT_PROMPT,
      digest_recipients:       (s.digest_recipients || []).join('\n'),
      anthropic_api_key:       s.anthropic_api_key       || '',
      openai_api_key:          s.openai_api_key          || '',
      gemini_api_key:          s.gemini_api_key          || '',
    })
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

      {/* ── System Status ────────────────────────────────── */}
      <Section title="System Status">
        <SystemStatusPanel />
      </Section>

      {/* ── AI Provider Status ───────────────────────────── */}
      <Section title="AI Provider Status">
        {statusLoading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm"><Loader2 size={14} className="animate-spin" /> Checking...</div>
        ) : status ? (
          <div className="space-y-2">
            {[
              ['Anthropic (Claude)', status.providers?.anthropic, 'ANTHROPIC_API_KEY'],
              ['OpenAI (GPT-4o)',    status.providers?.openai,    'OPENAI_API_KEY'],
              ['Google (Gemini)',    status.providers?.google,    'GEMINI_API_KEY'],
              ['Ollama (local)',     status.providers?.ollama,    null],
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

      {/* ── Ollama panel ─────────────────────────────────── */}
      <Section title="Ollama (Local Models)">
        <div className="flex items-center gap-2 mb-4">
          <Server size={16} className={ollamaInfo?.connected ? 'text-emerald-500' : 'text-red-400'} />
          <span className="text-sm font-medium">
            {ollamaInfo?.connected
              ? `Connected — ${ollamaInfo.models?.length || 0} model(s) installed`
              : 'Not connected'}
          </span>
          <button onClick={() => refetchOllama()} className="ml-auto btn-ghost text-xs gap-1">
            <RefreshCw size={11} />Test
          </button>
          <button onClick={() => runOllamaDiagnostics()} disabled={diagnosticsLoading} className="btn-ghost text-xs gap-1">
            {diagnosticsLoading ? <Loader2 size={11} className="animate-spin" /> : null}
            Diagnose
          </button>
        </div>

        {diagnostics && (
          <div className="bg-gray-50 border border-gray-100 rounded-xl p-3 mb-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-gray-600">Diagnostics — probed {diagnostics.probes?.length} URL(s)</p>
              <button onClick={() => setDiagnostics(null)} className="text-gray-300 hover:text-gray-600"><X size={12} /></button>
            </div>
            <ul className="space-y-1">
              {diagnostics.probes?.map(p => (
                <li key={p.url} className="text-xs flex items-center gap-2 font-mono">
                  <StatusDot ok={p.reachable} />
                  <span className="flex-1 break-all">{p.url}</span>
                  {p.reachable
                    ? <span className="text-emerald-600">{p.latency_ms}ms{p.version ? ` · v${p.version}` : ''}</span>
                    : <span className="text-red-400">{p.error || 'unreachable'}</span>}
                </li>
              ))}
            </ul>
            {diagnostics.loaded_models?.length > 0 && (
              <div>
                <p className="text-xs text-gray-500 mb-1">Currently loaded in GPU:</p>
                <div className="flex flex-wrap gap-1.5">
                  {diagnostics.loaded_models.map(m => (
                    <span key={m.name} className="badge bg-blue-50 text-blue-700 text-xs">
                      {m.name} <span className="opacity-60 ml-1">{m.size_mb} MB</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
            {diagnostics.remediation?.length > 0 && (
              <div className="bg-amber-50 border border-amber-100 rounded-lg p-2.5">
                {diagnostics.remediation.map((r, i) => (
                  <div key={i}>
                    <p className="text-xs font-semibold text-amber-800 mb-1">{r.title}</p>
                    <ol className="text-xs text-amber-700 list-decimal list-inside space-y-0.5">
                      {r.steps.map((s, j) => (
                        <li key={j} className="font-mono whitespace-pre-wrap">{s}</li>
                      ))}
                    </ol>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {ollamaInfo?.connected && allOllamaModels.length > 0 && (
          <div className="bg-gray-50 rounded-xl p-3 mb-4">
            <p className="text-xs font-medium text-gray-500 mb-2">Installed models</p>
            <div className="flex flex-wrap gap-1.5">
              {allOllamaModels.map(m => (
                <span key={m.name || m.value} className="badge bg-emerald-50 text-emerald-700 text-xs">
                  {m.name || m.value}
                  {m.supports_tools && <span className="ml-1 opacity-60">tools✓</span>}
                </span>
              ))}
            </div>
          </div>
        )}

        {!ollamaInfo?.connected && (
          <div className="space-y-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <p className="font-semibold text-emerald-800 text-sm mb-1">
                Option A — Ollama inside Docker (recommended)
              </p>
              <p className="text-emerald-700 text-xs mb-3">
                Stop the current stack and restart with the Ollama profile. Models are stored in a Docker volume.
              </p>
              <pre className="bg-emerald-100 rounded px-3 py-2 text-xs font-mono text-emerald-900 whitespace-pre-wrap">
{`docker-compose down
docker-compose --profile ollama up --build

# Pull models (in another terminal):
docker-compose exec ollama ollama pull gemma4
docker-compose exec ollama ollama pull qwen3.5:9b`}
              </pre>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
              <p className="font-semibold text-amber-800 text-sm mb-1">
                Option B — Fix host Ollama (systemd)
              </p>
              <pre className="bg-amber-100 rounded px-3 py-2 text-xs font-mono text-amber-900 whitespace-pre-wrap">
{`sudo systemctl stop ollama
sudo systemctl edit ollama
# Add: [Service]
#      Environment="OLLAMA_HOST=0.0.0.0"
sudo systemctl daemon-reload && sudo systemctl start ollama`}
              </pre>
            </div>

            <p className="text-xs text-gray-400">
              Current URL: <code className="bg-gray-100 px-1 rounded">{ollamaInfo?.base_url || 'http://host.docker.internal:11434'}</code>
              {' '}· Click <strong>Test</strong> after fixing.
            </p>
          </div>
        )}
      </Section>

      {/* ── Global model override ─────────────────────────── */}
      <Section title="Apply One Model to All Agents">
        <p className="text-xs text-gray-400 mb-3">
          Optional override that routes every agent call (librarian chat, ingestion, digests, monitor
          suggestions) through a single model — useful when only one local Ollama model is available.
          Per-agent assignments below are ignored while this is set.
        </p>
        {overrides?.model_override && (
          <div className="mb-3 p-3 bg-alexandria-50 border border-alexandria-200 rounded-xl text-sm flex items-center gap-2">
            <span className="text-alexandria-800 font-medium">Active:</span>
            <code className="text-alexandria-700 bg-white px-2 py-0.5 rounded text-xs">{overrides.model_override}</code>
            <span className="text-xs text-alexandria-600 ml-auto">all agents use this</span>
          </div>
        )}
        <div className="flex items-end gap-2">
          <div className="flex-1">
            <label className="label">Override model</label>
            <select
              className="input"
              value={overrideModel}
              onChange={e => setOverrideModel(e.target.value)}
            >
              <option value="">(no override — per-agent settings below apply)</option>
              {MODEL_GROUPS.map(group => (
                <optgroup key={group.label} label={group.label}>
                  {group.models.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <button
            onClick={applyOverride}
            disabled={overrideBusy || overrideModel === (overrides?.model_override || '')}
            className="btn-primary text-sm"
          >
            {overrideBusy ? <Loader2 size={12} className="animate-spin" /> : null}
            {overrideModel ? 'Apply' : 'Clear'}
          </button>
          {overrides?.model_override && (
            <button onClick={clearOverride} disabled={overrideBusy} className="btn-ghost text-sm">
              Clear
            </button>
          )}
        </div>
      </Section>

      {/* ── Agent model assignment ────────────────────────── */}
      <Section title="Agent Model Assignment">
        <p className="text-xs text-gray-400 mb-4">
          Assign different models to each task. Use a fast local model for ingestion, a smarter model for the librarian chat.
        </p>
        <div className="space-y-4">
          <ModelSelect label="Alexandria (librarian chat)"  field="librarian_model" help="Handles all chat queries. Benefits most from a capable model." />
          <ModelSelect label="Ingestion (PDF & URL processing)" field="ingestion_model" help="Generates metadata, summaries, and tags. A faster model is fine here." />
          <ModelSelect label="Digest generation" field="digest_model" help="Writes synthesis reports. Use a model with a large context window." />
        </div>
      </Section>

      {/* ── Alexandria's instructions ─────────────────────── */}
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

      {/* ── API key overrides ─────────────────────────────── */}
      <Section title="API Key Overrides">
        <p className="text-xs text-gray-400 mb-4">
          Override the system API keys (set in <code className="bg-gray-100 px-1 rounded">.env</code>) with project-specific keys.
          Keys are stored in the project settings — only enter keys you're comfortable storing in the database.
        </p>
        <div className="space-y-4">
          {[
            { field: 'anthropic_api_key', label: 'Anthropic API key', placeholder: 'sk-ant-…', provider: 'anthropic' },
            { field: 'openai_api_key',    label: 'OpenAI API key',    placeholder: 'sk-…',     provider: 'openai' },
            { field: 'gemini_api_key',    label: 'Google Gemini API key', placeholder: 'AI…',  provider: 'google' },
          ].map(({ field, label, placeholder, provider }) => (
            <div key={field}>
              <label className="label">{label} <span className="text-gray-400 font-normal">(optional override)</span></label>
              <div className="flex gap-2 items-center">
                <input
                  type="password"
                  className="input font-mono text-xs flex-1"
                  placeholder={placeholder}
                  value={form[field] || ''}
                  onChange={e => setForm(f => ({ ...f, [field]: e.target.value }))}
                  autoComplete="off"
                />
                <KeyTestButton provider={provider} keyValue={form[field] || ''} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 p-3 bg-amber-50 border border-amber-100 rounded-xl text-xs text-amber-800">
          <strong>Note:</strong> Claude.ai Pro, ChatGPT Plus, and Gemini Advanced are consumer subscriptions —
          they don't expose API access. You need the developer API (separate billing).
        </div>
      </Section>

      {/* ── Digest mailing list ───────────────────────────── */}
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
          placeholder={'alice@example.com\nbob@example.com'}
          value={form.digest_recipients}
          onChange={e => setForm(f => ({ ...f, digest_recipients: e.target.value }))}
        />
        <p className="text-xs text-gray-400 mt-1">
          Digests are sent when you click "Send email" on the Digest page.
          {!status?.email_configured && ' Configure SMTP in .env to enable.'}
        </p>
      </Section>

      {/* ── Email ingestion ───────────────────────────────── */}
      <Section title="Email Ingestion — Submit PDFs & Links by Email">
        <div className="bg-alexandria-50 border border-alexandria-200 rounded-xl p-4 mb-4">
          <p className="text-sm text-alexandria-800 leading-relaxed">
            <strong>How it works:</strong> Create a dedicated inbox (e.g.{' '}
            <code className="bg-alexandria-100 px-1 rounded">ingest@yourdomain.com</code>).
            Any team member can email PDFs or paste URLs to that address.
            Alexandria checks it every 10 minutes and files them into the library.
          </p>
        </div>

        <p className="text-xs text-gray-500 mb-4">
          Enable in <code className="bg-gray-100 px-1 rounded">.env</code> — set{' '}
          <code className="bg-gray-100 px-1 rounded">INGEST_EMAIL_ENABLED=true</code> and your IMAP credentials.
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
          <strong>Gmail tip:</strong> Use an App Password — enable 2FA then generate one at
          myaccount.google.com/apppasswords.
        </p>
      </Section>

      {/* ── Search sources ────────────────────────────────── */}
      <Section title="Search Sources">
        <p className="text-xs text-gray-400 mb-3">All sources are free — API keys only improve rate limits.</p>
        <div className="space-y-2">
          {[
            ['arXiv', true, 'AI/ML preprints — no key needed'],
            ['Semantic Scholar', true, `200M+ papers${status?.search_sources?.semantic_scholar_key ? ' (API key set ✓)' : ' — set SEMANTIC_SCHOLAR_API_KEY for higher rate limit'}`],
            ['OpenAlex', true, `250M+ works${status?.search_sources?.openalex_email ? ' (email set ✓)' : ' — set OPENALEX_EMAIL for polite pool'}`],
            ['Web (Brave/DDG)', true, 'Government sites, news, reports'],
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
