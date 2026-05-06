import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { referencesApi } from '../api/client'
import { Tag, Search, X, Loader2 } from 'lucide-react'
import ReferenceCard from '../components/ReferenceCard'

export default function TagBrowser() {
  const navigate = useNavigate()
  const [selectedTag, setSelectedTag] = useState(null)
  const [search, setSearch] = useState('')

  // Get all references to extract tags
  const { data: allRefs = [], isLoading } = useQuery({
    queryKey: ['references', 'all-for-tags'],
    queryFn: () => referencesApi.list({ limit: 200 }).then(r => r.data),
  })

  // Aggregate tags with counts
  const tagMap = {}
  for (const ref of allRefs) {
    for (const t of (ref.tags || [])) {
      tagMap[t.tag] = (tagMap[t.tag] || 0) + 1
    }
  }
  const tags = Object.entries(tagMap)
    .sort((a, b) => b[1] - a[1])
    .filter(([tag]) => !search || tag.includes(search.toLowerCase()))

  const taggedRefs = selectedTag
    ? allRefs.filter(r => r.tags?.some(t => t.tag === selectedTag))
    : []

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gray-900">Tag Browser</h1>
        <p className="text-sm text-gray-500 mt-1">
          Browse references by topic tag — tags cut across collections.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Tag cloud */}
        <div className="col-span-1">
          <div className="card p-4">
            <div className="relative mb-3">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                className="input pl-8 text-xs"
                placeholder="Filter tags..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>

            {isLoading ? (
              <div className="flex justify-center py-8"><Loader2 size={18} className="animate-spin text-gray-300" /></div>
            ) : tags.length === 0 ? (
              <p className="text-xs text-gray-400 text-center py-4">No tags yet</p>
            ) : (
              <div className="space-y-0.5 max-h-[65vh] overflow-y-auto">
                {tags.map(([tag, count]) => (
                  <button
                    key={tag}
                    onClick={() => setSelectedTag(selectedTag === tag ? null : tag)}
                    className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs transition-colors text-left ${
                      selectedTag === tag
                        ? 'bg-alexandria-600 text-white'
                        : 'text-gray-700 hover:bg-gray-50'
                    }`}
                  >
                    <span className="flex items-center gap-1.5">
                      <Tag size={10} />
                      {tag}
                    </span>
                    <span className={`text-xs ${selectedTag === tag ? 'text-white/70' : 'text-gray-400'}`}>
                      {count}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* References for selected tag */}
        <div className="col-span-2">
          {!selectedTag ? (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400">
              <Tag size={32} className="mb-3 text-gray-200" />
              <p className="font-medium">Select a tag to browse references</p>
              <p className="text-sm mt-1">{Object.keys(tagMap).length} unique tags across {allRefs.length} references</p>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="badge bg-alexandria-600 text-white px-2 py-1 text-sm">
                    <Tag size={11} className="mr-1" />
                    {selectedTag}
                  </span>
                  <span className="text-sm text-gray-500">{taggedRefs.length} reference{taggedRefs.length !== 1 ? 's' : ''}</span>
                </div>
                <button onClick={() => setSelectedTag(null)} className="text-gray-400 hover:text-gray-600">
                  <X size={16} />
                </button>
              </div>
              <div className="space-y-2">
                {taggedRefs.map(r => <ReferenceCard key={r.id} reference={r} />)}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
