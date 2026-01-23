import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, BookOpen, CheckCircle, XCircle, Loader, Trash2, RefreshCw, Wand2, ChevronDown, ChevronUp } from 'lucide-react'
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
    <div className="relative lg:pl-[20%]">
      {/* Decorative side image with fade */}
      <div
        className="fixed left-0 top-0 w-1/3 h-full pointer-events-none z-0 hidden lg:block"
        style={{
          backgroundImage: 'url(/img/library.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center right',
          maskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
        }}
      />

      <h1 className="font-display text-4xl text-parchment-100 mb-8">Sourcebooks</h1>

      {/* Upload area */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={`card border-2 border-dashed mb-8 p-8 text-center transition-colors ${
          dragActive
            ? 'border-parchment-500 bg-dungeon-700'
            : 'border-dungeon-600 hover:border-parchment-600'
        }`}
      >
        <Upload className="w-12 h-12 text-parchment-500 mx-auto mb-4" />
        <h2 className="font-display text-xl text-parchment-100 mb-2">
          Upload Sourcebooks
        </h2>
        <p className="text-parchment-400 mb-4">
          Drag and drop PDF files here, or click to browse
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          multiple
          onChange={handleFileSelect}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="btn btn-primary"
          disabled={uploadMutation.isPending}
        >
          {uploadMutation.isPending ? 'Uploading...' : 'Browse Files'}
        </button>
      </div>

      {/* Document list */}
      {isLoading ? (
        <div className="text-center text-parchment-400 py-12">
          Loading sourcebooks...
        </div>
      ) : documents?.length === 0 ? (
        <div className="card text-center py-12">
          <BookOpen className="w-16 h-16 text-parchment-500 mx-auto mb-4" />
          <h2 className="font-display text-2xl text-parchment-100 mb-2">No Sourcebooks Yet</h2>
          <p className="text-parchment-400">
            Upload your B/X D&D or OSR rulebooks and adventures to enable rule-accurate gameplay.
          </p>
          <p className="text-parchment-500 text-sm mt-2">
            Supports Basic/Expert D&D, Old-School Essentials, Labyrinth Lord, and other OSR retroclones.
          </p>
        </div>
      ) : (
        <>
          {/* Group by Category/Type */}
          {[
            { key: 'adventure', label: 'Adventure Modules' },
            { key: 'rules', label: 'Rulebooks' },
            { key: 'supplement', label: 'Supplements' },
            { key: null, label: 'Uncategorized' },
          ].map(({ key, label }) => {
            const categoryDocs = documents?.filter(d => d.category === key) || []
            if (categoryDocs.length === 0) return null

            return (
              <div key={key || 'uncategorized'} className="mb-8">
                <h2 className="font-display text-2xl text-parchment-100 mb-4">{label}</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
    <div className="card overflow-hidden">
      {/* Cover Image */}
      <div className="relative -mx-6 -mt-6 mb-3 h-32 bg-dungeon-900">
        <img
          src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/api/v1/sourcebooks/${document.id}/cover`}
          alt="Cover"
          className="w-full h-full object-cover opacity-80"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none'
          }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <BookOpen className="w-12 h-12 text-parchment-600 opacity-30" />
        </div>
        <div className="absolute inset-0 bg-gradient-to-t from-dungeon-800 to-transparent" />
        {/* Status badge */}
        <div className="absolute top-2 right-2">
          <StatusIcon
            className={`w-5 h-5 ${statusColor} ${
              document.status === 'processing' || document.status === 'pending' ? 'animate-spin' : ''
            }`}
          />
        </div>
      </div>

      {/* Title */}
      <h3 className="text-parchment-100 font-semibold text-sm truncate mb-1" title={document.title || document.original_filename}>
        {document.title || document.original_filename}
      </h3>
      <div className="text-parchment-500 text-xs mb-2">
        {document.page_count && `${document.page_count} pages`}
        {document.chunk_count > 0 && ` • ${document.chunk_count} chunks`}
      </div>

      {/* Description */}
      {isEditingDescription ? (
        <div className="mb-2">
          <textarea
            value={descriptionInput}
            onChange={(e) => setDescriptionInput(e.target.value)}
            placeholder="Add a brief description..."
            className="w-full bg-dungeon-700 border border-dungeon-600 text-parchment-200 text-xs rounded px-2 py-1 resize-none"
            rows={2}
            autoFocus
          />
          <div className="flex gap-1 mt-1">
            <button
              onClick={() => updateMutation.mutate({ description: descriptionInput })}
              disabled={updateMutation.isPending}
              className="px-2 py-0.5 text-xs bg-green-700 text-white rounded hover:bg-green-600"
            >
              Save
            </button>
            <button
              onClick={() => {
                setIsEditingDescription(false)
                setDescriptionInput(document.description || '')
              }}
              className="px-2 py-0.5 text-xs text-parchment-400 hover:text-parchment-200"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div
          onClick={() => setIsEditingDescription(true)}
          className="text-parchment-400 text-xs mb-2 cursor-pointer hover:text-parchment-300 min-h-[1.5rem]"
          title="Click to edit description"
        >
          {document.description || <span className="text-parchment-600 italic">Click to add description...</span>}
        </div>
      )}

      {/* Controls row */}
      <div className="flex items-center gap-1 mb-2">
        <select
          value={document.category || ''}
          onChange={(e) => updateMutation.mutate({ category: e.target.value })}
          className="flex-1 bg-dungeon-700 border border-dungeon-600 text-parchment-200 text-xs rounded px-1 py-1"
        >
          <option value="">Type...</option>
          <option value="rules">Rulebook</option>
          <option value="adventure">Adventure</option>
          <option value="supplement">Supplement</option>
        </select>
        <button
          onClick={() => reprocessMutation.mutate()}
          disabled={reprocessMutation.isPending || document.status === 'processing' || document.status === 'pending'}
          className="p-1.5 text-parchment-400 hover:text-blue-400 hover:bg-dungeon-700 rounded transition-colors disabled:opacity-50"
          title="Rescan"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${reprocessMutation.isPending ? 'animate-spin' : ''}`} />
        </button>
        <button
          onClick={() => setShowDeleteConfirm(true)}
          disabled={deleteMutation.isPending}
          className="p-1.5 text-parchment-400 hover:text-red-400 hover:bg-dungeon-700 rounded transition-colors"
          title="Delete"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {document.processing_error && (
        <div className="text-red-400 text-sm mt-2">{document.processing_error}</div>
      )}

      {/* Adventure parsing section - only shown for adventure documents */}
      {document.status === 'completed' && document.category === 'adventure' && (
        <div className="mt-2 pt-2 border-t border-dungeon-600">
          {/* Status line */}
          <div className="flex items-center gap-2 mb-2">
            <Wand2 className="w-4 h-4 text-purple-400 flex-shrink-0" />
            {adventureModule?.parsing_status === 'completed' && (
              <span className="text-green-400 text-xs">{adventureModule.location_count} loc, {adventureModule.npc_count} NPCs</span>
            )}
            {adventureModule?.parsing_status === 'processing' && (
              <span className="text-blue-400 text-xs flex items-center gap-1">
                <Loader className="w-3 h-3 animate-spin" />
                {adventureModule.parsing_progress}%
              </span>
            )}
            {adventureModule?.parsing_status === 'failed' && (
              <span className="text-red-400 text-xs truncate" title={adventureModule.parsing_error || ''}>Failed</span>
            )}
            {!adventureModule && (
              <span className="text-parchment-500 text-xs">Not parsed</span>
            )}
          </div>

          {/* Buttons */}
          <div className="flex flex-wrap gap-1">
            {adventureModule?.parsing_log && adventureModule.parsing_log.length > 0 && (
              <button
                onClick={() => setShowParsingLog(!showParsingLog)}
                className="px-2 py-1 text-xs text-parchment-400 hover:text-parchment-200 border border-dungeon-600 rounded"
              >
                {showParsingLog ? 'Hide' : 'Log'}
              </button>
            )}
            {adventureModule?.parsing_status === 'failed' && (
              <button
                onClick={() => retryEmbeddingsMutation.mutate()}
                disabled={retryEmbeddingsMutation.isPending}
                className="px-2 py-1 text-xs rounded bg-blue-700 text-white hover:bg-blue-600 disabled:opacity-50"
              >
                {retryEmbeddingsMutation.isPending ? '...' : 'Retry'}
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
              className={`px-2 py-1 text-xs rounded ${
                adventureModule?.parsing_status === 'completed'
                  ? 'bg-dungeon-700 text-parchment-300 hover:bg-dungeon-600'
                  : 'bg-purple-700 text-white hover:bg-purple-600'
              } disabled:opacity-50`}
            >
              {parseAdventureMutation.isPending || adventureModule?.parsing_status === 'processing'
                ? '...'
                : adventureModule?.parsing_status === 'completed'
                ? 'Re-parse'
                : 'Parse'}
            </button>
          </div>

          {/* Parsing log - auto-show during processing */}
          {(showParsingLog || adventureModule?.parsing_status === 'processing') && adventureModule?.parsing_log && adventureModule.parsing_log.length > 0 && (
            <div className="mt-3 bg-dungeon-900 border border-dungeon-700 rounded p-3 max-h-64 overflow-y-auto">
              <div className="font-mono text-xs space-y-1">
                {adventureModule.parsing_log.map((line, index) => (
                  <div
                    key={index}
                    className={`${
                      line.startsWith('ERROR') ? 'text-red-400' :
                      line.startsWith('Stage') ? 'text-purple-400' :
                      line.startsWith('  →') ? 'text-parchment-400' :
                      line.includes('complete') ? 'text-green-400' :
                      'text-parchment-500'
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

      {/* Delete confirmation modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-dungeon-800 border border-dungeon-600 rounded-lg p-6 max-w-md mx-4 shadow-xl">
            <h3 className="text-parchment-100 font-display text-lg mb-2">Delete Sourcebook?</h3>
            <p className="text-parchment-300 text-sm mb-4">
              Are you sure you want to delete <span className="text-parchment-100 font-semibold">{document.title || document.original_filename}</span>?
              This will remove all indexed content and cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-sm text-parchment-300 hover:text-parchment-100 transition-colors"
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
