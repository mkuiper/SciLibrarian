import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { referencesApi } from '../api/client'
import { FileText, Globe, Shield, Cpu, ClipboardList, Newspaper, ExternalLink, Star, Eye, CheckCircle, Clock } from 'lucide-react'
import clsx from 'clsx'

const TYPE_CONFIG = {
  paper:       { icon: FileText,      color: 'bg-blue-50 text-blue-700',      label: 'Paper' },
  policy:      { icon: Shield,        color: 'bg-purple-50 text-purple-700',  label: 'Policy' },
  model_card:  { icon: Cpu,           color: 'bg-emerald-50 text-emerald-700',label: 'Model Card' },
  evaluation:  { icon: ClipboardList, color: 'bg-amber-50 text-amber-700',    label: 'Evaluation' },
  government:  { icon: Shield,        color: 'bg-red-50 text-red-700',        label: 'Government' },
  news:        { icon: Newspaper,     color: 'bg-gray-50 text-gray-600',      label: 'News' },
  other:       { icon: Globe,         color: 'bg-gray-50 text-gray-600',      label: 'Other' },
}

const READ_CONFIG = {
  unread:  { icon: Eye,          color: 'text-gray-300',       next: 'reading', label: 'Mark as reading' },
  reading: { icon: Clock,        color: 'text-amber-400',      next: 'read',    label: 'Mark as read' },
  read:    { icon: CheckCircle,  color: 'text-emerald-500',    next: 'unread',  label: 'Mark as unread' },
}

export default function ReferenceCard({ reference: r, showControls = true }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [optimisticStarred, setOptimisticStarred] = useState(null)
  const [optimisticRead, setOptimisticRead] = useState(null)

  const isStarred = optimisticStarred ?? r.is_starred
  const readStatus = optimisticRead ?? r.read_status

  const config = TYPE_CONFIG[r.source_type] || TYPE_CONFIG.other
  const Icon = config.icon
  const readCfg = READ_CONFIG[readStatus] || READ_CONFIG.unread
  const ReadIcon = readCfg.icon

  const toggleStar = async (e) => {
    e.stopPropagation()
    setOptimisticStarred(!isStarred)
    try {
      await referencesApi.update(r.id, { is_starred: !isStarred })
      queryClient.invalidateQueries({ queryKey: ['references'] })
    } catch {
      setOptimisticStarred(isStarred) // revert
    }
  }

  const cycleRead = async (e) => {
    e.stopPropagation()
    const next = readCfg.next
    setOptimisticRead(next)
    try {
      await referencesApi.update(r.id, { read_status: next })
      queryClient.invalidateQueries({ queryKey: ['references'] })
    } catch {
      setOptimisticRead(readStatus) // revert
    }
  }

  return (
    <div
      className={clsx(
        'card p-4 hover:shadow-md transition-all cursor-pointer group',
        readStatus === 'read' && 'opacity-70',
      )}
      onClick={() => navigate(`/references/${r.id}`)}
    >
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={clsx('badge text-xs', config.color)}>
              <Icon size={9} className="mr-1" />
              {config.label}
            </span>
            {r.year && <span className="text-xs text-gray-400">{r.year}</span>}
            {readStatus === 'read' && (
              <span className="badge bg-emerald-50 text-emerald-600 text-xs">read</span>
            )}
            {readStatus === 'reading' && (
              <span className="badge bg-amber-50 text-amber-600 text-xs">reading</span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-gray-900 group-hover:text-alexandria-700 transition-colors line-clamp-2">
            {r.title}
          </h3>
          {r.authors && (
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{r.authors}</p>
          )}
          {r.summary && (
            <p className="text-xs text-gray-500 mt-1.5 line-clamp-2 leading-relaxed">{r.summary}</p>
          )}
          {r.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {r.tags.slice(0, 4).map(t => (
                <span key={t.tag} className="badge bg-gray-100 text-gray-500 text-xs">{t.tag}</span>
              ))}
              {r.tags.length > 4 && <span className="text-xs text-gray-400">+{r.tags.length - 4}</span>}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-col items-center gap-1.5 flex-shrink-0">
          {showControls && (
            <>
              <button
                onClick={toggleStar}
                title={isStarred ? 'Unstar' : 'Star'}
                className={clsx(
                  'p-1 rounded transition-colors',
                  isStarred ? 'text-amber-400 hover:text-amber-500' : 'text-gray-200 hover:text-amber-400'
                )}
              >
                <Star size={14} fill={isStarred ? 'currentColor' : 'none'} />
              </button>
              <button
                onClick={cycleRead}
                title={readCfg.label}
                className={clsx('p-1 rounded transition-colors', readCfg.color, 'hover:opacity-80')}
              >
                <ReadIcon size={14} />
              </button>
            </>
          )}
          {r.url && (
            <a
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="p-1 text-gray-200 hover:text-alexandria-500 transition-colors"
              title="Open source"
            >
              <ExternalLink size={14} />
            </a>
          )}
        </div>
      </div>
    </div>
  )
}
