import { useState, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Users, Map, Scroll, ExternalLink, CheckCircle, Loader } from 'lucide-react'
import { api } from '@/services/api'

interface RPGSystem {
  id: string
  name: string
  code: string
}

export function HomePage() {
  const [dragActive, setDragActive] = useState(false)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  // Fetch RPG systems to get the default B/X system ID
  const { data: systems } = useQuery({
    queryKey: ['rpg-systems'],
    queryFn: () => api.get<RPGSystem[]>('/campaigns/systems'),
  })

  const defaultSystemId = systems?.find((s) => s.code === 'bx-dnd')?.id || systems?.[0]?.id

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!defaultSystemId) {
        throw new Error('System not loaded yet')
      }
      const formData = new FormData()
      formData.append('file', file)
      formData.append('rpg_system_id', defaultSystemId)
      formData.append('category', 'adventure')
      return api.upload('/sourcebooks/upload', formData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sourcebooks'] })
      setUploadSuccess(true)
      // Navigate to sourcebooks after brief delay to show success
      setTimeout(() => navigate('/sourcebooks'), 1500)
    },
  })

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)

    const files = Array.from(e.dataTransfer.files)
    const pdfFiles = files.filter((f) => f.type === 'application/pdf')
    if (pdfFiles.length > 0) {
      uploadMutation.mutate(pdfFiles[0])
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) {
      uploadMutation.mutate(files[0])
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <div className="relative max-w-4xl mx-auto">
      {/* Left side background image with fade */}
      <div
        className="fixed left-0 top-0 w-1/3 h-full pointer-events-none z-0"
        style={{
          backgroundImage: 'url(/img/forgottenheroesoftherealm.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center right',
          maskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
          WebkitMaskImage: 'linear-gradient(to right, rgba(0,0,0,0.4) 0%, rgba(0,0,0,0.2) 50%, transparent 100%)',
        }}
      />
      <div className="relative z-10 text-center mb-12">
        <h1 className="font-display text-5xl text-parchment-100 mb-4">
          OSR Classic Solo Adventures
        </h1>
        <p className="text-parchment-300 text-xl mb-2">
          Play classic adventure modules solo with an AI Dungeon Master
        </p>
        <p className="text-parchment-500 text-sm mb-2">
          Bring-your-own-PDFs • Based on open and free OSR rules
        </p>
        <p className="text-parchment-600 text-xs">
          Powered by Old-School Essentials (free SRD) and Black Streams: Solo Heroes (free!)
        </p>
      </div>

      {/* Primary CTA - Upload Adventure with drag-drop */}
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => !uploadMutation.isPending && !uploadSuccess && fileInputRef.current?.click()}
        className={`card mb-8 border-2 border-dashed cursor-pointer transition-all ${
          uploadSuccess
            ? 'bg-green-900/30 border-green-500'
            : dragActive
            ? 'bg-purple-900/40 border-purple-400 scale-[1.02]'
            : 'bg-gradient-to-br from-purple-900/30 to-dungeon-800 border-purple-700 hover:border-purple-500'
        }`}
      >
        <div className="flex items-center space-x-6">
          <div className={`p-5 rounded-lg ${uploadSuccess ? 'bg-green-800' : 'bg-purple-800'}`}>
            {uploadSuccess ? (
              <CheckCircle className="w-10 h-10 text-green-200" />
            ) : uploadMutation.isPending ? (
              <Loader className="w-10 h-10 text-purple-200 animate-spin" />
            ) : (
              <Upload className="w-10 h-10 text-purple-200" />
            )}
          </div>
          <div className="flex-1">
            <h2 className="font-display text-2xl text-parchment-100 mb-1">
              {uploadSuccess
                ? 'Upload Complete!'
                : uploadMutation.isPending
                ? 'Uploading...'
                : 'Upload Your Adventure Module'}
            </h2>
            <p className="text-parchment-400">
              {uploadSuccess ? (
                'Redirecting to sourcebooks...'
              ) : uploadMutation.isPending ? (
                'Processing your PDF...'
              ) : dragActive ? (
                <span className="text-purple-300">Drop your PDF here!</span>
              ) : (
                <>
                  Drag and drop a B/X adventure module PDF here, or click to browse.
                  <span className="block text-parchment-500 text-sm mt-1">
                    Examples: B2 Keep on the Borderlands, B4 The Lost City, etc.
                  </span>
                </>
              )}
            </p>
            {uploadMutation.isError && (
              <p className="text-red-400 text-sm mt-2">
                Error: {(uploadMutation.error as Error).message}
              </p>
            )}
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
        <Link to="/characters" className="card hover:border-parchment-500 transition-colors group">
          <div className="flex items-center space-x-4">
            <div className="bg-dungeon-700 p-4 rounded-lg group-hover:bg-dungeon-600">
              <Users className="w-8 h-8 text-parchment-500" />
            </div>
            <div>
              <h2 className="font-display text-xl text-parchment-100">Characters</h2>
              <p className="text-parchment-400 text-sm">Create your hero</p>
            </div>
          </div>
        </Link>

        <Link to="/campaigns" className="card hover:border-parchment-500 transition-colors group">
          <div className="flex items-center space-x-4">
            <div className="bg-dungeon-700 p-4 rounded-lg group-hover:bg-dungeon-600">
              <Map className="w-8 h-8 text-parchment-500" />
            </div>
            <div>
              <h2 className="font-display text-xl text-parchment-100">Campaigns</h2>
              <p className="text-parchment-400 text-sm">Start adventures</p>
            </div>
          </div>
        </Link>

        <Link to="/sourcebooks" className="card hover:border-parchment-500 transition-colors group">
          <div className="flex items-center space-x-4">
            <div className="bg-dungeon-700 p-4 rounded-lg group-hover:bg-dungeon-600">
              <Scroll className="w-8 h-8 text-parchment-500" />
            </div>
            <div>
              <h2 className="font-display text-xl text-parchment-100">Sourcebooks</h2>
              <p className="text-parchment-400 text-sm">Manage PDFs</p>
            </div>
          </div>
        </Link>
      </div>

      {/* How It Works */}
      <div className="card mb-8">
        <h2 className="font-display text-2xl text-parchment-100 mb-4">How It Works</h2>
        <ol className="list-decimal list-inside space-y-3 text-parchment-300">
          <li><strong className="text-parchment-200">Upload</strong> your adventure module PDF (B/X, OSE, or compatible)</li>
          <li><strong className="text-parchment-200">Parse</strong> the module to extract locations, NPCs, and encounters</li>
          <li><strong className="text-parchment-200">Create</strong> a character using the classic race-as-class system</li>
          <li><strong className="text-parchment-200">Play</strong> with the AI Dungeon Master guiding you through the adventure</li>
        </ol>
        <p className="text-parchment-500 text-sm mt-4">
          Combat uses Solo Heroes rules (2d6 damage, Fray die for weak enemies). All dice rolls are automatic.
        </p>
      </div>

      {/* Rules Systems */}
      <div className="card">
        <h2 className="font-display text-2xl text-parchment-100 mb-4">Rules & Resources</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <a
            href="https://necroticgnome.com/pages/about-old-school-essentials"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center p-3 bg-dungeon-900 rounded border border-dungeon-700 hover:border-parchment-600 transition-colors"
          >
            <div className="flex-1">
              <div className="text-parchment-200 font-semibold">Old-School Essentials</div>
              <div className="text-parchment-500 text-sm">Core rules for B/X gameplay</div>
            </div>
            <ExternalLink className="w-4 h-4 text-parchment-500" />
          </a>
          <a
            href="https://www.drivethrurpg.com/en/product/114895/black-streams-solo-heroes"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center p-3 bg-dungeon-900 rounded border border-dungeon-700 hover:border-parchment-600 transition-colors"
          >
            <div className="flex-1">
              <div className="text-parchment-200 font-semibold">Black Streams: Solo Heroes</div>
              <div className="text-parchment-500 text-sm">Solo play mechanics (free!)</div>
            </div>
            <ExternalLink className="w-4 h-4 text-parchment-500" />
          </a>
        </div>
        <p className="text-parchment-500 text-sm mt-4">
          Compatible with B/X D&D, Old-School Essentials, Labyrinth Lord, and other OSR retroclones.
        </p>
      </div>
    </div>
  )
}
