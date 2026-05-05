import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { projectsApi } from '../api/client'
import { Eye, Plus, Loader2, Trash2, Radio } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'

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
      queryClient.invalidateQueries({ queryKey: ['monitors'] })
      toast.success('Watch request created — a weekly monitor has been set up automatically')
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
            placeholder="e.g. Papers on mechanistic interpretability of large language models, especially work using sparse autoencoders."
          />
          <p className="text-xs text-gray-400 mt-1">
            Write naturally. A weekly monitor will be created automatically using your keywords below.
          </p>
        </div>
        <div>
          <label className="label">Search keywords <span className="text-gray-400 font-normal">(used for the automated monitor)</span></label>
          <input
            className="input"
            value={form.keywords}
            onChange={e => setForm(f => ({ ...f, keywords: e.target.value }))}
            placeholder="e.g. mechanistic interpretability sparse autoencoder"
          />
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

function WatchRequestCard({ request, projectId }) {
  const [deleting, setDeleting] = useState(false)
  const queryClient = useQueryClient()

  const del = async () => {
    if (!confirm('Remove this watch request?')) return
    setDeleting(true)
    try {
      await projectsApi.deleteWatchRequest(projectId, request.id)
      queryClient.invalidateQueries({ queryKey: ['watch-requests', projectId] })
      toast.success('Watch request removed')
    } catch {
      toast.error('Failed to remove')
    } finally {
      setDeleting(false)
    }
  }

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
            <span className="text-xs text-gray-400 ml-auto">
              {formatDistanceToNow(new Date(request.created_at), { addSuffix: true })}
            </span>
          </div>
          <p className="text-sm text-gray-800 leading-relaxed">{request.description}</p>
          {request.keywords && (
            <p className="text-xs text-gray-400 mt-2">
              Monitor keywords: <span className="font-mono bg-gray-50 px-1 rounded">{request.keywords}</span>
            </p>
          )}
          <p className="text-xs text-gray-400 mt-1 flex items-center gap-1">
            <Radio size={10} className="text-emerald-400" />
            Weekly monitor created automatically
          </p>
        </div>
        <button
          onClick={del}
          disabled={deleting}
          className="text-gray-300 hover:text-red-400 transition-colors flex-shrink-0"
          title="Remove watch request"
        >
          {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
        </button>
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
            Tell Alexandria what you're looking for — a search monitor is created automatically.
          </p>
        </div>
        <button onClick={() => setShowForm(v => !v)} className="btn-primary">
          <Plus size={15} />New request
        </button>
      </div>

      {/* Explain the difference */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-blue-50 border border-blue-100 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <Eye size={14} className="text-blue-600" />
            <span className="text-sm font-semibold text-blue-800">Watch Requests</span>
          </div>
          <p className="text-xs text-blue-700 leading-relaxed">
            Describe what you need in plain language. Creates a monitor automatically.
            Alexandria also uses these when answering your chat questions.
          </p>
        </div>
        <div className="bg-emerald-50 border border-emerald-100 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-1">
            <Radio size={14} className="text-emerald-600" />
            <span className="text-sm font-semibold text-emerald-800">Monitors</span>
          </div>
          <p className="text-xs text-emerald-700 leading-relaxed">
            Automated scheduled searches (weekly/daily) across arXiv, OpenAlex, web.
            Results go to the Review Queue for your approval.
          </p>
        </div>
      </div>

      {showForm && currentProject && (
        <WatchRequestForm projectId={currentProject.id} onClose={() => setShowForm(false)} />
      )}

      {!currentProject ? (
        <div className="text-center py-12 text-gray-400">Create a project first.</div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-16"><Loader2 size={24} className="animate-spin text-gray-300" /></div>
      ) : requests.length === 0 ? (
        <div className="text-center py-16">
          <Eye size={32} className="text-gray-200 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">No watch requests yet</p>
          <p className="text-gray-400 text-sm mt-1">Describe what Alexandria should look out for.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map(r => <WatchRequestCard key={r.id} request={r} projectId={currentProject.id} />)}
        </div>
      )}
    </div>
  )
}
