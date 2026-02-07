import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, BookOpen, CheckCircle, XCircle, Loader, Trash2, RefreshCw, Wand2 } from 'lucide-react'
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

// Map system codes to short display names
const SYSTEM_SHORT_NAMES: Record<string, string> = {
  'bx-dnd': 'B/X D&D',
  'osr-dnd': 'OSR',
}

export function SourcebooksPage() {
  const [dragActive, setDragActive] = useState(false)
  const [selectedSystemId, setSelectedSystemId] = useState<string>('')
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
      // Refetch every 3 seconds if any document is processing
      const docs = query.state.data
      if (docs?.some((d) => d.status === 'processing' || d.status === 'pending')) {
        return 3000
      }
      return false
    },
  })

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

  return (
    <div className="min-h-[calc(100vh-8rem)] flex">
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
      <div className="max-w-2xl mx-auto lg:mx-0">
        <div className="mb-8">
          <h1 className="font-['Cinzel',serif] text-4xl text-[#d4b870] mb-2">Library</h1>
          <p className="text-[#6a6250] text-sm font-['Crimson_Text',serif]">
            Stored adventure modules and reference material. Only PDFs you provide are used in play.
          </p>
        </div>

      {/* Upload area */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => !uploadMutation.isPending && fileInputRef.current?.click()}
        className={`bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 mb-8 cursor-pointer transition-all ${
          dragActive
            ? 'border-[#b8a060] bg-[rgba(180,160,80,0.06)]'
            : 'hover:border-[rgba(180,160,100,0.2)]'
        }`}
      >
        <div className="flex items-center gap-5">
          <div className="p-4 rounded-lg bg-[#0f0d0a]">
            <Upload className="w-8 h-8 text-[#b8a060]" />
          </div>
          <div className="flex-1">
            <h2 className="font-['Cinzel',serif] text-xl text-[#d4b870] mb-1">
              Add to Library
            </h2>
            <p className="text-[#8a8270] text-sm font-['Crimson_Text',serif]">
              {dragActive ? (
                <span className="text-[#c8c0aa]">Release to upload</span>
              ) : uploadMutation.isPending ? (
                'Processing...'
              ) : (
                'Drop PDF files here, or click to browse'
              )}
            </p>
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          multiple
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      {/* Document list */}
      {isLoading ? (
        <div className="text-center text-[#8a8270] py-12 font-['Crimson_Text',serif]">
          Loading sourcebooks...
        </div>
      ) : documents?.length === 0 ? (
        <div className="bg-[#141210] border border-[rgba(180,160,100,0.1)] rounded-lg p-6 text-center py-12">
          <BookOpen className="w-16 h-16 text-[#6a6250] mx-auto mb-4" />
          <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-2">The Shelves Are Empty</h2>
          <p className="text-[#8a8270] font-['Crimson_Text',serif]">
            Add your rulebooks and adventure modules to begin.
          </p>
          <p className="text-[#6a6250] text-sm mt-2 font-['Crimson_Text',serif]">
            Compatible with B/X, Old-School Essentials, and similar retroclones.
          </p>
        </div>
      ) : (
        <>
          {/* Group by Category/Type - New Uploads first so users see them immediately */}
          {[
            { key: null, label: 'New Uploads', description: 'Set the type to organize these' },
            { key: 'adventure', label: 'Adventure Modules' },
            { key: 'rules', label: 'Rulebooks' },
            { key: 'supplement', label: 'Supplements' },
          ].map(({ key, label, description }) => {
            const categoryDocs = (documents?.filter(d => d.category === key) || [])
              // Sort by created_at descending (newest first)
              .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
            if (categoryDocs.length === 0) return null

            return (
              <div key={key || 'uncategorized'} className="mb-8">
                <h2 className="font-['Cinzel',serif] text-2xl text-[#d4b870] mb-1">{label}</h2>
                {description && <p className="text-[#6a6250] text-sm mb-3 font-['Crimson_Text',serif]">{description}</p>}
                <div className="space-y-4">
                  {categoryDocs.map((doc) => (
                    <DocumentCard key={doc.id} document={doc} systems={systems || []} />
                  ))}
                </div>
              </div>
            )
          })}
        </>
      )}
      </div>
      </div>
    </div>
  )
}

function DocumentCard({ document, systems }: { document: PDFDocument; systems: RPGSystem[] }) {
  const queryClient = useQueryClient()
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showParsingLog, setShowParsingLog] = useState(false)
  const [isEditingDescription, setIsEditingDescription] = useState(false)
  const [descriptionInput, setDescriptionInput] = useState(document.description || '')

  // Query for adventure parsing status
  const { data: adventureModule } = useQuery({
    queryKey: ['adventure-module', document.id],
    queryFn: () => api.get<AdventureModule>(`/adventures/by-document/${document.id}`).catch(() => null),
    enabled: document.status === 'completed' && document.category === 'adventure',
    refetchInterval: (query) => {
      const module = query.state.data
      if (module && (module.parsing_status === 'pending' || module.parsing_status === 'processing')) {
        return 1500 // Refetch every 1.5 seconds while parsing for live updates
      }
      return false
    },
  })

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
      setShowDeleteConfirm(false)
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
      queryClient.invalidateQueries({ queryKey: ['adventure-module', document.id] })
    },
  })

  const retryEmbeddingsMutation = useMutation({
    mutationFn: () => api.post(`/adventures/${document.id}/embeddings`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adventure-module', document.id] })
    },
  })

  const StatusIcon = {
    pending: Loader,
    processing: Loader,
    completed: CheckCircle,
    failed: XCircle,
  }[document.status]

  const statusColor = {
    pending: 'text-yellow-500',
    processing: 'text-blue-500',
    completed: 'text-green-500',
    failed: 'text-red-500',
  }[document.status]

  return (
    <div className="bg-[#141210] border border-[rgba(180,160,100,0.15)] rounded-lg overflow-hidden hover:border-[rgba(180,160,100,0.3)] transition-colors">
      <div className="flex">
        {/* Cover Image - Left side */}
        <div className="relative w-32 min-h-[140px] flex-shrink-0 bg-dungeon-900">
          <img
            src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/sourcebooks/${document.id}/cover`}
            alt="Cover"
            className="w-full h-full object-cover opacity-90"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none'
            }}
          />
          <div className="absolute inset-0 flex items-center justify-center">
            <BookOpen className="w-10 h-10 text-parchment-600 opacity-30" />
          </div>
          {/* Status badge */}
          <div className="absolute top-2 left-2">
            <StatusIcon
              className={`w-5 h-5 ${statusColor} ${
                document.status === 'processing' || document.status === 'pending' ? 'animate-spin' : ''
              }`}
            />
          </div>
        </div>

        {/* Content - Right side */}
        <div className="flex-1 p-4">
          {/* Title */}
          <h3 className="text-[#d4b870] font-['Cinzel',serif] text-lg mb-1 truncate" title={document.title || document.original_filename}>
            {document.title || document.original_filename}
          </h3>
          <div className="text-[#6a6250] text-xs mb-2 font-['Crimson_Text',serif]">
            {document.page_count && `${document.page_count} pages`}
            {document.chunk_count > 0 && ` • ${document.chunk_count} chunks indexed`}
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
          ) : (
            <div
              onClick={() => setIsEditingDescription(true)}
              className="text-[#8a8270] text-sm mb-3 cursor-pointer hover:text-[#c8c0aa] font-['Crimson_Text',serif] line-clamp-2"
              title="Click to edit description"
            >
              {document.description || <span className="text-[#5a5245] italic">Click to add description...</span>}
            </div>
          )}

          {/* Controls row */}
          <div className="flex items-center gap-2">
            <select
              value={document.category || ''}
              onChange={(e) => updateMutation.mutate({ category: e.target.value })}
              className="bg-[#0f0d0a] border border-[rgba(180,160,100,0.2)] text-[#c8c0aa] text-xs rounded px-2 py-1.5"
            >
              <option value="">Set type...</option>
              <option value="rules">Rulebook</option>
              <option value="adventure">Adventure</option>
              <option value="supplement">Supplement</option>
            </select>
            <button
              onClick={() => reprocessMutation.mutate()}
              disabled={reprocessMutation.isPending || document.status === 'processing' || document.status === 'pending'}
              className="p-1.5 text-[#6a6250] hover:text-[#b8a060] hover:bg-[#0f0d0a] rounded transition-colors disabled:opacity-50"
              title="Rescan PDF"
            >
              <RefreshCw className={`w-4 h-4 ${reprocessMutation.isPending ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              disabled={deleteMutation.isPending}
              className="p-1.5 text-[#6a6250] hover:text-red-400 hover:bg-[#0f0d0a] rounded transition-colors"
              title="Delete"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Adventure parsing section - shown below the main card content */}
      {document.status === 'completed' && document.category === 'adventure' && (
        <div className="px-4 py-3 border-t border-[rgba(180,160,100,0.1)] bg-[#0f0d0a]">
          <div className="flex items-center justify-between">
            {/* Status line */}
            <div className="flex items-center gap-2">
              <Wand2 className="w-4 h-4 text-[#b8a060]" />
              {adventureModule?.parsing_status === 'completed' && (
                <span className="text-green-400 text-xs font-['Crimson_Text',serif]">
                  {adventureModule.location_count} locations, {adventureModule.npc_count} NPCs, {adventureModule.encounter_count} encounters
                </span>
              )}
              {adventureModule?.parsing_status === 'processing' && (
                <span className="text-blue-400 text-xs flex items-center gap-1">
                  <Loader className="w-3 h-3 animate-spin" />
                  Parsing... {adventureModule.parsing_progress}%
                </span>
              )}
              {adventureModule?.parsing_status === 'failed' && (
                <span className="text-red-400 text-xs" title={adventureModule.parsing_error || ''}>Parsing failed</span>
              )}
              {!adventureModule && (
                <span className="text-[#6a6250] text-xs font-['Crimson_Text',serif]">Ready to parse adventure content</span>
              )}
            </div>

            {/* Buttons */}
            <div className="flex gap-2">
              {adventureModule?.parsing_log && adventureModule.parsing_log.length > 0 && (
                <button
                  onClick={() => setShowParsingLog(!showParsingLog)}
                  className="px-2 py-1 text-xs text-[#8a8270] hover:text-[#c8c0aa] border border-[rgba(180,160,100,0.2)] rounded"
                >
                  {showParsingLog ? 'Hide Log' : 'Show Log'}
                </button>
              )}
              {adventureModule?.parsing_status === 'failed' && (
                <button
                  onClick={() => retryEmbeddingsMutation.mutate()}
                  disabled={retryEmbeddingsMutation.isPending}
                  className="px-3 py-1 text-xs rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
                >
                  {retryEmbeddingsMutation.isPending ? 'Retrying...' : 'Retry'}
                </button>
              )}
              <button
                onClick={() => parseAdventureMutation.mutate()}
                disabled={
                  parseAdventureMutation.isPending ||
                  retryEmbeddingsMutation.isPending ||
                  adventureModule?.parsing_status === 'processing' ||
                  adventureModule?.parsing_status === 'pending'
                }
                className={`px-3 py-1 text-xs rounded font-medium ${
                  adventureModule?.parsing_status === 'completed'
                    ? 'bg-[#1a1816] text-[#8a8270] hover:text-[#c8c0aa] border border-[rgba(180,160,100,0.2)]'
                    : 'bg-[#b8a060] text-[#0f0d0a] hover:bg-[#d4b870]'
                } disabled:opacity-50`}
              >
                {parseAdventureMutation.isPending || adventureModule?.parsing_status === 'processing'
                  ? 'Parsing...'
                  : adventureModule?.parsing_status === 'completed'
                  ? 'Re-parse'
                  : 'Parse Adventure'}
              </button>
            </div>
          </div>

          {/* Parsing log - auto-show during processing */}
          {(showParsingLog || adventureModule?.parsing_status === 'processing') && adventureModule?.parsing_log && adventureModule.parsing_log.length > 0 && (
            <div className="mt-3 bg-[#0a0908] border border-[rgba(180,160,100,0.1)] rounded p-3 max-h-64 overflow-y-auto">
              <div className="font-mono text-xs space-y-1">
                {adventureModule.parsing_log.map((line, index) => (
                  <div
                    key={index}
                    className={`${
                      line.startsWith('ERROR') ? 'text-red-400' :
                      line.startsWith('Stage') ? 'text-[#b8a060]' :
                      line.startsWith('  →') ? 'text-[#8a8270]' :
                      line.includes('complete') ? 'text-green-400' :
                      'text-[#6a6250]'
                    }`}
                  >
                    {line}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {document.processing_error && (
        <div className="px-4 py-2 text-red-400 text-sm bg-[#1a0a0a]">{document.processing_error}</div>
      )}

      {/* Delete confirmation modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#1a1816] border border-[rgba(180,160,100,0.2)] rounded-lg p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-[#d4b870] font-['Cinzel',serif] text-xl mb-3">Delete Sourcebook?</h3>
            <p className="text-[#c8c0aa] text-sm mb-5 font-['Crimson_Text',serif]">
              Are you sure you want to delete <span className="text-[#d4b870] font-semibold">{document.title || document.original_filename}</span>?
              This will remove all indexed content and cannot be undone.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-sm text-[#8a8270] hover:text-[#c8c0aa] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 text-sm bg-red-700 hover:bg-red-600 text-white rounded transition-colors"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
