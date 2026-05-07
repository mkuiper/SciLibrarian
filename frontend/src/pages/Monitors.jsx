import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { reviewApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import { Plus, Play, Pause, Trash2, Loader2, Radio } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'

const FREQUENCIES = ['daily', 'weekly']

function MonitorForm({ onClose, projectId }) {
  const [form, setForm] = useState({
    name: '',
    query: '',
    sources: 'arxiv,semantic_scholar,openalex,web,huggingface',
    frequency: 'weekly',
  })
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await reviewApi.createMonitor({ ...form, project_id: projectId || undefined })
      queryClient.invalidateQueries({ queryKey: ['monitors'] })
      toast.success('Monitor created')
      onClose()
    } catch {
      toast.error('Failed to create monitor')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card p-5 mb-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">New search monitor</h3>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label className="label">Monitor name</label>
          <input className="input" required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. AI alignment papers" />
        </div>
        <div>
          <label className="label">Search query</label>
          <input className="input" required value={form.query} onChange={e => setForm(f => ({ ...f, query: e.target.value }))} placeholder="e.g. constitutional AI alignment safety" />
          <p className="text-xs text-gray-400 mt-1">Keywords Alexandria will search across all configured sources</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Frequency</label>
            <select className="input" value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}>
              {FREQUENCIES.map(f => <option key={f} value={f}>{f.charAt(0).toUpperCase() + f.slice(1)}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Sources</label>
            <select className="input" value={form.sources} onChange={e => setForm(f => ({ ...f, sources: e.target.value }))}>
              <option value="arxiv,semantic_scholar,openalex,web,huggingface">All sources (recommended)</option>
              <option value="arxiv,openalex,web,huggingface">Academic + Web + HuggingFace</option>
              <option value="arxiv,semantic_scholar,openalex">Academic only</option>
              <option value="web,huggingface">Web + HuggingFace (model cards, reports)</option>
              <option value="huggingface">HuggingFace only (model cards)</option>
              <option value="web">Web search only (policy, news, gov docs)</option>
              <option value="arxiv">arXiv only</option>
              <option value="semantic_scholar">Semantic Scholar only</option>
              <option value="openalex">OpenAlex only</option>
            </select>
          </div>
        </div>
        <div className="flex gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn-ghost text-xs">Cancel</button>
          <button type="submit" disabled={loading} className="btn-primary text-xs">
            {loading && <Loader2 size={12} className="animate-spin" />}
            Create monitor
          </button>
        </div>
      </form>
    </div>
  )
}

function MonitorCard({ monitor }) {
  const [running, setRunning] = useState(false)
  const queryClient = useQueryClient()

  const runNow = async () => {
    setRunning(true)
    try {
      const { data } = await reviewApi.runMonitor(monitor.id)
      toast.success(`Monitor ran — ${data.added_to_queue} items added to review queue`)
      queryClient.invalidateQueries({ queryKey: ['review-queue'] })
    } catch {
      toast.error('Failed to run monitor')
    } finally {
      setRunning(false)
    }
  }

  const toggle = async () => {
    try {
      await reviewApi.updateMonitor(monitor.id, { enabled: !monitor.enabled })
      queryClient.invalidateQueries({ queryKey: ['monitors'] })
    } catch {
      toast.error('Failed to update monitor')
    }
  }

  const del = async () => {
    if (!confirm('Delete this monitor?')) return
    try {
      await reviewApi.deleteMonitor(monitor.id)
      queryClient.invalidateQueries({ queryKey: ['monitors'] })
      toast.success('Monitor deleted')
    } catch {
      toast.error('Failed to delete monitor')
    }
  }

  return (
    <div className={`card p-5 ${!monitor.enabled ? 'opacity-60' : ''}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <Radio size={14} className={monitor.enabled ? 'text-emerald-500' : 'text-gray-400'} />
            <span className="text-sm font-semibold text-gray-900">{monitor.name}</span>
            <span className={`badge text-xs ${monitor.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
              {monitor.enabled ? 'active' : 'paused'}
            </span>
          </div>
          <p className="text-xs text-gray-500 font-mono bg-gray-50 px-2 py-1 rounded mt-2 inline-block">
            "{monitor.query}"
          </p>
          <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
            <span>{monitor.frequency}</span>
            <span>·</span>
            <span>{monitor.sources.split(',').join(', ')}</span>
            {monitor.last_run && (
              <>
                <span>·</span>
                <span>Last run {formatDistanceToNow(new Date(monitor.last_run), { addSuffix: true })}</span>
              </>
            )}
          </div>
          {(monitor.approve_count + monitor.reject_count) > 0 && (
            <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
              <span className="text-emerald-600">✓ {monitor.approve_count} approved</span>
              <span className="text-red-400">✗ {monitor.reject_count} rejected</span>
              <span className={`font-medium ${
                (monitor.approve_count / (monitor.approve_count + monitor.reject_count)) >= 0.6
                  ? 'text-emerald-600' : 'text-amber-500'
              }`}>
                {Math.round(100 * monitor.approve_count / (monitor.approve_count + monitor.reject_count))}% precision
              </span>
            </div>
          )}
        </div>
        <div className="flex gap-1.5">
          <button onClick={runNow} disabled={running} className="btn-ghost p-2" title="Run now">
            {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          </button>
          <button onClick={toggle} className="btn-ghost p-2" title={monitor.enabled ? 'Pause' : 'Resume'}>
            <Pause size={14} />
          </button>
          <button onClick={del} className="btn-ghost p-2 text-red-400 hover:text-red-600" title="Delete">
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Monitors() {
  const [showForm, setShowForm] = useState(false)
  const { projectId } = useProject()

  const { data: monitors = [], isLoading } = useQuery({
    queryKey: ['monitors', projectId],
    queryFn: () => reviewApi.listMonitors(projectId ? { project_id: projectId } : {}).then(r => r.data),
  })

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Search Monitors</h1>
          <p className="text-sm text-gray-500 mt-1">
            Alexandria watches these queries and adds discoveries to your review queue.
          </p>
        </div>
        <button onClick={() => setShowForm(v => !v)} className="btn-primary">
          <Plus size={15} />
          New monitor
        </button>
      </div>

      {showForm && <MonitorForm onClose={() => setShowForm(false)} projectId={projectId} />}

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-gray-300" />
        </div>
      ) : monitors.length === 0 ? (
        <div className="text-center py-16">
          <Radio size={32} className="text-gray-200 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">No monitors yet</p>
          <p className="text-gray-400 text-sm mt-1">
            Create a monitor to have Alexandria proactively find new references.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {monitors.map(m => <MonitorCard key={m.id} monitor={m} />)}
        </div>
      )}
    </div>
  )
}
