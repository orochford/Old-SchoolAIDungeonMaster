import { useState, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, CheckCircle, Loader, ChevronRight } from 'lucide-react'
import { api } from '@/services/api'

interface RPGSystem {
  id: string
  name: string
  code: string
}

interface Session {
  id: string
  campaign_id: string
  character_id: string
  updated_at: string
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

  // Fetch the most recent session to enable "Enter the World"
  const { data: recentSessions } = useQuery({
    queryKey: ['sessions', 'recent'],
    queryFn: () => api.get<Session[]>('/sessions?limit=1'),
  })

  const lastSession = recentSessions?.[0]
  const canEnterWorld = !!lastSession

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
    <div className="min-h-[calc(100vh-8rem)] flex">
      {/* Left atmosphere panel */}
      <div
        className="hidden lg:block w-[30%] relative"
        style={{
          backgroundImage: 'url(/img/forgottenheroesoftherealm.png)',
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        <div className="absolute inset-0 bg-gradient-to-r from-dungeon-900/60 via-dungeon-900/80 to-dungeon-900" />
      </div>

      {/* Right interaction panel */}
      <div className="flex-1 lg:w-[70%] px-6 lg:px-12 py-12 overflow-y-auto">
        <div className="max-w-xl mx-auto lg:mx-0">
          {/* Hero */}
          <header className="mb-12">
            <h1 className="font-display text-4xl lg:text-5xl text-parchment-100 mb-3">
              OSR Classic Solo Adventures
            </h1>
            <p className="text-parchment-300 text-lg mb-2">
              Play classic adventure modules solo, guided by an impartial Dungeon Master.
            </p>
            <p className="text-parchment-500 text-sm">
              Compatible with B/X, Old-School Essentials, and most OSR modules.
            </p>
          </header>

          {/* Begin Adventure Panel */}
          <section className="mb-14">
            <div
              onDragOver={(e) => {
                e.preventDefault()
                setDragActive(true)
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={handleDrop}
              onClick={() => !uploadMutation.isPending && !uploadSuccess && fileInputRef.current?.click()}
              className={`ritual-panel cursor-pointer transition-all ${
                uploadSuccess
                  ? 'border-parchment-600/50'
                  : dragActive
                  ? 'border-parchment-500/50 bg-dungeon-700/90'
                  : 'hover:border-parchment-600/40'
              }`}
            >
              <div className="flex items-start gap-5">
                <div className={`p-4 rounded-lg ${uploadSuccess ? 'bg-parchment-700/20' : 'bg-dungeon-600'}`}>
                  {uploadSuccess ? (
                    <CheckCircle className="w-8 h-8 text-parchment-500" />
                  ) : uploadMutation.isPending ? (
                    <Loader className="w-8 h-8 text-parchment-400 animate-spin" />
                  ) : (
                    <Upload className="w-8 h-8 text-parchment-400" />
                  )}
                </div>
                <div className="flex-1">
                  <h2 className="font-display text-xl text-parchment-100 mb-2">
                    {uploadSuccess
                      ? 'Module Received'
                      : uploadMutation.isPending
                      ? 'Processing...'
                      : 'Begin an Adventure'}
                  </h2>
                  <p className="text-parchment-400 text-sm leading-relaxed">
                    {uploadSuccess ? (
                      'Proceeding to library...'
                    ) : uploadMutation.isPending ? (
                      'Reading the adventure...'
                    ) : dragActive ? (
                      <span className="text-parchment-300">Release to upload</span>
                    ) : (
                      <>
                        Place an adventure module PDF here, or choose one already in your library.
                        <span className="block text-parchment-500 mt-1">
                          B/X and compatible formats are recommended.
                        </span>
                      </>
                    )}
                  </p>
                  {uploadMutation.isError && (
                    <p className="text-red-400 text-sm mt-2">
                      {(uploadMutation.error as Error).message}
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

            <p className="text-parchment-500 text-sm mt-4 text-center">
              or{' '}
              <Link to="/sourcebooks" className="text-parchment-400 hover:text-parchment-200 underline underline-offset-2">
                browse your library
              </Link>
            </p>
          </section>

          {/* How Play Proceeds */}
          <section className="mb-14">
            <h3 className="text-parchment-500 text-xs uppercase tracking-wider mb-5">How Play Proceeds</h3>

            <div className="space-y-1">
              <Link
                to="/characters/create"
                className="flex items-center justify-between p-4 bg-dungeon-800/50 border border-dungeon-700 rounded hover:border-parchment-700/30 hover:bg-dungeon-800 transition-all group"
              >
                <div>
                  <div className="text-parchment-200 font-medium">Prepare Your Hero</div>
                  <div className="text-parchment-500 text-sm">
                    Create a character using classic race-as-class rules.
                    Ability scores, equipment, and starting spells are handled automatically.
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-parchment-600 group-hover:text-parchment-400 transition-colors flex-shrink-0 ml-4" />
              </Link>

              <Link
                to="/campaigns"
                className="flex items-center justify-between p-4 bg-dungeon-800/50 border border-dungeon-700 rounded hover:border-parchment-700/30 hover:bg-dungeon-800 transition-all group"
              >
                <div>
                  <div className="text-parchment-200 font-medium">Choose an Adventure</div>
                  <div className="text-parchment-500 text-sm">
                    Begin a new expedition or return to one already in progress.
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-parchment-600 group-hover:text-parchment-400 transition-colors flex-shrink-0 ml-4" />
              </Link>

              {canEnterWorld ? (
                <Link
                  to={`/play/${lastSession.character_id}/${lastSession.campaign_id}`}
                  className="flex items-center justify-between p-4 bg-dungeon-800/50 border border-dungeon-700 rounded hover:border-parchment-700/30 hover:bg-dungeon-800 transition-all group"
                >
                  <div>
                    <div className="text-parchment-200 font-medium">Enter the World</div>
                    <div className="text-parchment-500 text-sm">
                      Continue your adventure where you left off.
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-parchment-600 group-hover:text-parchment-400 transition-colors flex-shrink-0 ml-4" />
                </Link>
              ) : (
                <div className="flex items-center justify-between p-4 bg-dungeon-800/30 border border-dungeon-700/50 rounded opacity-60">
                  <div>
                    <div className="text-parchment-300 font-medium">Enter the World</div>
                    <div className="text-parchment-500 text-sm">
                      Create a character and choose a campaign first.
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-parchment-700 flex-shrink-0 ml-4" />
                </div>
              )}
            </div>
          </section>

          {/* Rules in Use */}
          <footer className="pt-8 border-t border-dungeon-700">
            <h3 className="text-parchment-500 text-xs uppercase tracking-wider mb-4">Rules in Use</h3>
            <ul className="text-parchment-400 text-sm space-y-1 mb-4">
              <li>
                <a
                  href="https://necroticgnome.com/pages/about-old-school-essentials"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-parchment-200 underline underline-offset-2"
                >
                  Old-School Essentials
                </a>
                {' '}(B/X compatible)
              </li>
              <li>
                <a
                  href="https://www.drivethrurpg.com/en/product/114895/black-streams-solo-heroes"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-parchment-200 underline underline-offset-2"
                >
                  Black Streams: Solo Heroes
                </a>
              </li>
            </ul>
            <p className="text-parchment-500 text-xs leading-relaxed">
              Combat uses simplified solo rules.
              Minor foes fall quickly; dangerous enemies do not.
              All dice rolls are resolved automatically.
              Judgment and caution remain your responsibility.
            </p>
          </footer>
        </div>
      </div>
    </div>
  )
}
