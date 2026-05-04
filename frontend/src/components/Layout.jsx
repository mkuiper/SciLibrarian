import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import LibrarianPanel from './LibrarianPanel'
import { MessageSquare, PanelRightClose, PanelRightOpen } from 'lucide-react'

export default function Layout() {
  const [chatOpen, setChatOpen] = useState(false)

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      <Sidebar />

      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>

      {chatOpen ? (
        <div className="w-96 flex-shrink-0 border-l border-gray-200 bg-white flex flex-col">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-slate-900">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-alexandria-600 flex items-center justify-center text-white text-xs font-bold">A</div>
              <div>
                <p className="text-sm font-semibold text-white">Alexandria</p>
                <p className="text-xs text-slate-400">Research Librarian</p>
              </div>
            </div>
            <button onClick={() => setChatOpen(false)} className="text-slate-400 hover:text-slate-200 transition-colors">
              <PanelRightClose size={18} />
            </button>
          </div>
          <LibrarianPanel />
        </div>
      ) : (
        <button
          onClick={() => setChatOpen(true)}
          className="fixed bottom-6 right-6 w-14 h-14 bg-alexandria-600 text-white rounded-full shadow-lg hover:bg-alexandria-700 transition-all flex items-center justify-center group"
          title="Ask Alexandria"
        >
          <MessageSquare size={22} />
          <span className="absolute right-16 bg-slate-900 text-white text-xs px-2 py-1 rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity">
            Ask Alexandria
          </span>
        </button>
      )}
    </div>
  )
}
