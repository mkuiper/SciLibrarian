import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Folder, FolderOpen, ChevronRight, ChevronDown } from 'lucide-react'
import clsx from 'clsx'

function TreeNode({ node, depth }) {
  const [open, setOpen] = useState(depth < 1)
  const hasChildren = node.children?.length > 0
  const indent = depth * 12

  return (
    <div>
      <div className="flex items-center" style={{ paddingLeft: `${12 + indent}px` }}>
        {hasChildren ? (
          <button
            onClick={() => setOpen(v => !v)}
            className="mr-1 text-slate-500 hover:text-slate-300 flex-shrink-0"
          >
            {open ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </button>
        ) : (
          <span className="w-4 flex-shrink-0" />
        )}

        <NavLink
          to={`/library/${node.id}`}
          className={({ isActive }) =>
            clsx(
              'flex items-center gap-1.5 flex-1 py-1 pr-2 text-xs rounded transition-colors truncate',
              isActive ? 'text-alexandria-400' : 'text-slate-400 hover:text-slate-200'
            )
          }
        >
          {open && hasChildren ? <FolderOpen size={12} className="flex-shrink-0" /> : <Folder size={12} className="flex-shrink-0" />}
          <span className="truncate">{node.name}</span>
          {node.reference_count > 0 && (
            <span className="ml-auto text-slate-600 text-xs flex-shrink-0">{node.reference_count}</span>
          )}
        </NavLink>
      </div>

      {open && hasChildren && (
        <div>
          {node.children.map(child => (
            <TreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function CollectionTree({ nodes, depth = 0 }) {
  return (
    <div>
      {nodes.map(node => (
        <TreeNode key={node.id} node={node} depth={depth} />
      ))}
    </div>
  )
}
