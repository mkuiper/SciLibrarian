import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectsApi } from '../api/client'
import { Eye, Plus, Loader2, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'

const SOURCE_TYPE_OPTIONS = [
  'paper', 'policy', 'model_card', 'evaluation', 'government', 'news', 'any',
]

function WatchRequestForm({ projectId, onClose }) {
  const [form, setForm] = useState({ description: '', keywords: '', source_types: 'any' })
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await projectsApi.createWatchRequest(projectId, {
        description: form.description,
        keywords: form.keywords || null,
        source_types: form.source_types === 'any' ? null : form.source_types,
      })
      queryClient.invalidateQueries({ queryKey: ['watch-requests', projectId] })
      toast.success('Watch request created — Alexandria will look out for this')
      onClose()
    } catch {
      toast.error('Failed to create watch request')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card p-5 mb-6">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">New watch request</h3>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label className="label">What should Alexandria look out for?</label>
          <textarea
            className="input"
            rows={3}
            required
            value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            placeholder="e.g. Papers on mechanistic interpretability of large language models, especially work from Anthropic or DeepMind. I'm particularly interested in sparse autoencoders and activation patching methods."
          />
          <p className="text-xs text-gray-400 mt-1">
            Write naturally — Alexandria will extract the relevant search terms.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Keywords (optional)</label>
            <input
              className="input"
              value={form.keywords}
              onChange={e => setForm(f => ({ ...f, keywords: e.target.value }))}
              placeholder="e.g. mechanistic interpretability, SAE"
            />
          </div>
          <div>
            <label className="label">Source type</label>
            <select
              className="input"
              value={form.source_types}
              onChange={e => setForm(f => ({ ...f, source_types: e.target.value }))}
            >
              {SOURCE_TYPE_OPTIONS.map(t => (
                <option key={t} value={t}>{t === 'any' ? 'Any type' : t.replace('_', ' ')}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} className="btn-ghost text-xs">Cancel</button>
          <button type="submit" disabled={loading} className="btn-primary text-xs">
            {loading && <Loader2 size={12} className="animate-spin" />}
            Submit request
          </button>
        </div>
      </form>
    </div>
  )
}

function WatchRequestCard({ request }) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Eye size={14} className="text-alexandria-500" />
            <span className={`badge text-xs ${request.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>
              {request.status}
            </span>
            {request.source_types && (
              <span className="badge bg-blue-50 text-blue-700 text-xs">{request.source_types}</span>
            )}
          </div>
          <p className="text-sm text-gray-800 leading-relaxed">{request.description}</p>
          {request.keywords && (
            <p className="text-xs text-gray-400 mt-2">
              Keywords: <span className="font-mono bg-gray-50 px-1 rounded">{request.keywords}</span>
            </p>
          )}
          <p className="text-xs text-gray-400 mt-2">
            Submitted {formatDistanceToNow(new Date(request.created_at), { addSuffix: true })}
          </p>
        </div>
      </div>
    </div>
  )
}

export default function WatchRequests() {
  const [showForm, setShowForm] = useState(false)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list().then(r => r.data),
  })

  const currentProject = projects[0]

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['watch-requests', currentProject?.id],
    queryFn: () => projectsApi.listWatchRequests(currentProject.id).then(r => r.data),
    enabled: !!currentProject,
  })

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Watch Requests</h1>
          <p className="text-sm text-gray-500 mt-1">
            Tell Alexandria what you're looking for. She'll keep an eye out when running monitors and reviews.
          </p>
        </div>
        <button onClick={() => setShowForm(v => !v)} className="btn-primary">
          <Plus size={15} />
          New request
        </button>
      </div>

      <div className="bg-alexandria-50 border border-alexandria-100 rounded-xl p-4 mb-6">
        <p className="text-sm text-alexandria-800 leading-relaxed">
          <strong>How it works:</strong> Describe what you need in plain language. Alexandria will use your watch requests to inform what she flags during proactive searches and to tune monitor results to your research interests.
        </p>
      </div>

      {showForm && currentProject && (
        <WatchRequestForm projectId={currentProject.id} onClose={() => setShowForm(false)} />
      )}

      {!currentProject ? (
        <div className="text-center py-12 text-gray-400">Create a project first to add watch requests.</div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-gray-300" /></div>
      ) : requests.length === 0 ? (
        <div className="text-center py-16">
          <Eye size={32} className="text-gray-200 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">No watch requests yet</p>
          <p className="text-gray-400 text-sm mt-1">Tell Alexandria what types of papers and resources to look out for.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map(r => <WatchRequestCard key={r.id} request={r} />)}
        </div>
      )}
    </div>
  )
}
