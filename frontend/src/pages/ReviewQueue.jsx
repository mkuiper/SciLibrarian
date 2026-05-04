import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { reviewApi } from '../api/client'
import { Check, X, ExternalLink, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'

const STATUS_TABS = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
]

function QueueItem({ item, onDecide }) {
  const [loading, setLoading] = useState(false)

  const decide = async (action) => {
    setLoading(action)
    await onDecide(item.id, action)
    setLoading(false)
  }

  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="badge bg-gray-100 text-gray-600 text-xs">{item.source}</span>
            {item.year && <span className="text-xs text-gray-400">{item.year}</span>}
          </div>
          <h3 className="text-sm font-semibold text-gray-900 line-clamp-2">{item.title}</h3>
          {item.authors && <p className="text-xs text-gray-500 mt-1">{item.authors}</p>}
          {item.abstract && <p className="text-xs text-gray-500 mt-2 line-clamp-3 leading-relaxed">{item.abstract}</p>}
          <p className="text-xs text-gray-400 mt-2">
            Found {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
            {item.search_query && ` · query: "${item.search_query}"`}
          </p>
        </div>

        <div className="flex flex-col gap-2">
          {item.url && (
            <a href={item.url} target="_blank" rel="noopener noreferrer" className="btn-ghost p-2">
              <ExternalLink size={14} />
            </a>
          )}
          {item.status === 'pending' && (
            <>
              <button
                onClick={() => decide('approve')}
                disabled={!!loading}
                className="w-9 h-9 flex items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 hover:bg-emerald-100 transition-colors disabled:opacity-50"
                title="Approve — add to library"
              >
                {loading === 'approve' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
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
        </div>
      </div>
    </div>
  )
}

export default function ReviewQueue() {
  const [status, setStatus] = useState('pending')
  const queryClient = useQueryClient()

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['review-queue', status],
    queryFn: () => reviewApi.getQueue({ status, limit: 50 }).then(r => r.data),
  })

  const handleDecide = async (itemId, action) => {
    try {
      await reviewApi.decide(itemId, { action })
      queryClient.invalidateQueries({ queryKey: ['review-queue'] })
      toast.success(action === 'approve' ? 'Added to library' : 'Item rejected')
    } catch {
      toast.error('Failed to update item')
    }
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Review Queue</h1>
        <p className="text-sm text-gray-500 mt-1">
          Items discovered by Alexandria's monitors, waiting for your approval before entering the library.
        </p>
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
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-gray-300" />
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-500 font-medium">No {status} items</p>
          <p className="text-gray-400 text-sm mt-1">
            {status === 'pending' ? 'Run a monitor to find new references' : 'Nothing here yet'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map(item => (
            <QueueItem key={item.id} item={item} onDecide={handleDecide} />
          ))}
        </div>
      )}
    </div>
  )
}
