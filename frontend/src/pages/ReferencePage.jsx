import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { referencesApi, collectionsApi } from '../api/client'
import { ArrowLeft, ExternalLink, FileText, Trash2, Loader2, Copy, Download, ChevronDown, ChevronUp, Pencil, Check, X, Star, Eye, Clock, CheckCircle, StickyNote } from 'lucide-react'
import toast from 'react-hot-toast'

const TYPE_COLORS = {
  paper:       'bg-blue-50 text-blue-700',
  policy:      'bg-purple-50 text-purple-700',
  model_card:  'bg-emerald-50 text-emerald-700',
  evaluation:  'bg-amber-50 text-amber-700',
  government:  'bg-red-50 text-red-700',
  other:       'bg-gray-100 text-gray-600',
}

function PdfViewer({ refId }) {
  const [blobUrl, setBlobUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const token = localStorage.getItem('token')
      const resp = await fetch(referencesApi.fileUrl(refId), {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) throw new Error(`Server returned ${resp.status}`)
      const blob = await resp.blob()
      setBlobUrl(URL.createObjectURL(blob))
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const close = () => {
    if (blobUrl) URL.revokeObjectURL(blobUrl)
    setBlobUrl(null)
  }

  if (!blobUrl && !loading) {
    return (
      <button onClick={load} className="btn-secondary text-xs">
        <FileText size={13} />
        View PDF
      </button>
    )
  }

  if (loading) {
    return (
      <button disabled className="btn-secondary text-xs opacity-60">
        <Loader2 size={13} className="animate-spin" />
        Loading...
      </button>
    )
  }

  if (error) {
    return <p className="text-xs text-red-500">Could not load PDF: {error}</p>
  }

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">PDF Viewer</h2>
        <button onClick={close} className="text-xs text-gray-400 hover:text-gray-600">Hide</button>
      </div>
      <iframe
        src={`${blobUrl}#toolbar=1&view=FitH`}
        className="w-full rounded-xl border border-gray-200"
        style={{ height: '72vh' }}
        title="PDF viewer"
      />
    </div>
  )
}

function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy} className="btn-ghost text-xs gap-1.5">
      <Copy size={12} />
      {copied ? 'Copied!' : label}
    </button>
  )
}

function plainCitation(ref) {
  const authors = ref.authors || 'Unknown'
  const year = ref.year || 'n.d.'
  const url = ref.url ? ` ${ref.url}` : ''
  return `${authors} (${year}). ${ref.title}.${url}`
}

const SOURCE_TYPES = ['paper', 'policy', 'model_card', 'evaluation', 'government', 'news', 'other']

function TagEditor({ tags, onSave }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(tags.join(', '))

  const save = async () => {
    const newTags = draft.split(',').map(t => t.trim().toLowerCase()).filter(Boolean)
    await onSave(newTags)
    setEditing(false)
  }

  if (!editing) return (
    <div className="group flex items-center gap-1 flex-wrap">
      {tags.length > 0
        ? tags.map(t => <span key={t} className="badge bg-gray-100 text-gray-600">{t}</span>)
        : <span className="text-gray-300 italic text-xs">No tags</span>
      }
      <button onClick={() => { setDraft(tags.join(', ')); setEditing(true) }}
        className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-300 hover:text-gray-500 ml-1">
        <Pencil size={11} />
      </button>
    </div>
  )

  return (
    <div>
      <input
        className="input text-sm"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        placeholder="tag1, tag2, tag3"
        autoFocus
        onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') setEditing(false) }}
      />
      <p className="text-xs text-gray-400 mt-1">Comma-separated tags</p>
      <div className="flex gap-1 mt-2">
        <button onClick={save} className="btn-primary text-xs py-1 px-2"><Check size={11} /> Save</button>
        <button onClick={() => setEditing(false)} className="btn-ghost text-xs py-1 px-2"><X size={11} /> Cancel</button>
      </div>
    </div>
  )
}

function InlineEdit({ value, onSave, multiline = false, className = '' }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value || '')

  const save = async () => {
    if (draft !== value) await onSave(draft)
    setEditing(false)
  }
  const cancel = () => { setDraft(value || ''); setEditing(false) }

  if (!editing) return (
    <div className={`group flex items-start gap-1 ${className}`}>
      <span className="flex-1">{value || <span className="text-gray-300 italic">Not set</span>}</span>
      <button onClick={() => setEditing(true)} className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-300 hover:text-gray-500 flex-shrink-0">
        <Pencil size={11} />
      </button>
    </div>
  )

  return (
    <div className={className}>
      {multiline ? (
        <textarea
          className="input text-sm w-full"
          rows={4}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          autoFocus
        />
      ) : (
        <input
          className="input text-sm"
          value={draft}
          onChange={e => setDraft(e.target.value)}
          autoFocus
          onKeyDown={e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') cancel() }}
        />
      )}
      <div className="flex gap-1 mt-1">
        <button onClick={save} className="btn-primary text-xs py-1 px-2"><Check size={11} /> Save</button>
        <button onClick={cancel} className="btn-ghost text-xs py-1 px-2"><X size={11} /> Cancel</button>
      </div>
    </div>
  )
}

export default function ReferencePage() {
  const { refId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showFullText, setShowFullText] = useState(false)

  const { data: ref, isLoading } = useQuery({
    queryKey: ['reference', refId],
    queryFn: () => referencesApi.get(refId).then(r => r.data),
  })

  const { data: collections = [] } = useQuery({
    queryKey: ['collections-flat'],
    queryFn: () => collectionsApi.list().then(r => r.data),
  })

  const update = async (field, value) => {
    try {
      await referencesApi.update(refId, { [field]: value })
      queryClient.invalidateQueries({ queryKey: ['reference', refId] })
      queryClient.invalidateQueries({ queryKey: ['references'] })
      toast.success('Updated')
    } catch {
      toast.error('Failed to update')
    }
  }

  const handleDelete = async () => {
    if (!confirm('Delete this reference?')) return
    try {
      await referencesApi.delete(refId)
      queryClient.invalidateQueries({ queryKey: ['references'] })
      toast.success('Reference deleted')
      navigate('/library')
    } catch {
      toast.error('Failed to delete')
    }
  }

  if (isLoading) return (
    <div className="flex items-center justify-center py-24">
      <Loader2 size={24} className="animate-spin text-gray-300" />
    </div>
  )

  if (!ref) return <div className="p-8 text-center text-gray-400">Reference not found</div>

  const hasPdf = !!ref.file_name

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <button onClick={() => navigate(-1)} className="btn-ghost mb-6 -ml-2 text-gray-500">
        <ArrowLeft size={15} />
        Back
      </button>

      <div className="card p-8">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <select
                value={ref.source_type}
                onChange={e => update('source_type', e.target.value)}
                className={`badge text-xs cursor-pointer border-0 bg-transparent focus:outline-none ${TYPE_COLORS[ref.source_type] || TYPE_COLORS.other}`}
              >
                {SOURCE_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
              </select>
              <InlineEdit
                value={String(ref.year || '')}
                onSave={v => update('year', v ? parseInt(v) : null)}
                className="text-sm text-gray-400 w-16"
              />
            </div>
            <InlineEdit
              value={ref.title}
              onSave={v => update('title', v)}
              className="text-xl font-bold text-gray-900 leading-tight mb-1"
            />
            <InlineEdit
              value={ref.authors || ''}
              onSave={v => update('authors', v)}
              className="text-sm text-gray-500 mt-1"
            />
            {/* Collection assignment */}
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-gray-400">Collection:</span>
              <select
                value={ref.collection_id || ''}
                onChange={e => update('collection_id', e.target.value ? parseInt(e.target.value) : null)}
                className="text-xs border border-gray-200 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-alexandria-400"
              >
                <option value="">Uncategorised</option>
                {collections.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-2 flex-shrink-0">
            {hasPdf && <PdfViewer refId={ref.id} />}
            {ref.url && (
              <a href={ref.url} target="_blank" rel="noopener noreferrer" className="btn-secondary">
                <ExternalLink size={14} />
                Open
              </a>
            )}
            <button onClick={handleDelete} className="btn-ghost text-red-400 hover:text-red-600">
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {/* Star / Read status */}
        <div className="flex items-center gap-2 mb-5 pb-4 border-b border-gray-100">
          <button
            onClick={() => update('is_starred', !ref.is_starred)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border ${
              ref.is_starred ? 'bg-amber-50 text-amber-700 border-amber-300' : 'border-gray-200 text-gray-500 hover:border-amber-200'
            }`}
          >
            <Star size={14} fill={ref.is_starred ? 'currentColor' : 'none'} />
            {ref.is_starred ? 'Starred' : 'Star'}
          </button>

          {[
            { status: 'unread',  icon: Eye,          label: 'Unread',   color: 'text-gray-500' },
            { status: 'reading', icon: Clock,         label: 'Reading',  color: 'text-amber-600' },
            { status: 'read',    icon: CheckCircle,   label: 'Read',     color: 'text-emerald-600' },
          ].map(({ status, icon: Icon, label, color }) => (
            <button
              key={status}
              onClick={() => update('read_status', status)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors border ${
                ref.read_status === status
                  ? 'bg-gray-100 border-gray-300 ' + color
                  : 'border-gray-200 text-gray-400 hover:border-gray-300'
              }`}
            >
              <Icon size={14} />
              {label}
            </button>
          ))}
        </div>

        {/* Export / copy actions */}
        <div className="flex flex-wrap gap-1 mb-6 pb-4 border-b border-gray-100">
          <CopyButton text={plainCitation(ref)} label="Copy citation" />
          {hasPdf || ref.url ? (
            <a
              href={hasPdf ? referencesApi.bibtexUrl(ref.id) : '#'}
              download={hasPdf ? `${ref.id}.bib` : undefined}
              onClick={!hasPdf ? (e) => {
                e.preventDefault()
                // Generate bibtex on the fly from available data for URL references
                const bib = `@misc{${ref.id},\n  title = {${ref.title}},\n  author = {${ref.authors || 'Unknown'}},\n  year = {${ref.year || 'n.d.'}},\n  url = {${ref.url || ''}}\n}`
                navigator.clipboard.writeText(bib)
                toast.success('BibTeX copied to clipboard')
              } : undefined}
              className="btn-ghost text-xs gap-1.5"
            >
              <Download size={12} />
              BibTeX
            </a>
          ) : null}
          <CopyButton text={ref.title} label="Copy title" />
        </div>

        {/* Alexandria summary */}
        <div className="mb-6">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
            Alexandria's Summary
          </h2>
          <div className="bg-alexandria-50 border border-alexandria-100 rounded-xl p-4">
            <InlineEdit
              value={ref.summary || ''}
              onSave={v => update('summary', v)}
              multiline
              className="text-sm text-gray-700 leading-relaxed"
            />
          </div>
        </div>

        {/* Abstract */}
        <div className="mb-6">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Abstract</h2>
          <InlineEdit
            value={ref.abstract || ''}
            onSave={v => update('abstract', v)}
            multiline
            className="text-sm text-gray-600 leading-relaxed"
          />
        </div>

        {/* Tags — editable */}
        <div className="mb-6">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Tags</h2>
          <TagEditor
            tags={ref.tags?.map(t => t.tag) || []}
            onSave={tags => update('tags', tags)}
          />
        </div>

        {/* Extra metadata */}
        {ref.extra_metadata && Object.keys(ref.extra_metadata).length > 0 && (
          <div className="mb-6">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Metadata</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
              {Object.entries(ref.extra_metadata).map(([k, v]) => v ? (
                <div key={k}>
                  <dt className="text-xs text-gray-400 capitalize">{k.replace(/_/g, ' ')}</dt>
                  <dd className="text-sm text-gray-700 break-all">{String(v)}</dd>
                </div>
              ) : null)}
            </dl>
          </div>
        )}

        {/* Personal notes */}
        <div className="mb-6">
          <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
            <StickyNote size={11} />
            My Notes
          </h2>
          <InlineEdit
            value={ref.notes || ''}
            onSave={v => update('notes', v || null)}
            multiline
            className="text-sm text-gray-700 leading-relaxed bg-yellow-50 border border-yellow-100 rounded-xl p-3 min-h-[60px]"
          />
          {!ref.notes && <p className="text-xs text-gray-400 mt-1">Click to add personal notes about this reference</p>}
        </div>

        {/* Full text (collapsible) */}
        {ref.full_text && (
          <div className="mb-6">
            <button
              onClick={() => setShowFullText(v => !v)}
              className="flex items-center gap-1.5 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:text-gray-600 transition-colors"
            >
              {showFullText ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              Extracted text {showFullText ? '(hide)' : '(show)'}
            </button>
            {showFullText && (
              <div className="mt-2 max-h-64 overflow-y-auto bg-gray-50 rounded-xl p-4 border border-gray-100">
                <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed">
                  {ref.full_text}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* PDF viewer (embedded) */}
        {hasPdf && <PdfViewer refId={ref.id} />}

        <div className="mt-6 pt-6 border-t border-gray-100 text-xs text-gray-400">
          Added {new Date(ref.created_at).toLocaleDateString('en-AU', { year: 'numeric', month: 'long', day: 'numeric' })}
          {ref.file_name && ` · ${ref.file_name}`}
        </div>
      </div>
    </div>
  )
}
