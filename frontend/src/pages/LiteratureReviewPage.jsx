import { Children, cloneElement, isValidElement, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import { projectsApi, referencesApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import { BookOpen, RefreshCw, Loader2, History, ChevronDown, ChevronUp } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'

function CitationLink({ refId, refTitleMap }) {
  const title = refTitleMap[refId]
  return (
    <Link
      to={`/references/${refId}`}
      className="inline-block bg-alexandria-50 text-alexandria-700 hover:bg-alexandria-100 rounded px-1.5 py-0 text-xs font-mono no-underline"
      title={title || `Reference ${refId}`}
    >
      [{refId}]
    </Link>
  )
}

/**
 * Walk every string in a React-Markdown children tree and replace `[id]` tokens
 * with CitationLink elements. Works inside paragraphs, list items, headings,
 * bold, italic, and any other inline element — the critical-review pass for
 * Cycle 20 flagged that the previous components-override approach silently
 * dropped citations nested inside formatting nodes.
 */
function linkifyCitations(node, refTitleMap, keyPrefix = 'c') {
  if (node == null || typeof node === 'boolean') return node
  if (typeof node === 'number') return node
  if (typeof node === 'string') {
    const regex = /\[(\d+)\]/g
    const parts = []
    let lastIndex = 0
    let match
    let idx = 0
    while ((match = regex.exec(node)) !== null) {
      if (match.index > lastIndex) {
        parts.push(<span key={`${keyPrefix}-${idx++}`}>{node.slice(lastIndex, match.index)}</span>)
      }
      parts.push(
        <CitationLink key={`${keyPrefix}-${idx++}`} refId={Number(match[1])} refTitleMap={refTitleMap} />,
      )
      lastIndex = regex.lastIndex
    }
    if (parts.length === 0) return node
    if (lastIndex < node.length) {
      parts.push(<span key={`${keyPrefix}-${idx++}`}>{node.slice(lastIndex)}</span>)
    }
    return parts
  }
  if (Array.isArray(node)) {
    return node.map((child, i) => linkifyCitations(child, refTitleMap, `${keyPrefix}-${i}`))
  }
  if (isValidElement(node)) {
    if (node.props?.children == null) return node
    return cloneElement(
      node,
      { ...node.props },
      linkifyCitations(node.props.children, refTitleMap, `${keyPrefix}-e`),
    )
  }
  return node
}

function withCitations(Component, refTitleMap) {
  return function CitationsWrap({ children, ...rest }) {
    return <Component {...rest}>{linkifyCitations(children, refTitleMap)}</Component>
  }
}

export default function LiteratureReviewPage() {
  const { projectId } = useProject()
  const queryClient = useQueryClient()
  const [generating, setGenerating] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  const { data: review, isLoading, error } = useQuery({
    queryKey: ['literature-review', projectId],
    queryFn: () => projectsApi.getLiteratureReview(projectId).then(r => r.data),
    enabled: !!projectId,
    retry: false,
  })

  const { data: historyData } = useQuery({
    queryKey: ['literature-review-history', projectId],
    queryFn: () => projectsApi.literatureReviewHistory(projectId).then(r => r.data),
    enabled: !!projectId && showHistory,
  })

  // Resolve cited reference IDs to titles via the batch endpoint for nicer hovers
  const citedIds = review?.cited_reference_ids || []
  const { data: citedRefs } = useQuery({
    queryKey: ['cited-refs', projectId, citedIds.join(',')],
    queryFn: () => referencesApi.batch(citedIds.slice(0, 50), projectId).then(r => r.data),
    enabled: !!projectId && citedIds.length > 0,
  })
  const refTitleMap = useMemo(
    () => Object.fromEntries((citedRefs || []).map(r => [r.id, r.title])),
    [citedRefs],
  )

  const generate = async () => {
    if (!projectId) return
    setGenerating(true)
    try {
      await projectsApi.generateLiteratureReview(projectId)
      queryClient.invalidateQueries({ queryKey: ['literature-review', projectId] })
      queryClient.invalidateQueries({ queryKey: ['literature-review-history', projectId] })
      toast.success('Literature review generated')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const notFound = !isLoading && error && error.response?.status === 404

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-10 h-10 rounded-xl bg-alexandria-50 flex items-center justify-center">
          <BookOpen size={18} className="text-alexandria-600" />
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-bold text-gray-900">Living literature review</h1>
          <p className="text-sm text-gray-500">
            Whole-library synthesis — themes, methods, consensus, gaps, must-reads
          </p>
        </div>
        <button onClick={generate} disabled={generating || !projectId} className="btn-primary text-sm">
          {generating ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          {review ? 'Regenerate' : 'Generate'}
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-gray-400 py-12 justify-center">
          <Loader2 size={18} className="animate-spin" />
          <span className="text-sm">Loading…</span>
        </div>
      )}

      {notFound && !generating && (
        <div className="card p-8 text-center text-gray-500">
          <BookOpen size={28} className="mx-auto mb-3 text-gray-300" />
          <p className="text-sm">No literature review generated yet for this project.</p>
          <p className="text-xs text-gray-400 mt-1">Click "Generate" above — Alexandria will synthesise the corpus.</p>
        </div>
      )}

      {generating && !review && (
        <div className="card p-8 text-center text-gray-500">
          <Loader2 size={22} className="mx-auto mb-3 animate-spin text-alexandria-500" />
          <p className="text-sm">Alexandria is reading and synthesising — this can take a minute or two.</p>
        </div>
      )}

      {review && (
        <>
          <div className="flex items-center gap-3 text-xs text-gray-400 mb-4">
            <span>Version {review.version}</span>
            <span>·</span>
            <span>Generated {formatDistanceToNow(new Date(review.created_at), { addSuffix: true })}</span>
            {review.model_used && (<><span>·</span><span className="font-mono">{review.model_used}</span></>)}
            {review.ref_count_at_generation > 0 && (
              <><span>·</span><span>{review.ref_count_at_generation} refs at generation</span></>
            )}
          </div>

          <div className="card p-6 prose prose-sm max-w-none prose-headings:font-semibold prose-headings:text-gray-900 prose-h2:text-base prose-h3:text-sm prose-p:text-sm prose-p:text-gray-700 prose-p:leading-relaxed">
            <ReactMarkdown
              components={{
                // Cover every node that can contain inline text where Alexandria
                // might cite refs. Citations inside ## headers or **bold** text
                // are common in the generated output and were dropping silently
                // before this pass.
                p: withCitations('p', refTitleMap),
                li: withCitations('li', refTitleMap),
                h1: withCitations('h1', refTitleMap),
                h2: withCitations('h2', refTitleMap),
                h3: withCitations('h3', refTitleMap),
                h4: withCitations('h4', refTitleMap),
                strong: withCitations('strong', refTitleMap),
                em: withCitations('em', refTitleMap),
                blockquote: withCitations('blockquote', refTitleMap),
              }}
            >
              {review.content}
            </ReactMarkdown>
          </div>

          <div className="mt-6">
            <button onClick={() => setShowHistory(v => !v)} className="btn-ghost text-xs gap-1.5">
              {showHistory ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              <History size={11} /> Version history
            </button>
            {showHistory && historyData?.entries?.length > 0 && (
              <ul className="mt-3 card divide-y divide-gray-50 px-4">
                {historyData.entries.map(entry => (
                  <li key={entry.id} className="py-2 flex items-center justify-between text-xs">
                    <span className="text-gray-700">
                      v{entry.version} <span className="text-gray-400 ml-2">{entry.ref_count_at_generation} refs</span>
                    </span>
                    <span className="text-gray-400">
                      {formatDistanceToNow(new Date(entry.created_at), { addSuffix: true })}
                      {entry.model_used && <span className="ml-2 font-mono">{entry.model_used}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  )
}
