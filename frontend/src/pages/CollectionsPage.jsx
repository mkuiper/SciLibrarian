import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { collectionsApi } from '../api/client'
import { useProject } from '../hooks/useProject'
import {
  FolderOpen, Folder, Plus, Pencil, Trash2, Check, X,
  Loader2, ChevronRight, ChevronDown,
} from 'lucide-react'
import toast from 'react-hot-toast'

function EditableLabel({ value, onSave, onCancel, className = '' }) {
  const [draft, setDraft] = useState(value)
  return (
    <div className={`flex items-center gap-1 ${className}`}>
      <input
        className="input py-0.5 text-sm flex-1"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        autoFocus
        onKeyDown={e => {
          if (e.key === 'Enter') onSave(draft)
          if (e.key === 'Escape') onCancel()
        }}
      />
      <button onClick={() => onSave(draft)} className="text-emerald-500 hover:text-emerald-700"><Check size={14} /></button>
      <button onClick={onCancel} className="text-gray-400 hover:text-gray-600"><X size={14} /></button>
    </div>
  )
}

function CollectionRow({ col, depth = 0, children, onEdit, onDelete, onAddChild }) {
  const [open, setOpen] = useState(depth < 2)
  const [editing, setEditing] = useState(false)
  const hasChildren = children && children.length > 0

  return (
    <div>
      <div
        className="flex items-center gap-1 py-1.5 px-2 rounded-lg hover:bg-gray-50 group"
        style={{ paddingLeft: `${8 + depth * 20}px` }}
      >
        <button
          onClick={() => setOpen(v => !v)}
          className={`flex-shrink-0 ${hasChildren ? 'text-gray-400' : 'invisible'}`}
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>

        {open && hasChildren
          ? <FolderOpen size={15} className="text-alexandria-500 flex-shrink-0" />
          : <Folder size={15} className="text-gray-400 flex-shrink-0" />
        }

        {editing ? (
          <EditableLabel
            value={col.name}
            className="flex-1 ml-1"
            onSave={async (name) => {
              await onEdit(col.id, name)
              setEditing(false)
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <div className="flex-1 min-w-0 flex items-center gap-2 ml-1">
            <span className="text-sm text-gray-800 truncate">{col.name}</span>
            {col.reference_count > 0 && (
              <span className="text-xs text-gray-400 flex-shrink-0">{col.reference_count} refs</span>
            )}
          </div>
        )}

        {!editing && (
          <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
            <button
              onClick={() => setEditing(true)}
              className="p-1 text-gray-400 hover:text-gray-700 rounded"
              title="Rename"
            >
              <Pencil size={12} />
            </button>
            <button
              onClick={() => onAddChild(col.id)}
              className="p-1 text-gray-400 hover:text-alexandria-600 rounded"
              title="Add sub-collection"
            >
              <Plus size={12} />
            </button>
            <button
              onClick={() => onDelete(col.id, col.name, col.reference_count)}
              className="p-1 text-gray-400 hover:text-red-500 rounded"
              title="Delete"
            >
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>

      {open && hasChildren && (
        <div>
          {children.map(child => (
            <CollectionRow
              key={child.id}
              col={child}
              depth={depth + 1}
              children={child.children}
              onEdit={onEdit}
              onDelete={onDelete}
              onAddChild={onAddChild}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function AddCollectionForm({ parentId, parentName, projectId, onDone }) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [loading, setLoading] = useState(false)
  const queryClient = useQueryClient()

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await collectionsApi.create({
        name,
        description: desc || null,
        parent_id: parentId || null,
        project_id: projectId || null,
      })
      queryClient.invalidateQueries({ queryKey: ['collections-tree'] })
      queryClient.invalidateQueries({ queryKey: ['collections-flat'] })
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
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        {parentName ? `Add sub-collection under "${parentName}"` : 'New top-level collection'}
      </h3>
      <div className="space-y-2">
        <input
          className="input"
          placeholder="Collection name"
          required
          value={name}
          onChange={e => setName(e.target.value)}
          autoFocus
        />
        <input
          className="input"
          placeholder="Description (optional)"
          value={desc}
          onChange={e => setDesc(e.target.value)}
        />
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

export default function CollectionsPage() {
  const queryClient = useQueryClient()
  const { project, projectId } = useProject()
  const [addingParentId, setAddingParentId] = useState(null)
  const [addingParentName, setAddingParentName] = useState('')
  const [showAddTop, setShowAddTop] = useState(false)

  const { data: tree = [], isLoading } = useQuery({
    queryKey: ['collections-tree', projectId],
    queryFn: () => collectionsApi.tree(projectId).then(r => r.data),
    enabled: !!projectId,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['collections-tree'] })
    queryClient.invalidateQueries({ queryKey: ['collections-flat'] })
  }

  const handleEdit = async (id, name) => {
    try {
      await collectionsApi.update(id, { name })
      invalidate()
      toast.success('Renamed')
    } catch {
      toast.error('Failed to rename')
    }
  }

  const handleDelete = async (id, name, refCount) => {
    const msg = refCount > 0
      ? `Delete "${name}"? It contains ${refCount} reference(s) which will become uncategorised.`
      : `Delete "${name}"?`
    if (!confirm(msg)) return
    try {
      await collectionsApi.delete(id)
      invalidate()
      toast.success('Collection deleted')
    } catch {
      toast.error('Failed to delete')
    }
  }

  const handleAddChild = (parentId) => {
    const findName = (nodes) => {
      for (const n of nodes) {
        if (n.id === parentId) return n.name
        const found = findName(n.children || [])
        if (found) return found
      }
      return ''
    }
    setAddingParentId(parentId)
    setAddingParentName(findName(tree))
    setShowAddTop(false)
  }

  return (
    <div className="p-8 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Collections</h1>
          <p className="text-sm text-gray-500 mt-1">
            {project ? `${project.name} · ` : ''}Manage your library's folder structure.
            Hover any collection to rename, add sub-collections, or delete.
          </p>
        </div>
        <button onClick={() => { setShowAddTop(true); setAddingParentId(null) }} className="btn-primary">
          <Plus size={15} />New collection
        </button>
      </div>

      {showAddTop && (
        <AddCollectionForm parentId={null} parentName="" projectId={projectId} onDone={() => setShowAddTop(false)} />
      )}

      {addingParentId && (
        <AddCollectionForm
          parentId={addingParentId}
          parentName={addingParentName}
          projectId={projectId}
          onDone={() => { setAddingParentId(null); setAddingParentName('') }}
        />
      )}

      <div className="card p-2">
        {isLoading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 size={20} className="animate-spin text-gray-300" />
          </div>
        ) : tree.length === 0 ? (
          <div className="text-center py-10 text-gray-400">
            <Folder size={28} className="mx-auto mb-2" />
            <p className="text-sm">No collections yet — create one above.</p>
          </div>
        ) : (
          tree.map(col => (
            <CollectionRow
              key={col.id}
              col={col}
              depth={0}
              children={col.children}
              onEdit={handleEdit}
              onDelete={handleDelete}
              onAddChild={handleAddChild}
            />
          ))
        )}
      </div>

      <p className="text-xs text-gray-400 mt-4 text-center">
        Tip: drag references between collections from the Library page, or use the collection picker on each reference.
      </p>
    </div>
  )
}
