import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { referencesApi } from '../api/client'
import { FileText, Globe, Shield, Cpu, ClipboardList, Newspaper, ExternalLink, Star, Eye, CheckCircle, Clock, Bookmark } from 'lucide-react'
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

// Cycle: unread → reading → read → important → unread
const READ_CONFIG = {
  unread:    { icon: Eye,         color: 'text-gray-300',       next: 'reading',   label: 'Mark as reading' },
  reading:   { icon: Clock,       color: 'text-amber-400',      next: 'read',      label: 'Mark as read' },
  read:      { icon: CheckCircle, color: 'text-emerald-500',    next: 'important', label: 'Mark as important' },
  important: { icon: Bookmark,    color: 'text-alexandria-600', next: 'unread',    label: 'Clear status' },
  flagged:   { icon: Bookmark,    color: 'text-red-400',        next: 'unread',    label: 'Clear status' },
}

const STATUS_BADGE = {
  read:      'badge bg-emerald-50 text-emerald-600 text-xs',
  reading:   'badge bg-amber-50 text-amber-600 text-xs',
  important: 'badge bg-alexandria-50 text-alexandria-700 text-xs',
  flagged:   'badge bg-red-50 text-red-600 text-xs',
}

export default function ReferenceCard({ reference: r, showControls = true, snippet, selectable = false, selected = false, onToggleSelect }) {
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
      setOptimisticStarred(isStarred)
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
      setOptimisticRead(readStatus)
    }
  }

  // Show snippet (from FTS) if provided, otherwise show summary
  const bodyText = snippet || r.summary

  const handleCardClick = () => {
    if (selectable && onToggleSelect) {
      onToggleSelect(r.id)
    } else {
      navigate(`/references/${r.id}`)
    }
  }

  return (
    <div
      className={clsx(
        'card p-4 hover:shadow-md transition-all cursor-pointer group',
        readStatus === 'read' && !selected && 'opacity-70',
        selected && 'ring-2 ring-alexandria-400 bg-alexandria-50/30',
      )}
      onClick={handleCardClick}
    >
      <div className="flex items-start gap-3">
        {selectable && (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect?.(r.id)}
            onClick={(e) => e.stopPropagation()}
            className="mt-1 accent-alexandria-500 shrink-0"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className={clsx('badge text-xs', config.color)}>
              <Icon size={9} className="mr-1" />
              {config.label}
            </span>
            {r.year && <span className="text-xs text-gray-400">{r.year}</span>}
            {STATUS_BADGE[readStatus] && (
              <span className={STATUS_BADGE[readStatus]}>{readStatus}</span>
            )}
          </div>
          <h3 className="text-sm font-semibold text-gray-900 group-hover:text-alexandria-700 transition-colors line-clamp-2">
            {r.title}
          </h3>
          {r.authors && (
            <p className="text-xs text-gray-500 mt-0.5 line-clamp-1">{r.authors}</p>
          )}
          {bodyText && (
            <p className={clsx(
              'text-xs text-gray-500 mt-1.5 line-clamp-2 leading-relaxed',
              snippet && 'italic text-gray-600'
            )}>
              {bodyText}
            </p>
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
