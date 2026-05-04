import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { referencesApi, collectionsApi, searchApi } from '../api/client'
import ReferenceCard from '../components/ReferenceCard'
import AddReferenceModal from '../components/AddReferenceModal'
import { Plus, Search, Filter, FolderPlus, Loader2, X } from 'lucide-react'
import toast from 'react-hot-toast'

const SOURCE_TYPES = ['paper', 'policy', 'model_card', 'evaluation', 'government', 'news', 'other']

function NewCollectionForm({ parentId, onDone }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await collectionsApi.create({ name, description: desc, parent_id: parentId })
      queryClient.invalidateQueries({ queryKey: ['collections-tree'] })
      toast.success('Collection created')
      onDone()
    } catch {
      toast.error('Failed to create collection')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={submit} className="card p-4 mb-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">New collection</h3>
      <div className="space-y-2">
        <input className="input" placeholder="Collection name" required value={name} onChange={e => setName(e.target.value)} />
        <input className="input" placeholder="Description (optional)" value={desc} onChange={e => setDesc(e.target.value)} />
      </div>
      <div className="flex gap-2 mt-3">
        <button type="button" onClick={onDone} className="btn-ghost text-xs">Cancel</button>
        <button type="submit" disabled={loading} className="btn-primary text-xs">
          {loading && <Loader2 size={12} className="animate-spin" />}
          Create
        </button>
      </div>
    </form>
  )
}

export default function Library() {
  const { collectionId } = useParams()
  const colId = collectionId ? parseInt(collectionId) : undefined
  const [showAdd, setShowAdd] = useState(false)
  const [showNewCol, setShowNewCol] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [filterType, setFilterType] = useState('')
  const [searching, setSearching] = useState(false)

  const { data: collection } = useQuery({
    queryKey: ['collection', colId],
    queryFn: () => colId ? collectionsApi.get(colId).then(r => r.data) : null,
    enabled: !!colId,
  })

  const { data: refs = [], isLoading } = useQuery({
    queryKey: ['references', colId, filterType],
    queryFn: () => referencesApi.list({ collection_id: colId, source_type: filterType || undefined, limit: 100 }).then(r => r.data),
    enabled: !searchQ,
  })

  const { data: searchResults } = useQuery({
    queryKey: ['search', searchQ, colId, filterType],
    queryFn: () => searchApi.search({ q: searchQ, collection_id: colId, source_type: filterType || undefined }).then(r => r.data),
    enabled: !!searchQ && searchQ.length > 2,
  })

  const displayRefs = searchQ && searchQ.length > 2 ? (searchResults?.results || []) : refs

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">
            {collection ? collection.name : 'Library'}
          </h1>
          {collection?.description && (
            <p className="text-sm text-gray-500 mt-0.5">{collection.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowNewCol(v => !v)} className="btn-secondary">
            <FolderPlus size={15} />
            New collection
          </button>
          <button onClick={() => setShowAdd(true)} className="btn-primary">
            <Plus size={15} />
            Add reference
          </button>
        </div>
      </div>

      {showNewCol && (
        <NewCollectionForm parentId={colId} onDone={() => setShowNewCol(false)} />
      )}

      <div className="flex gap-3 mb-6">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            className="input pl-9"
            placeholder="Search titles, abstracts, summaries..."
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
          />
          {searchQ && (
            <button onClick={() => setSearchQ('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              <X size={14} />
            </button>
          )}
        </div>
        <select
          value={filterType}
          onChange={e => setFilterType(e.target.value)}
          className="input w-44"
        >
          <option value="">All types</option>
          {SOURCE_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={24} className="animate-spin text-gray-300" />
        </div>
      ) : displayRefs.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-gray-200 text-6xl mb-4">📚</div>
          <h3 className="text-gray-500 font-medium">
            {searchQ ? 'No results found' : 'No references yet'}
          </h3>
          <p className="text-gray-400 text-sm mt-1">
            {searchQ ? 'Try different search terms' : 'Add your first reference to get started'}
          </p>
          {!searchQ && (
            <button onClick={() => setShowAdd(true)} className="btn-primary mt-4">
              <Plus size={15} />
              Add reference
            </button>
          )}
        </div>
      ) : (
        <div>
          <p className="text-xs text-gray-400 mb-4">
            {searchQ ? `${displayRefs.length} results` : `${displayRefs.length} references`}
          </p>
          <div className="grid grid-cols-1 gap-3">
            {displayRefs.map(r => <ReferenceCard key={r.id} ref={r} />)}
          </div>
        </div>
      )}

      {showAdd && (
        <AddReferenceModal
          collectionId={colId}
          onClose={() => setShowAdd(false)}
        />
      )}
    </div>
  )
}
