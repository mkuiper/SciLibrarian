import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { referencesApi, collectionsApi, searchApi, semanticSearchApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import ReferenceCard from '../components/ReferenceCard'
import AddReferenceModal from '../components/AddReferenceModal'
import { Plus, Search, FolderPlus, Loader2, X, Star, Eye, ChevronDown, ChevronLeft, ChevronRight, Columns, Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'

const PAGE_SIZE = 50

const SOURCE_TYPES = ['paper', 'policy', 'model_card', 'evaluation', 'government', 'news', 'other']

function NewCollectionForm({ parentId, projectId, onDone }) {
  const [name, setName] = useState('')
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    try {
      await collectionsApi.create({ name: name.trim(), parent_id: parentId || null, project_id: projectId || null })
      queryClient.invalidateQueries({ queryKey: ['collections-tree'] })
      queryClient.invalidateQueries({ queryKey: ['collections-flat'] })
      toast.success('Collection created')
      onDone()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create collection')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={submit} className="card p-4 mb-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">New collection</h3>
      <div className="flex gap-2">
        <input className="input flex-1" placeholder="Collection name" required value={name} onChange={e => setName(e.target.value)} autoFocus />
        <button type="submit" disabled={loading} className="btn-primary text-xs px-3">
          {loading ? <Loader2 size={12} className="animate-spin" /> : 'Create'}
        </button>
        <button type="button" onClick={onDone} className="btn-ghost text-xs">Cancel</button>
      </div>
      {!projectId && (
        <p className="text-xs text-amber-500 mt-2">⚠ No project selected — create a project first.</p>
      )}
    </form>
  )
}

export default function Library() {
  const { collectionId } = useParams()
  const navigate = useNavigate()
  const colId = collectionId ? parseInt(collectionId) : undefined
  const { projectId } = useProject()

  const [showAdd, setShowAdd] = useState(false)
  const [showNewCol, setShowNewCol] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterStarred, setFilterStarred] = useState(false)
  const [filterUnread, setFilterUnread] = useState(false)
  const [filterImportant, setFilterImportant] = useState(false)
  const [yearFrom, setYearFrom] = useState('')
  const [yearTo, setYearTo] = useState('')
  const [sortBy, setSortBy] = useState('recent')
  const [page, setPage] = useState(0)
  const [compareMode, setCompareMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState(() => new Set())

  useEffect(() => {
    setPage(0)
  }, [colId, projectId, searchQ, filterType, filterStarred, filterUnread, filterImportant, yearFrom, yearTo])

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < 8) next.add(id)
      else toast.error('Compare up to 8 references at a time')
      return next
    })
  }

  const exitCompareMode = () => {
    setCompareMode(false)
    setSelectedIds(new Set())
  }

  const goCompare = () => {
    if (selectedIds.size < 2) {
      toast.error('Select at least 2 references')
      return
    }
    navigate(`/compare?ids=${[...selectedIds].join(',')}`)
  }

  const { data: collection } = useQuery({
    queryKey: ['collection', colId],
    queryFn: () => colId ? collectionsApi.get(colId).then(r => r.data) : null,
    enabled: !!colId,
  })

  // Build server-side filter params shared by both list and search queries
  const serverFilters = {
    project_id: projectId,
    collection_id: colId,
    source_type: filterType || undefined,
    starred: filterStarred ? true : undefined,
    read_status: filterImportant ? 'important' : (filterUnread ? 'unread' : undefined),
    year_from: yearFrom ? parseInt(yearFrom) : undefined,
    year_to: yearTo ? parseInt(yearTo) : undefined,
  }

  const [semantic, setSemantic] = useState(false)
  // Reset page on every toggle so a "Page 5 of 1" state is impossible after
  // switching to semantic (which always returns one page).
  useEffect(() => { setPage(0) }, [semantic])
  const isSearching = searchQ && searchQ.length > 2
  const offset = page * PAGE_SIZE

  const { data: listResponse, isLoading } = useQuery({
    queryKey: ['references', projectId, colId, filterType, filterStarred, filterUnread, filterImportant, yearFrom, yearTo, page],
    queryFn: () => referencesApi.list({ ...serverFilters, limit: PAGE_SIZE, offset }).then(r => ({
      results: r.data,
      total: parseInt(r.headers['x-total-count'] || `${r.data.length}`, 10),
    })),
    enabled: !isSearching,
    keepPreviousData: true,
  })
  const refs = listResponse?.results || []
  const listTotal = listResponse?.total ?? 0

  // Keyword search via FTS — handles pagination via offset.
  const { data: searchResults } = useQuery({
    queryKey: ['search', projectId, searchQ, colId, filterType, filterStarred, filterUnread, filterImportant, yearFrom, yearTo, page],
    queryFn: () => searchApi.search({ ...serverFilters, q: searchQ, limit: PAGE_SIZE, offset }).then(r => r.data),
    enabled: !!isSearching && !semantic && !!projectId,
    keepPreviousData: true,
  })

  // Semantic search — embedding-based, currently no pagination (returns top-k from one call).
  const { data: semanticResults, isFetching: semanticFetching, error: semanticError } = useQuery({
    queryKey: ['search-semantic', projectId, searchQ],
    queryFn: () => semanticSearchApi.search({ q: searchQ, project_id: projectId, limit: 30 }).then(r => r.data),
    enabled: !!isSearching && semantic && !!projectId,
  })

  const activeSearch = semantic ? semanticResults : searchResults
  let displayRefs = isSearching ? (activeSearch?.results || []) : refs
  const total = isSearching ? (activeSearch?.total ?? displayRefs.length) : listTotal
  const totalPages = Math.max(1, semantic ? 1 : Math.ceil(total / PAGE_SIZE))
  const snippets = isSearching && !semantic ? Object.fromEntries((searchResults?.results || []).map(r => [r.id, r.snippet])) : {}

  if (sortBy === 'year') displayRefs = [...displayRefs].sort((a, b) => (b.year || 0) - (a.year || 0))
  else if (sortBy === 'title') displayRefs = [...displayRefs].sort((a, b) => a.title.localeCompare(b.title))

  const clearFilters = () => {
    setFilterStarred(false); setFilterUnread(false); setFilterImportant(false)
    setFilterType(''); setYearFrom(''); setYearTo('')
  }
  const hasFilters = filterStarred || filterUnread || filterImportant || filterType || yearFrom || yearTo

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{collection ? collection.name : 'Library'}</h1>
          {collection?.description && <p className="text-sm text-gray-500 mt-0.5">{collection.description}</p>}
          {!collection && <p className="text-xs text-gray-400 mt-0.5">All references · select a collection from the sidebar to filter</p>}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => compareMode ? exitCompareMode() : setCompareMode(true)}
            className={`btn-ghost text-sm ${compareMode ? 'text-alexandria-700' : ''}`}
            title="Compare references side by side"
          >
            <Columns size={14} />{compareMode ? 'Cancel compare' : 'Compare'}
          </button>
          <button onClick={() => setShowNewCol(v => !v)} className="btn-secondary text-sm">
            <FolderPlus size={14} />New collection
          </button>
          <button onClick={() => setShowAdd(true)} className="btn-primary text-sm">
            <Plus size={14} />Add reference
          </button>
        </div>
      </div>

      {showNewCol && <NewCollectionForm parentId={colId} projectId={projectId} onDone={() => setShowNewCol(false)} />}

      {/* Search + filters */}
      <div className="space-y-2 mb-5">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              className="input pl-9 text-sm"
              placeholder={semantic ? 'Semantic search — find conceptually similar refs...' : 'Search — full-text, ranked by relevance...'}
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
            />
            {searchQ && (
              <button onClick={() => setSearchQ('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                <X size={13} />
              </button>
            )}
          </div>
          <button
            onClick={() => setSemantic(v => !v)}
            className={`btn-ghost text-sm gap-1.5 ${semantic ? 'text-alexandria-700 bg-alexandria-50' : ''}`}
            title={semantic ? 'Switch to keyword (full-text) search' : 'Switch to semantic search (embedding-based)'}
          >
            <Sparkles size={13} />{semantic ? 'Semantic' : 'Keyword'}
          </button>
          <select value={filterType} onChange={e => setFilterType(e.target.value)} className="input w-40 text-sm">
            <option value="">All types</option>
            {SOURCE_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
          </select>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)} className="input w-32 text-sm">
            <option value="recent">Recent</option>
            <option value="year">By year</option>
            <option value="title">A–Z</option>
          </select>
          <button
            onClick={() => setShowFilters(v => !v)}
            className={`btn-ghost px-3 text-sm ${showFilters ? 'text-alexandria-600' : ''}`}
            title="More filters"
          >
            <ChevronDown size={14} className={showFilters ? 'rotate-180' : ''} />
          </button>
        </div>

        {/* Expanded filter row */}
        {showFilters && (
          <div className="flex gap-2 items-center flex-wrap pl-1">
            <span className="text-xs text-gray-400">Year:</span>
            <input type="number" placeholder="From" className="input w-24 text-xs py-1" value={yearFrom} onChange={e => setYearFrom(e.target.value)} />
            <span className="text-xs text-gray-400">–</span>
            <input type="number" placeholder="To" className="input w-24 text-xs py-1" value={yearTo} onChange={e => setYearTo(e.target.value)} />
          </div>
        )}

        {/* Quick filters */}
        <div className="flex items-center gap-2 flex-wrap">
          {[
            { label: 'Starred', icon: <Star size={12} />, active: filterStarred, toggle: () => setFilterStarred(v => !v) },
            { label: 'Unread', icon: <Eye size={12} />, active: filterUnread, toggle: () => setFilterUnread(v => !v) },
            { label: 'Important', icon: <span className="text-amber-500 font-bold text-xs">★</span>, active: filterImportant, toggle: () => setFilterImportant(v => !v) },
          ].map(({ label, icon, active, toggle }) => (
            <button
              key={label}
              onClick={toggle}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border ${
                active ? 'bg-alexandria-50 text-alexandria-700 border-alexandria-300' : 'bg-white text-gray-500 border-gray-200 hover:border-alexandria-200'
              }`}
            >
              {icon}{label}
            </button>
          ))}
          {hasFilters && (
            <button onClick={clearFilters} className="text-xs text-gray-400 hover:text-gray-600 flex items-center gap-1">
              <X size={11} /> Clear
            </button>
          )}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={22} className="animate-spin text-gray-300" />
        </div>
      ) : displayRefs.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-5xl mb-4">📚</div>
          <h3 className="text-gray-500 font-medium">
            {isSearching ? 'No results' : hasFilters ? 'No matching references' : 'No references yet'}
          </h3>
          <p className="text-gray-400 text-sm mt-1">
            {isSearching ? 'Try different terms or ask Alexandria in the chat panel'
              : hasFilters ? 'Clear the filter to see all references'
              : 'Click "Add reference" to get started'}
          </p>
          {!isSearching && !hasFilters && (
            <button onClick={() => setShowAdd(true)} className="btn-primary mt-4">
              <Plus size={14} /> Add reference
            </button>
          )}
        </div>
      ) : (
        <div>
          <p className="text-xs text-gray-400 mb-3">
            {isSearching
              ? `${total} results for "${searchQ}"`
              : `${total} reference${total !== 1 ? 's' : ''}`}
            {collection && ` in ${collection.name}`}
            {totalPages > 1 && ` · page ${page + 1} of ${totalPages}`}
          </p>
          <div className="space-y-2">
            {displayRefs.map(r => (
              <ReferenceCard
                key={r.id}
                reference={r}
                snippet={snippets[r.id]}
                selectable={compareMode}
                selected={selectedIds.has(r.id)}
                onToggleSelect={toggleSelect}
              />
            ))}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="btn-ghost text-xs disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <ChevronLeft size={14} /> Prev
              </button>
              <span className="text-xs text-gray-500 px-3">
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="btn-ghost text-xs disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          )}
        </div>
      )}

      {showAdd && (
        <AddReferenceModal collectionId={colId} projectId={projectId} onClose={() => setShowAdd(false)} />
      )}

      {compareMode && selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 card px-4 py-2.5 shadow-lg flex items-center gap-3 bg-white border border-alexandria-200">
          <span className="text-sm text-gray-700">{selectedIds.size} selected</span>
          <button onClick={goCompare} className="btn-primary text-sm" disabled={selectedIds.size < 2}>
            <Columns size={14} /> Compare {selectedIds.size}
          </button>
          <button onClick={exitCompareMode} className="btn-ghost text-xs">Cancel</button>
        </div>
      )}
    </div>
  )
}
