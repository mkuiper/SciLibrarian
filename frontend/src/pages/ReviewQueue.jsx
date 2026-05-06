import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { reviewApi, collectionsApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import { Check, X, ExternalLink, Loader2, CheckCheck, XCircle, Inbox, Sparkles, Zap } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'

const STATUS_TABS = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

function QueueItem({ item, onDecide, collections, fullIngest }) {
  const [loading, setLoading] = useState(false)
  const [targetCollection, setTargetCollection] = useState('')

  const decide = async (action) => {
    setLoading(action)
    await onDecide(item.id, action, targetCollection ? parseInt(targetCollection) : null, fullIngest)
    setLoading(false)
  }

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <span className="badge bg-gray-100 text-gray-600 text-xs">{item.source}</span>
            {item.year && <span className="text-xs text-gray-400">{item.year}</span>}
            {item.search_query && (
              <span className="text-xs text-gray-400 italic">via "{item.search_query}"</span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-gray-900 line-clamp-2">{item.title}</h3>
          {item.authors && <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{item.authors}</p>}
          {item.abstract && <p className="text-xs text-gray-500 mt-2 line-clamp-3 leading-relaxed">{item.abstract}</p>}
          <p className="text-xs text-gray-400 mt-2">
            Found {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
          </p>
        </div>

        <div className="flex flex-col gap-2 flex-shrink-0">
          {item.url && (
            <a href={item.url} target="_blank" rel="noopener noreferrer" className="btn-ghost p-2" title="Open source">
              <ExternalLink size={14} />
            </a>
          )}
          {item.status === 'pending' && (
            <>
              <select
                value={targetCollection}
                onChange={e => setTargetCollection(e.target.value)}
                className="text-xs border border-gray-200 rounded-lg px-1.5 py-1 w-32 focus:outline-none focus:ring-1 focus:ring-alexandria-400"
                title="Add to collection (optional)"
              >
                <option value="">No collection</option>
                {collections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
              <button
                onClick={() => decide('approve')}
                disabled={!!loading}
                className="w-9 h-9 flex items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors disabled:opacity-50"
                title={fullIngest ? "Approve with full ingestion (Alexandria will summarise)" : "Approve — add basic metadata"}
              >
                {loading === 'approve' ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : fullIngest ? (
                  <Sparkles size={14} />
                ) : (
                  <Check size={14} />
                )}
              </button>
              <button
                onClick={() => decide('reject')}
                disabled={!!loading}
                className="w-9 h-9 flex items-center justify-center rounded-lg bg-red-50 text-red-400 hover:bg-red-100 transition-colors disabled:opacity-50"
                title="Reject"
              >
                {loading === 'reject' ? <Loader2 size={14} className="animate-spin" /> : <X size={14} />}
              </button>
            </>
          )}
          {item.status === 'approved' && <span className="badge bg-emerald-50 text-emerald-700 text-xs">approved</span>}
          {item.status === 'rejected' && <span className="badge bg-red-50 text-red-400 text-xs">rejected</span>}
        </div>
      </div>
    </div>
  )
}

export default function ReviewQueue() {
  const [status, setStatus] = useState('pending')
  const [bulkLoading, setBulkLoading] = useState(false)
  const [fullIngest, setFullIngest] = useState(true)
  const queryClient = useQueryClient()
  const { projectId } = useProject()

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['review-queue', status, projectId],
    queryFn: () => reviewApi.getQueue({ status, project_id: projectId, limit: 100 }).then(r => r.data),
  })

  const { data: flatCollections = [] } = useQuery({
    queryKey: ['collections-flat', projectId],
    queryFn: () => collectionsApi.list(projectId).then(r => r.data),
  })

  const handleDecide = async (itemId, action, collectionId = null, doFullIngest = true) => {
    try {
      await reviewApi.decide(itemId, {
        action,
        collection_id: collectionId,
        full_ingest: doFullIngest && action === 'approve',
      })
      queryClient.invalidateQueries({ queryKey: ['review-queue'] })
      queryClient.invalidateQueries({ queryKey: ['ref-stats'] })
      queryClient.invalidateQueries({ queryKey: ['references'] })
      toast.success(
        action === 'approve'
          ? doFullIngest ? 'Added and fully processed by Alexandria' : 'Added to library'
          : 'Item rejected'
      )
    } catch {
      toast.error('Failed to update item')
    }
  }

  const bulkApprove = async () => {
    if (!items.length) return
    const label = fullIngest ? 'fully process and approve' : 'approve'
    if (!confirm(`${label.charAt(0).toUpperCase() + label.slice(1)} all ${items.length} pending items?\n${fullIngest ? '\nNote: full ingestion may take a few minutes.' : ''}`)) return
    setBulkLoading(true)
    let approved = 0
    for (const item of items) {
      try {
        await reviewApi.decide(item.id, { action: 'approve', full_ingest: fullIngest })
        approved++
      } catch {}
    }
    queryClient.invalidateQueries({ queryKey: ['review-queue'] })
    queryClient.invalidateQueries({ queryKey: ['ref-stats'] })
    queryClient.invalidateQueries({ queryKey: ['references'] })
    toast.success(`Approved ${approved} items`)
    setBulkLoading(false)
  }

  const bulkReject = async () => {
    if (!items.length) return
    if (!confirm(`Reject all ${items.length} pending items?`)) return
    setBulkLoading(true)
    let rejected = 0
    for (const item of items) {
      try {
        await reviewApi.decide(item.id, { action: 'reject', full_ingest: false })
        rejected++
      } catch {}
    }
    queryClient.invalidateQueries({ queryKey: ['review-queue'] })
    toast.success(`Rejected ${rejected} items`)
    setBulkLoading(false)
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Review Queue</h1>
          <p className="text-sm text-gray-500 mt-1">
            Discoveries from Alexandria's monitors — approve to add to library, reject to discard.
          </p>
        </div>
        {status === 'pending' && items.length > 0 && (
          <div className="flex gap-2">
            <button onClick={bulkReject} disabled={bulkLoading} className="btn-secondary text-xs gap-1.5">
              {bulkLoading ? <Loader2 size={12} className="animate-spin" /> : <XCircle size={12} />}
              Reject all
            </button>
            <button
              onClick={bulkApprove}
              disabled={bulkLoading}
              className="btn-primary text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700"
            >
              {bulkLoading ? <Loader2 size={12} className="animate-spin" /> : <CheckCheck size={12} />}
              Approve all
            </button>
          </div>
        )}
      </div>

      {/* Full ingest toggle */}
      <div className={`flex items-start gap-3 rounded-xl p-4 mb-5 border ${fullIngest ? 'bg-alexandria-50 border-alexandria-200' : 'bg-gray-50 border-gray-200'}`}>
        <button
          onClick={() => setFullIngest(v => !v)}
          className={`flex-shrink-0 w-10 h-6 rounded-full transition-colors relative mt-0.5 ${fullIngest ? 'bg-alexandria-600' : 'bg-gray-300'}`}
        >
          <span className={`absolute top-1 w-4 h-4 bg-white rounded-full shadow transition-all ${fullIngest ? 'left-5' : 'left-1'}`} />
        </button>
        <div>
          <div className="flex items-center gap-1.5">
            <Sparkles size={14} className={fullIngest ? 'text-alexandria-600' : 'text-gray-400'} />
            <span className={`text-sm font-medium ${fullIngest ? 'text-alexandria-800' : 'text-gray-600'}`}>
              Full ingestion on approve
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">
            {fullIngest
              ? 'Alexandria will fetch the full page, extract text, and generate a proper summary and tags — same as a manual upload. Takes 15–30s per item.'
              : 'Items are added with the scraped title/abstract only. Faster but less detailed.'}
          </p>
        </div>
      </div>

      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6 w-fit">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setStatus(tab.value)}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-all ${
              status === tab.value ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
            {tab.value === 'pending' && items.length > 0 && status !== 'pending' && (
              <span className="ml-1.5 bg-amber-100 text-amber-700 text-xs px-1.5 py-0.5 rounded-full">{items.length}</span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-gray-300" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16">
          <Inbox size={32} className="text-gray-200 mx-auto mb-3" />
          <p className="text-gray-500 font-medium">No {status} items</p>
          <p className="text-gray-400 text-sm mt-1">
            {status === 'pending' ? 'Run a monitor to find new references.' : 'Nothing here yet.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <QueueItem
              key={item.id}
              item={item}
              onDecide={handleDecide}
              collections={flatCollections}
              fullIngest={fullIngest}
            />
          ))}
        </div>
      )}
    </div>
  )
}
