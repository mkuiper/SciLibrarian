import { useNavigate } from 'react-router-dom'
import {
  BookOpen, FolderTree, Search, MessageSquare, Inbox,
  Radio, Sparkles, Eye, Upload, ArrowRight, Layers,
} from 'lucide-react'

function Section({ icon: Icon, color, title, children }) {
  return (
    <div className="card p-6">
      <div className="flex items-start gap-4">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
          <Icon size={18} className="text-white" />
        </div>
        <div className="flex-1">
          <h2 className="text-base font-semibold text-gray-900 mb-2">{title}</h2>
          {children}
        </div>
      </div>
    </div>
  )
}

function Step({ n, text }) {
  return (
    <div className="flex items-start gap-3">
      <span className="w-6 h-6 rounded-full bg-alexandria-100 text-alexandria-700 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">{n}</span>
      <p className="text-sm text-gray-600">{text}</p>
    </div>
  )
}

export default function HowItWorks() {
  const navigate = useNavigate()

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">How SciLibrarian works</h1>
        <p className="text-gray-500 mt-2">
          A guide to organising your research library and getting the most from Alexandria.
        </p>
      </div>

      {/* Structure overview */}
      <div className="card p-6 mb-6 bg-gradient-to-r from-slate-900 to-slate-800">
        <h2 className="text-white font-semibold mb-4">Library structure</h2>
        <div className="flex items-center gap-2 text-sm flex-wrap">
          {[
            ['Project', 'bg-alexandria-600', 'The top-level container. Each project has its own library, collections, and Alexandria configuration.'],
            ['→', 'text-slate-400', ''],
            ['Collections', 'bg-purple-600', 'Folders that organise your references. Can be nested (sub-collections). Alexandria designs the initial structure for you.'],
            ['→', 'text-slate-400', ''],
            ['References', 'bg-emerald-600', 'Individual papers, documents, datasets, or any file. Each has AI-generated metadata, summary, and tags.'],
          ].map(([label, cls, _], i) => (
            label === '→'
              ? <ArrowRight key={i} size={16} className="text-slate-500" />
              : <div key={i} className="flex-shrink-0">
                  <span className={`badge ${cls} text-white text-xs px-2 py-1`}>{label}</span>
                </div>
          ))}
        </div>
        <p className="text-slate-400 text-xs mt-4">
          Each project is completely independent — its own collections, references, monitors, digests, and Alexandria settings.
          Switch between projects using the dropdown in the sidebar.
        </p>
      </div>

      <div className="space-y-4 mb-8">
        <Section icon={Layers} color="bg-alexandria-600" title="Projects — your research spaces">
          <p className="text-sm text-gray-600 mb-3">
            A <strong>project</strong> represents a research initiative or topic area. Create one for each distinct body of work:
            e.g. "AI Safety Literature Review", "Model Evaluation Research", "Policy Analysis".
          </p>
          <p className="text-sm text-gray-600">
            When you create a project, Alexandria analyses your description and goals, then designs a custom collection
            structure tailored to your domain. You can edit this structure at any time via the <strong>Collections</strong> page.
          </p>
        </Section>

        <Section icon={FolderTree} color="bg-purple-600" title="Collections — organising your references">
          <p className="text-sm text-gray-600 mb-3">
            Collections are the folder structure within your project's library. They can be nested to any depth.
            Examples: <em>Technical Papers → Alignment → Constitutional AI</em> or <em>Policy Documents → Australia → AISC</em>.
          </p>
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Manage collections</p>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
              <div className="bg-gray-50 rounded-lg p-2">
                <strong>Collections page</strong> — rename, add, nest, delete collections
              </div>
              <div className="bg-gray-50 rounded-lg p-2">
                <strong>Restructure page</strong> — ask Alexandria to analyse and suggest improvements
              </div>
            </div>
          </div>
        </Section>

        <Section icon={Upload} color="bg-blue-600" title="Adding references to your library">
          <p className="text-sm text-gray-600 mb-3">
            Any reference you add is automatically processed by Alexandria: text is extracted, a summary is generated,
            metadata is assigned (title, authors, year, type, tags), and it's stored for search.
          </p>
          <div className="space-y-2 text-sm text-gray-600">
            <div className="grid grid-cols-2 gap-3">
              {[
                ['📄 PDF upload', 'Drag and drop or browse. Full text extracted and indexed.'],
                ['🔗 URL', 'Paste any URL — arXiv, government sites, journals, news.'],
                ['📁 Batch / ZIP', 'Upload a ZIP of PDFs or select multiple files at once.'],
                ['✉️ Email', 'Email PDFs or URLs to your ingestion address (configure in Settings).'],
                ['🗂️ Spreadsheets', 'CSV, Excel — Alexandria summarises the dataset structure.'],
                ['🧬 PDB / FASTA', 'Protein structures and sequences — metadata extracted automatically.'],
              ].map(([t, d]) => (
                <div key={t} className="bg-gray-50 rounded-lg p-2">
                  <p className="font-medium text-gray-700">{t}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{d}</p>
                </div>
              ))}
            </div>
          </div>
        </Section>

        <Section icon={Search} color="bg-amber-500" title="Searching the library">
          <p className="text-sm text-gray-600 mb-3">
            Use the search bar on the <strong>Library</strong> page to search across all reference titles, abstracts,
            summaries, and full extracted text simultaneously. Filter by source type (paper, policy, model card, etc.).
          </p>
          <p className="text-sm text-gray-600">
            For semantic questions like "what do we know about X?" — ask <strong>Alexandria</strong> in the chat panel
            instead. She searches the library with multiple queries and synthesises an answer with citations.
          </p>
        </Section>

        <Section icon={MessageSquare} color="bg-indigo-600" title="Alexandria — your AI librarian">
          <p className="text-sm text-gray-600 mb-3">
            Click the chat button (bottom-right) to open Alexandria. She has four tools available:
          </p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              ['search_library', 'Full-text search of your references'],
              ['get_full_text', 'Read the complete text of a specific reference'],
              ['web_search', 'DuckDuckGo for current events and policy docs'],
              ['lookup_paper', 'Fetch arXiv metadata by ID or search terms'],
            ].map(([name, desc]) => (
              <div key={name} className="bg-indigo-50 rounded-lg p-2">
                <code className="text-indigo-700 font-medium">{name}</code>
                <p className="text-gray-500 mt-0.5">{desc}</p>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-500 mt-3">
            Customise Alexandria's behaviour via <strong>Configuration → Alexandria's Instructions</strong>.
            Assign different models (Ollama/Claude/GPT) per task.
          </p>
        </Section>

        <Section icon={Radio} color="bg-emerald-600" title="Monitors & Watch Requests — staying current">
          <p className="text-sm text-gray-600 mb-3">
            <strong>Monitors</strong> run automated searches (daily or weekly) across arXiv, Semantic Scholar,
            OpenAlex, and the web. Results appear in the <strong>Review Queue</strong> where you approve or reject
            each item before it enters the library.
          </p>
          <p className="text-sm text-gray-600">
            <strong>Watch Requests</strong> are plain-language descriptions of your interests — e.g.
            "Papers on interpretability methods using sparse autoencoders". Submitting a watch request automatically
            creates a weekly monitor. Alexandria also uses these when answering chat questions.
          </p>
        </Section>

        <Section icon={Inbox} color="bg-orange-500" title="Review Queue — quality control">
          <p className="text-sm text-gray-600">
            Everything found by monitors goes through the Review Queue first — nothing enters your library without
            your approval. This keeps quality high. Review individually (approve/reject + assign to collection)
            or use <strong>Approve all</strong> / <strong>Reject all</strong> for batch processing.
          </p>
        </Section>

        <Section icon={Sparkles} color="bg-pink-600" title="Monthly Digest — staying on top of the field">
          <p className="text-sm text-gray-600">
            Generate a monthly digest at any time. Alexandria reads your library's summaries and synthesises a
            state-of-the-art report covering: new additions, key themes, notable developments, coverage gaps,
            and recommended next steps. Generate for the whole project or zoom in on a single collection.
          </p>
        </Section>
      </div>

      {/* Recommended workflow */}
      <div className="card p-6 mb-6">
        <h2 className="text-base font-semibold text-gray-900 mb-4">Recommended workflow</h2>
        <div className="space-y-3">
          <Step n="1" text="Create a project — describe your research area and goals. Alexandria designs your initial collection structure." />
          <Step n="2" text="Add seed references — upload PDFs, paste arXiv URLs, or batch-import a ZIP of papers you already have." />
          <Step n="3" text="Set up monitors — create 2–3 monitors for your core topics. Run them immediately to populate the review queue." />
          <Step n="4" text="Review the queue weekly — approve relevant items, assign them to collections, reject noise." />
          <Step n="5" text="Ask Alexandria — use the chat panel to synthesise what you know, find gaps, and plan next reading." />
          <Step n="6" text="Generate a monthly digest — share with your team to keep everyone aligned on the state of the field." />
          <Step n="7" text="Restructure as needed — as the library grows, ask Alexandria for reorganisation suggestions." />
        </div>
      </div>

      <div className="flex gap-3 justify-center">
        <button onClick={() => navigate('/projects/new')} className="btn-primary">
          <Sparkles size={15} />Create a project
        </button>
        <button onClick={() => navigate('/library')} className="btn-secondary">
          <BookOpen size={15} />Go to Library
        </button>
      </div>
    </div>
  )
}
