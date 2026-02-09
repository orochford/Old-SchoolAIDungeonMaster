import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Upload, BookOpen, Loader, Trash2, RefreshCw, Wand2, Map } from 'lucide-react'
import { api } from '@/services/api'

interface PDFDocument {
  id: string
  original_filename: string
  title: string | null
  description: string | null
  category: 'rules' | 'adventure' | 'supplement' | null
  rpg_system_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  page_count: number | null
  chunk_count: number
  processing_error: string | null
  created_at: string
}

interface AdventureModule {
  id: string
  pdf_document_id: string
  title: string
  code: string | null
  parsing_status: 'pending' | 'processing' | 'completed' | 'failed'
  parsing_progress: number
  parsing_error: string | null
  parsing_log: string[]
  location_count: number
  npc_count: number
  encounter_count: number
  item_count: number
}

interface RPGSystem {
  id: string
  name: string
  code: string
}

/* ─── HELPERS ─── */

/** Clean up a document title for display — strip .pdf extension and parenthetical noise. */
function cleanTitle(raw: string): string {
  let t = raw
    .replace(/\.pdf$/i, '')          // strip .pdf
    .replace(/\s*\(\d+\)\s*$/, '')   // strip " (1)" duplicate suffix
    .replace(/\s*\([^)]*cover[^)]*\)/i, '') // strip "(Brown Cover)" etc
    .trim()
  return t || raw
}

/* ─── COMPONENTS ─── */

const EntityBadge = ({ icon, count, label, color }: { icon: string; count: number; label: string; color: string }) => (
  <div
    className="flex items-center gap-1.5 px-2.5 py-1 rounded"
    style={{
      background: `${color}10`,
      border: `1px solid ${color}20`,
    }}
  >
    <span className="text-xs">{icon}</span>
    <span className="font-['IBM_Plex_Mono',monospace] text-sm font-semibold" style={{ color }}>{count}</span>
    <span className="font-['Crimson_Text',serif] text-[11px] text-[#6a6250]">{label}</span>
  </div>
)

const FakeCover = ({ hue, title }: { hue: number; title: string }) => (
  <div
    className="w-full h-full relative overflow-hidden rounded-t-lg"
    style={{
      background: `linear-gradient(160deg, hsl(${hue}, 30%, 18%) 0%, hsl(${hue}, 20%, 10%) 100%)`,
    }}
  >
    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black/40" />
    {/* Geometric decorative element */}
    <div
      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16 rounded-full"
      style={{ border: `1px solid rgba(255,255,255,0.08)` }}
    />
    <div
      className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 rotate-45 w-10 h-10"
      style={{ border: `1px solid rgba(255,255,255,0.06)` }}
    />
    {/* Module label */}
    <div
      className="absolute top-3 left-3 px-2 py-1 rounded bg-black/50 font-['IBM_Plex_Mono',monospace] text-[9px] tracking-wider uppercase"
      style={{ color: `hsl(${hue}, 40%, 65%)` }}
    >
      PDF Document
    </div>
    {/* Title */}
    <div className="absolute bottom-3 left-3 right-3 font-['Cinzel',serif] text-sm font-semibold text-white/60 leading-tight">
      {title}
    </div>
  </div>
)

const StatusPill = ({ status }: { status: string }) => {
  const configs: Record<string, { label: string; color: string; icon: string }> = {
    completed: { label: 'Indexed', color: '#5a8a5a', icon: '✓' },
    processing: { label: 'Processing…', color: '#c90', icon: '⟳' },
    pending: { label: 'Pending…', color: '#c90', icon: '○' },
    failed: { label: 'Error', color: '#c44', icon: '!' },
  }
  const c = configs[status] || configs.completed
  return (
    <span
      className="inline-flex items-center gap-1 font-['IBM_Plex_Mono',monospace] text-[10px] tracking-wide px-2 py-0.5 rounded-full"
      style={{
        color: c.color,
        background: `${c.color}12`,
        border: `1px solid ${c.color}25`,
      }}
    >
      <span className={`text-[9px] ${status === 'processing' || status === 'pending' ? 'animate-spin inline-block' : ''}`}>{c.icon}</span> {c.label}
    </span>
  )
}

const ModuleCard = ({
  document,
  systems,
  adventureModule,
  index,
  menuOpen,
  onMenuToggle,
}: {
  document: PDFDocument
  systems: RPGSystem[]
  adventureModule: AdventureModule | null
  index: number
  menuOpen: boolean
  onMenuToggle: () => void
}) => {
  const queryClient = useQueryClient()
  const [showParsingLog, setShowParsingLog] = useState(false)
  const [isEditingDescription, setIsEditingDescription] = useState(false)
  const [descriptionInput, setDescriptionInput] = useState(document.description || '')
  const [imgFailed, setImgFailed] = useState(false)

  const updateMutation = useMutation({
    mutationFn: (data: { category?: string; rpg_system_id?: string; description?: string }) =>
      api.patch(`/sourcebooks/${document.id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourcebooks'] })
      setIsEditingDescription(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/sourcebooks/${document.id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourcebooks'] })
    },
  })

  const reprocessMutation = useMutation({
    mutationFn: () => api.post(`/sourcebooks/${document.id}/reprocess`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourcebooks'] })
    },
  })

  const parseAdventureMutation = useMutation({
    mutationFn: () => api.post(`/adventures/${document.id}/parse`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adventure-modules-all'] })
    },
  })

  const retryEmbeddingsMutation = useMutation({
    mutationFn: () => api.post(`/adventures/${document.id}/embeddings`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adventure-modules-all'] })
    },
  })

  // Generate a hue from the title for the fake cover
  const coverHue = (document.title || document.original_filename).split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % 360
  const hasEntities = adventureModule && (adventureModule.location_count + adventureModule.npc_count + adventureModule.encounter_count) > 0

  const categoryLabel: Record<string, string> = {
    adventure: 'Adventure',
    rules: 'Rulebook',
    supplement: 'Supplement',
  }

  return (
    <div
      className="bg-[#141210] rounded-lg overflow-hidden flex flex-col transition-all duration-300 hover:border-[rgba(180,160,100,0.2)] hover:-translate-y-0.5"
      style={{
        border: '1px solid rgba(180,160,100,0.1)',
        animation: `cardIn 0.4s ease ${index * 0.08}s both`,
      }}
    >
      {/* Cover Area */}
      <div className="h-44 relative flex-shrink-0 bg-[#0a0908] rounded-t-lg">
        {!imgFailed ? (
          <img
            src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/sourcebooks/${document.id}/cover`}
            alt="Cover"
            className="w-full h-full object-contain rounded-t-lg"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <FakeCover hue={coverHue} title={cleanTitle(document.title || document.original_filename)} />
        )}

        {/* Category badge */}
        {document.category && (
          <div
            className="absolute top-2 right-2 px-2.5 py-1 rounded font-['IBM_Plex_Mono',monospace] text-[9px] tracking-wider uppercase text-[#b8a060]"
            style={{
              background: 'rgba(10,9,8,0.8)',
              backdropFilter: 'blur(8px)',
              border: '1px solid rgba(180,160,100,0.15)',
            }}
          >
            {categoryLabel[document.category] || document.category}
          </div>
        )}

        {/* Menu button */}
        <button
          onClick={(e) => { e.stopPropagation(); onMenuToggle() }}
          className="absolute bottom-2 right-2 w-7 h-7 rounded flex items-center justify-center text-[#6a6250] hover:text-[#c8c0aa] cursor-pointer transition-colors"
          style={{
            background: 'rgba(10,9,8,0.7)',
            backdropFilter: 'blur(8px)',
            border: '1px solid rgba(180,160,100,0.1)',
          }}
        >
          ⋯
        </button>

        {/* Dropdown menu */}
        {menuOpen && (
          <div className="absolute bottom-10 right-2 z-20 bg-[#1a1816] border border-[rgba(180,160,100,0.2)] rounded-md p-1 min-w-[140px] shadow-xl">
            <button
              onClick={() => reprocessMutation.mutate()}
              disabled={reprocessMutation.isPending || document.status === 'processing' || document.status === 'pending'}
              className="flex items-center gap-2 w-full px-2.5 py-1.5 rounded text-left font-['Crimson_Text',serif] text-sm text-[#8a8270] hover:bg-[rgba(180,160,100,0.06)] transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${reprocessMutation.isPending ? 'animate-spin' : ''}`} />
              Re-index PDF
            </button>
            {document.category === 'adventure' && (
              <button
                onClick={() => parseAdventureMutation.mutate()}
                disabled={parseAdventureMutation.isPending || adventureModule?.parsing_status === 'processing'}
                className="flex items-center gap-2 w-full px-2.5 py-1.5 rounded text-left font-['Crimson_Text',serif] text-sm text-[#8a8270] hover:bg-[rgba(180,160,100,0.06)] transition-colors disabled:opacity-50"
              >
                <Wand2 className="w-3 h-3" />
                {adventureModule?.parsing_status === 'completed' ? 'Re-parse' : 'Parse Adventure'}
              </button>
            )}
            {adventureModule?.parsing_log && adventureModule.parsing_log.length > 0 && (
              <button
                onClick={() => setShowParsingLog(!showParsingLog)}
                className="flex items-center gap-2 w-full px-2.5 py-1.5 rounded text-left font-['Crimson_Text',serif] text-sm text-[#8a8270] hover:bg-[rgba(180,160,100,0.06)] transition-colors"
              >
                <span className="w-3 text-center">📋</span>
                Show Parse Log
              </button>
            )}
            <button
              onClick={() => {
                if (confirm(`Delete "${cleanTitle(document.title || document.original_filename)}"? This cannot be undone.`)) {
                  deleteMutation.mutate()
                }
              }}
              disabled={deleteMutation.isPending}
              className="flex items-center gap-2 w-full px-2.5 py-1.5 rounded text-left font-['Crimson_Text',serif] text-sm text-red-400 hover:bg-red-400/10 transition-colors"
            >
              <Trash2 className="w-3 h-3" />
              Delete
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 flex-1 flex flex-col">
        {/* Title & status */}
        <div className="flex items-start justify-between gap-2 mb-1">
          <h3 className="font-['Cinzel',serif] text-base font-semibold text-[#c8c0aa] leading-tight line-clamp-2">
            {cleanTitle(document.title || document.original_filename)}
          </h3>
          <StatusPill status={document.status} />
        </div>

        {/* Meta */}
        <div className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#6a6250] mb-2 flex gap-2">
          {document.page_count && <span>{document.page_count} pages</span>}
          {document.chunk_count > 0 && (
            <>
              <span className="opacity-30">·</span>
              <span>{document.chunk_count} chunks</span>
            </>
          )}
        </div>

        {/* Description */}
        {isEditingDescription ? (
          <div className="mb-3">
            <textarea
              value={descriptionInput}
              onChange={(e) => setDescriptionInput(e.target.value)}
              placeholder="Add a brief description..."
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.2)] text-[#c8c0aa] text-sm rounded px-2 py-1.5 resize-none font-['Crimson_Text',serif]"
              rows={2}
              autoFocus
            />
            <div className="flex gap-2 mt-2">
              <button
                onClick={() => updateMutation.mutate({ description: descriptionInput })}
                disabled={updateMutation.isPending}
                className="px-3 py-1 text-xs bg-[#b8a060] text-[#0f0d0a] rounded hover:bg-[#d4b870] font-medium"
              >
                Save
              </button>
              <button
                onClick={() => {
                  setIsEditingDescription(false)
                  setDescriptionInput(document.description || '')
                }}
                className="px-3 py-1 text-xs text-[#8a8270] hover:text-[#c8c0aa]"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : document.description ? (
          <p
            onClick={() => setIsEditingDescription(true)}
            className="font-['Crimson_Text',serif] text-sm text-[#8a8270] leading-relaxed mb-3 line-clamp-3 cursor-pointer hover:text-[#c8c0aa]"
          >
            {document.description}
          </p>
        ) : (
          <p
            onClick={() => setIsEditingDescription(true)}
            className="font-['Crimson_Text',serif] text-sm text-[#5a5245] italic mb-3 cursor-pointer hover:text-[#8a8270]"
          >
            Click to add description...
          </p>
        )}

        {/* Category selector for uncategorized */}
        {!document.category && (
          <div className="mb-3">
            <select
              value=""
              onChange={(e) => updateMutation.mutate({ category: e.target.value })}
              className="w-full bg-[#0f0d0a] border border-[rgba(180,160,100,0.2)] text-[#c8c0aa] text-xs rounded px-2 py-1.5 font-['Crimson_Text',serif]"
            >
              <option value="">Set document type...</option>
              <option value="rules">Rulebook</option>
              <option value="adventure">Adventure</option>
              <option value="supplement">Supplement</option>
            </select>
          </div>
        )}

        {/* Entity extraction badges */}
        {hasEntities && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {adventureModule.location_count > 0 && (
              <EntityBadge icon="🏰" count={adventureModule.location_count} label="locations" color="#7a9ab8" />
            )}
            {adventureModule.npc_count > 0 && (
              <EntityBadge icon="👤" count={adventureModule.npc_count} label={adventureModule.npc_count === 1 ? 'NPC' : 'NPCs'} color="#b8a060" />
            )}
            {adventureModule.encounter_count > 0 && (
              <EntityBadge icon="⚔" count={adventureModule.encounter_count} label="encounters" color="#c44" />
            )}
          </div>
        )}

        {/* View Map button for parsed adventures */}
        {adventureModule?.parsing_status === 'completed' && (
          <Link
            to={`/adventures/${adventureModule.id}/graph`}
            className="mb-3 w-full py-2 rounded flex items-center justify-center gap-2 font-['Cinzel',serif] text-xs font-medium transition-all text-[#b8a060] hover:text-[#f0e8d0]"
            style={{
              border: '1px solid rgba(180,160,100,0.2)',
              background: 'rgba(180,160,80,0.04)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(180,160,80,0.1)'
              e.currentTarget.style.borderColor = 'rgba(180,160,100,0.35)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(180,160,80,0.04)'
              e.currentTarget.style.borderColor = 'rgba(180,160,100,0.2)'
            }}
          >
            <Map className="w-3.5 h-3.5" />
            View Dungeon Map
          </Link>
        )}

        {/* Adventure parsing status */}
        {document.status === 'completed' && document.category === 'adventure' && adventureModule?.parsing_status === 'processing' && (
          <div className="mb-3">
            <div className="flex justify-between mb-1">
              <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#c90]">Parsing adventure...</span>
              <span className="font-['IBM_Plex_Mono',monospace] text-[10px] text-[#6a6250]">{adventureModule.parsing_progress}%</span>
            </div>
            <div className="h-1 bg-[#0a0908] rounded overflow-hidden">
              <div
                className="h-full rounded transition-all"
                style={{
                  width: `${adventureModule.parsing_progress}%`,
                  background: 'linear-gradient(90deg, rgba(204,153,0,0.4), #c90)',
                }}
              />
            </div>
            {/* Live log tail during parsing */}
            {adventureModule.parsing_log && adventureModule.parsing_log.length > 0 && (
              <div className="mt-2">
                <div className="bg-[#0a0908] border border-[rgba(180,160,100,0.08)] rounded p-2 max-h-24 overflow-y-auto">
                  <div className="font-mono text-[10px] space-y-0.5">
                    {adventureModule.parsing_log.slice(-6).map((line, i) => (
                      <div
                        key={i}
                        className={
                          line.includes('ERROR') ? 'text-red-400' :
                          line.startsWith('Pass ') ? 'text-[#b8a060]' :
                          line.startsWith('  →') ? 'text-[#6a6250]' :
                          'text-[#5a5240]'
                        }
                      >
                        {line}
                      </div>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => setShowParsingLog(true)}
                  className="mt-1 text-[10px] font-['IBM_Plex_Mono',monospace] text-[#8a7a50] hover:text-[#c90] transition-colors"
                >
                  View full log
                </button>
              </div>
            )}
          </div>
        )}

        {/* Parsing failed retry */}
        {adventureModule?.parsing_status === 'failed' && (
          <div className="mb-3 flex items-center gap-2">
            <span className="font-['Crimson_Text',serif] text-xs text-red-400">Parsing failed</span>
            <button
              onClick={() => retryEmbeddingsMutation.mutate()}
              disabled={retryEmbeddingsMutation.isPending}
              className="px-2 py-0.5 text-xs rounded bg-red-600/20 text-red-400 hover:bg-red-600/30 border border-red-600/30"
            >
              {retryEmbeddingsMutation.isPending ? 'Retrying...' : 'Retry'}
            </button>
          </div>
        )}

        {/* Ready to parse prompt */}
        {document.status === 'completed' && document.category === 'adventure' && !adventureModule && (
          <button
            onClick={() => parseAdventureMutation.mutate()}
            disabled={parseAdventureMutation.isPending}
            className="mb-3 w-full py-2 rounded text-xs font-['Cinzel',serif] font-medium bg-[#b8a060] text-[#0f0d0a] hover:bg-[#d4b870] transition-colors disabled:opacity-50"
          >
            {parseAdventureMutation.isPending ? 'Parsing...' : 'Parse Adventure Content'}
          </button>
        )}

        {/* Processing error */}
        {document.processing_error && (
          <div className="text-red-400 text-xs font-['Crimson_Text',serif] mb-3">
            {document.processing_error}
          </div>
        )}

        {/* Parsing log modal */}
        {showParsingLog && adventureModule?.parsing_log && (
          <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setShowParsingLog(false)}>
            <div className="bg-[#141210] border border-[rgba(180,160,100,0.2)] rounded-lg p-4 max-w-2xl w-full max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-['Cinzel',serif] text-lg text-[#d4b870]">Parse Log</h3>
                <button onClick={() => setShowParsingLog(false)} className="text-[#6a6250] hover:text-[#c8c0aa]">✕</button>
              </div>
              <div className="bg-[#0a0908] border border-[rgba(180,160,100,0.1)] rounded p-3 max-h-[60vh] overflow-y-auto">
                <div className="font-mono text-xs space-y-1">
                  {adventureModule.parsing_log.map((line, i) => (
                    <div
                      key={i}
                      className={
                        line.startsWith('ERROR') ? 'text-red-400' :
                        line.startsWith('Stage') ? 'text-[#b8a060]' :
                        line.startsWith('  →') ? 'text-[#8a8270]' :
                        line.includes('complete') ? 'text-green-400' :
                        'text-[#6a6250]'
                      }
                    >
                      {line}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/* ─── MAIN PAGE ─── */

export function SourcebooksPage() {
  const [dragActive, setDragActive] = useState(false)
  const [selectedSystemId, setSelectedSystemId] = useState<string>('')
  const [filter, setFilter] = useState('all')
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  // Fetch RPG systems
  const { data: systems } = useQuery({
    queryKey: ['rpg-systems'],
    queryFn: () => api.get<RPGSystem[]>('/campaigns/systems'),
  })

  // Set default system when systems load
  const defaultSystem = systems?.find((s) => s.code === 'bx-dnd') || systems?.[0]
  if (systems && !selectedSystemId && defaultSystem) {
    setSelectedSystemId(defaultSystem.id)
  }

  const { data: documents, isLoading } = useQuery({
    queryKey: ['sourcebooks'],
    queryFn: () => api.get<PDFDocument[]>('/sourcebooks'),
    refetchInterval: (query) => {
      const docs = query.state.data
      if (docs?.some((d) => d.status === 'processing' || d.status === 'pending')) {
        return 3000
      }
      return false
    },
  })

  // Fetch adventure modules for all adventure documents
  const { data: adventureModules } = useQuery({
    queryKey: ['adventure-modules-all'],
    queryFn: async () => {
      const adventures = documents?.filter(d => d.category === 'adventure' && d.status === 'completed') || []
      const modules: AdventureModule[] = []
      for (const adv of adventures) {
        try {
          const module = await api.get<AdventureModule>(`/adventures/by-document/${adv.id}`)
          modules.push(module)
        } catch {
          // Module not parsed yet
        }
      }
      return modules
    },
    enabled: !!documents,
    refetchInterval: (query) => {
      const modules = query.state.data
      if (modules?.some(m => m.parsing_status === 'processing' || m.parsing_status === 'pending')) {
        return 1500
      }
      return false
    },
  })

  const getAdventureModule = (docId: string) => adventureModules?.find(m => m.pdf_document_id === docId) || null

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!selectedSystemId) {
        throw new Error('Please select an RPG System')
      }
      const formData = new FormData()
      formData.append('file', file)
      formData.append('rpg_system_id', selectedSystemId)
      return api.upload('/sourcebooks/upload', formData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourcebooks'] })
    },
  })

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    const files = Array.from(e.dataTransfer.files)
    const pdfFiles = files.filter((f) => f.type === 'application/pdf')
    pdfFiles.forEach((file) => uploadMutation.mutate(file))
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    files.forEach((file) => uploadMutation.mutate(file))
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  // Filter documents
  const filteredDocs = filter === 'all'
    ? documents
    : filter === 'uncategorized'
    ? documents?.filter(d => !d.category)
    : documents?.filter(d => d.category === filter)

  // Group by category
  const grouped = {
    uncategorized: (filteredDocs?.filter(d => !d.category) || []).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    adventure: (filteredDocs?.filter(d => d.category === 'adventure') || []).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    supplement: (filteredDocs?.filter(d => d.category === 'supplement') || []).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    rules: (filteredDocs?.filter(d => d.category === 'rules') || []).sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
  }

  const categories = ['all', 'adventure', 'supplement', 'rules']
  const uncategorizedCount = documents?.filter(d => !d.category).length || 0

  return (
    <>
      <style>{`
        @keyframes cardIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes dropGlow {
          0%, 100% { border-color: rgba(180,160,80,0.3); }
          50% { border-color: rgba(180,160,80,0.6); }
        }
        .filter-pill {
          background: none;
          border: 1px solid transparent;
          cursor: pointer;
          font-family: 'Crimson Text', serif;
          font-size: 14px;
          color: #6a6250;
          padding: 5px 14px;
          border-radius: 20px;
          transition: all 0.2s;
        }
        .filter-pill:hover { color: #8a8270; }
        .filter-pill.active {
          color: #b8a060;
          border-color: rgba(180,160,80,0.4);
          background: rgba(180,160,80,0.06);
        }
      `}</style>

      <div className="min-h-[calc(100vh-8rem)] flex" onClick={() => openMenu && setOpenMenu(null)}>
        {/* Left atmosphere panel - fixed */}
        <div
          className="hidden lg:block w-[30%] fixed left-0 top-16 bottom-0"
          style={{
            backgroundImage: 'url(/img/library.png)',
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-dungeon-900/60 via-dungeon-900/80 to-dungeon-900" />
        </div>

        {/* Right content panel */}
        <div className="flex-1 lg:w-[70%] lg:ml-[30%] px-6 lg:px-12 py-12 overflow-y-auto">
          <div className="max-w-3xl mx-auto lg:mx-0">
            {/* Page header */}
            <div className="mb-8 flex items-end justify-between">
              <div>
                <h1 className="font-['Cinzel',serif] text-4xl text-[#c8c0aa] tracking-wide mb-2">Library</h1>
                <p className="font-['Crimson_Text',serif] text-base text-[#6a6250] italic">
                  Your collection of adventure modules and reference material.
                </p>
              </div>
              <div className="flex gap-1">
                {categories.map(cat => (
                  <button
                    key={cat}
                    className={`filter-pill ${filter === cat ? 'active' : ''}`}
                    onClick={() => setFilter(cat)}
                  >
                    {cat === 'all' ? 'All' : cat === 'adventure' ? 'Adventures' : cat === 'supplement' ? 'Supplements' : 'Rulebooks'}
                  </button>
                ))}
              </div>
            </div>

            {/* Upload zone */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => !uploadMutation.isPending && fileInputRef.current?.click()}
              className="mb-10 p-7 rounded-lg cursor-pointer transition-all flex items-center gap-5"
              style={{
                border: `2px dashed ${dragActive ? '#b8a060' : 'rgba(180,160,100,0.12)'}`,
                background: dragActive ? 'rgba(180,160,80,0.04)' : 'transparent',
                animation: dragActive ? 'dropGlow 1s ease infinite' : 'none',
              }}
              onMouseEnter={(e) => { if (!dragActive) (e.currentTarget as HTMLElement).style.borderColor = 'rgba(180,160,100,0.2)' }}
              onMouseLeave={(e) => { if (!dragActive) (e.currentTarget as HTMLElement).style.borderColor = 'rgba(180,160,100,0.12)' }}
            >
              <input ref={fileInputRef} type="file" accept=".pdf" multiple onChange={handleFileSelect} className="hidden" />
              <div
                className="w-12 h-12 rounded-xl flex-shrink-0 flex items-center justify-center transition-all"
                style={{
                  background: dragActive ? 'rgba(180,160,80,0.12)' : 'rgba(255,245,220,0.03)',
                  border: `1px solid ${dragActive ? 'rgba(180,160,80,0.4)' : 'rgba(180,160,100,0.1)'}`,
                }}
              >
                <Upload className={`w-5 h-5 ${dragActive ? 'text-[#b8a060]' : 'text-[#6a6250]'}`} />
              </div>
              <div>
                <div className={`font-['Crimson_Text',serif] text-base mb-0.5 ${dragActive ? 'text-[#b8a060]' : 'text-[#c8c0aa]'}`}>
                  {dragActive ? 'Drop PDF to add to library' : uploadMutation.isPending ? 'Processing...' : 'Add to Library'}
                </div>
                <div className="font-['Crimson_Text',serif] text-sm text-[#6a6250]">
                  Drop PDF files here, or click to browse. Modules are parsed and indexed automatically.
                </div>
              </div>
            </div>

            {isLoading ? (
              <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">
                Loading sourcebooks...
              </div>
            ) : documents?.length === 0 ? (
              <div className="text-center py-16">
                <BookOpen className="w-12 h-12 text-[#6a6250] mx-auto mb-4 opacity-40" />
                <div className="font-['Cinzel',serif] text-xl text-[#8a8270] mb-2">The Shelves Are Empty</div>
                <div className="font-['Crimson_Text',serif] text-sm text-[#6a6250]">
                  Drop a PDF above to get started.
                </div>
              </div>
            ) : (
              <>
                {/* New Uploads (uncategorized) */}
                {grouped.uncategorized.length > 0 && (filter === 'all' || filter === 'uncategorized') && (
                  <div className="mb-10">
                    <div className="flex items-center gap-4 mb-5">
                      <h2 className="font-['Cinzel',serif] text-lg font-semibold text-[#8a8270] tracking-wide">
                        New Uploads
                      </h2>
                      <div className="flex-1 h-px bg-[rgba(180,160,100,0.1)]" />
                      <span className="font-['IBM_Plex_Mono',monospace] text-xs text-[#6a6250]">
                        {grouped.uncategorized.length} {grouped.uncategorized.length === 1 ? 'book' : 'books'}
                      </span>
                    </div>
                    <p className="font-['Crimson_Text',serif] text-sm text-[#6a6250] mb-4 -mt-3">
                      Set the type to organize these
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      {grouped.uncategorized.map((doc, i) => (
                        <ModuleCard
                          key={doc.id}
                          document={doc}
                          systems={systems || []}
                          adventureModule={getAdventureModule(doc.id)}
                          index={i}
                          menuOpen={openMenu === doc.id}
                          onMenuToggle={() => setOpenMenu(openMenu === doc.id ? null : doc.id)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Adventure Modules */}
                {grouped.adventure.length > 0 && (filter === 'all' || filter === 'adventure') && (
                  <div className="mb-10">
                    <div className="flex items-center gap-4 mb-5">
                      <h2 className="font-['Cinzel',serif] text-lg font-semibold text-[#8a8270] tracking-wide">
                        Adventure Modules
                      </h2>
                      <div className="flex-1 h-px bg-[rgba(180,160,100,0.1)]" />
                      <span className="font-['IBM_Plex_Mono',monospace] text-xs text-[#6a6250]">
                        {grouped.adventure.length} {grouped.adventure.length === 1 ? 'book' : 'books'}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      {grouped.adventure.map((doc, i) => (
                        <ModuleCard
                          key={doc.id}
                          document={doc}
                          systems={systems || []}
                          adventureModule={getAdventureModule(doc.id)}
                          index={i}
                          menuOpen={openMenu === doc.id}
                          onMenuToggle={() => setOpenMenu(openMenu === doc.id ? null : doc.id)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Supplements */}
                {grouped.supplement.length > 0 && (filter === 'all' || filter === 'supplement') && (
                  <div className="mb-10">
                    <div className="flex items-center gap-4 mb-5">
                      <h2 className="font-['Cinzel',serif] text-lg font-semibold text-[#8a8270] tracking-wide">
                        Supplements
                      </h2>
                      <div className="flex-1 h-px bg-[rgba(180,160,100,0.1)]" />
                      <span className="font-['IBM_Plex_Mono',monospace] text-xs text-[#6a6250]">
                        {grouped.supplement.length} {grouped.supplement.length === 1 ? 'book' : 'books'}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      {grouped.supplement.map((doc, i) => (
                        <ModuleCard
                          key={doc.id}
                          document={doc}
                          systems={systems || []}
                          adventureModule={getAdventureModule(doc.id)}
                          index={i}
                          menuOpen={openMenu === doc.id}
                          onMenuToggle={() => setOpenMenu(openMenu === doc.id ? null : doc.id)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Rulebooks */}
                {grouped.rules.length > 0 && (filter === 'all' || filter === 'rules') && (
                  <div className="mb-10">
                    <div className="flex items-center gap-4 mb-5">
                      <h2 className="font-['Cinzel',serif] text-lg font-semibold text-[#8a8270] tracking-wide">
                        Rulebooks
                      </h2>
                      <div className="flex-1 h-px bg-[rgba(180,160,100,0.1)]" />
                      <span className="font-['IBM_Plex_Mono',monospace] text-xs text-[#6a6250]">
                        {grouped.rules.length} {grouped.rules.length === 1 ? 'book' : 'books'}
                      </span>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                      {grouped.rules.map((doc, i) => (
                        <ModuleCard
                          key={doc.id}
                          document={doc}
                          systems={systems || []}
                          adventureModule={getAdventureModule(doc.id)}
                          index={i}
                          menuOpen={openMenu === doc.id}
                          onMenuToggle={() => setOpenMenu(openMenu === doc.id ? null : doc.id)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* Empty filtered state */}
                {filteredDocs?.length === 0 && filter !== 'all' && (
                  <div className="text-center py-16">
                    <div className="text-4xl mb-3 opacity-30">📚</div>
                    <div className="font-['Crimson_Text',serif] text-base text-[#6a6250]">
                      No {filter === 'adventure' ? 'adventures' : filter === 'supplement' ? 'supplements' : 'rulebooks'} in your library yet.
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
