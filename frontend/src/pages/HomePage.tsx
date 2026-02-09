import { useState, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'

// ─── Types ───

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

interface Character {
  id: string
  name: string
  level: number
  class_name: string
  race?: string
}

interface Campaign {
  id: string
  name: string
  status: string
  settings: {
    character_id?: string
    sourcebook_ids?: string[]
  }
}

// ─── Step Icon ───

function StepIcon({ type, done, active }: { type: string; done: boolean; active: boolean }) {
  const color = done ? '#5a8a5a' : active ? 'var(--gold)' : 'var(--muted)'
  const bg = done ? 'rgba(90,138,90,0.1)' : active ? 'rgba(180,160,80,0.08)' : 'rgba(180,160,100,0.03)'
  const borderColor = done ? 'rgba(90,138,90,0.3)' : active ? 'rgba(180,160,80,0.25)' : 'var(--border)'

  const icons: Record<string, React.ReactNode> = {
    character: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round">
        <path d="M12 2a5 5 0 0 1 5 5v1a5 5 0 0 1-10 0V7a5 5 0 0 1 5-5z" />
        <path d="M3.5 21.5c0-4 3.8-7 8.5-7s8.5 3 8.5 7" />
      </svg>
    ),
    module: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
        <path d="M8 7h8M8 11h5" opacity="0.5" />
      </svg>
    ),
    embark: (
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round">
        <polygon points="3,22 12,2 21,22" fill="none" />
        <line x1="12" y1="2" x2="12" y2="14" opacity="0.3" />
        <circle cx="12" cy="17" r="1.5" fill={color} opacity="0.5" />
        <path d="M7.5 17h9" opacity="0.3" />
      </svg>
    ),
  }

  return (
    <div style={{
      width: 56, height: 56, borderRadius: 12, flexShrink: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: bg, border: `1.5px solid ${borderColor}`,
      transition: 'all 0.3s ease',
      boxShadow: active ? '0 0 20px rgba(180,160,80,0.08)' : 'none',
    }}>
      {done ? (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#5a8a5a" strokeWidth="2.5" strokeLinecap="round">
          <polyline points="4 12 9 17 20 6" />
        </svg>
      ) : icons[type]}
    </div>
  )
}

// ─── Main ───

export function HomePage() {
  const [dragActive, setDragActive] = useState(false)
  const [uploadSuccess, setUploadSuccess] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  // ─── Data fetching ───

  const { data: systems } = useQuery({
    queryKey: ['rpg-systems'],
    queryFn: () => api.get<RPGSystem[]>('/campaigns/systems'),
  })

  const { data: characters } = useQuery({
    queryKey: ['characters'],
    queryFn: () => api.get<Character[]>('/characters'),
  })

  const { data: campaigns } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => api.get<Campaign[]>('/campaigns'),
  })

  const { data: recentSessions } = useQuery({
    queryKey: ['sessions', 'recent'],
    queryFn: () => api.get<Session[]>('/sessions?limit=1'),
  })

  const defaultSystemId = systems?.find(s => s.code === 'bx-dnd')?.id || systems?.[0]?.id
  const lastSession = recentSessions?.[0]

  const hasCharacter = (characters?.length ?? 0) > 0
  const hasCampaign = (campaigns?.length ?? 0) > 0
  const readyToPlay = hasCharacter && hasCampaign && !!lastSession

  // Most recent character for the "done" label
  const latestCharacter = characters?.[0]
  const characterLabel = latestCharacter
    ? `${latestCharacter.name} — Lv.${latestCharacter.level} ${latestCharacter.race || ''} ${latestCharacter.class_name}`.trim()
    : ''

  // Most recent campaign for the "done" label
  const latestCampaign = campaigns?.[0]
  const campaignLabel = latestCampaign ? latestCampaign.name : ''

  // ─── Upload ───

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!defaultSystemId) throw new Error('System not loaded yet')
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
    const pdfFiles = files.filter(f => f.type === 'application/pdf')
    if (pdfFiles.length > 0) uploadMutation.mutate(pdfFiles[0])
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length > 0) uploadMutation.mutate(files[0])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // ─── Steps ───

  const steps = [
    {
      key: 'character',
      num: 'I',
      title: 'Prepare Your Hero',
      subtitle: 'Create a character using classic race-as-class rules',
      description: 'Roll ability scores with 3d6-in-order, choose a class, buy equipment, and record starting spells. The rules of B/X and Old-School Essentials are built in — everything is handled for you, but nothing is hidden from you.',
      done: hasCharacter,
      active: !hasCharacter,
      doneLabel: characterLabel,
      iconType: 'character',
      link: '/characters/create',
      actionLabel: 'Create Character',
    },
    {
      key: 'module',
      num: 'II',
      title: 'Choose Your Expedition',
      subtitle: 'Upload an adventure module or select from your library',
      description: 'Drop a PDF of any B/X-compatible adventure module. The AI parses maps, room descriptions, encounters, and treasure tables. Your module becomes the world — nothing is invented, nothing is skipped.',
      done: hasCampaign,
      active: !hasCampaign,
      doneLabel: campaignLabel,
      iconType: 'module',
      link: '/campaigns',
      actionLabel: 'Choose Adventure',
    },
    {
      key: 'embark',
      num: 'III',
      title: 'Enter the World',
      subtitle: 'Begin your expedition into danger',
      description: 'Your character stands at the threshold. The AI Dungeon Master runs the module faithfully — rolling on encounter tables, tracking torches, enforcing morale. Time passes. Consequences persist. There are no save points.',
      done: false,
      active: readyToPlay,
      doneLabel: '',
      iconType: 'embark',
      link: lastSession ? `/play/${lastSession.character_id}/${lastSession.campaign_id}` : '#',
      actionLabel: 'Begin Adventure',
    },
  ]

  return (
    <>
      <style>{`
        :root {
          --bg: #0f0d0a; --bg-panel: #141210; --bg-card: rgba(255,245,220,0.03);
          --bg-deep: #0a0908; --bg-input: #1a1816;
          --border: rgba(180,160,100,0.1); --border-strong: rgba(180,160,100,0.2);
          --text: #c8c0aa; --text-dim: #8a8270; --muted: #6a6250;
          --gold: #b8a060; --gold-dim: rgba(180,160,80,0.4); --gold-bright: #d4b870;
          --font-display: 'Cinzel', serif; --font-body: 'Crimson Text', serif;
          --font-label: 'Cinzel', serif; --font-mono: 'IBM Plex Mono', monospace;
        }

        @keyframes fadeUp { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes glow { 0%, 100% { box-shadow: 0 0 20px rgba(180,160,80,0.08); } 50% { box-shadow: 0 0 30px rgba(180,160,80,0.15); } }
        @keyframes dropGlow { 0%, 100% { border-color: rgba(180,160,80,0.3); } 50% { border-color: rgba(180,160,80,0.6); } }
        @keyframes pulseReady { 0%, 100% { box-shadow: 0 4px 20px rgba(180,160,80,0.15); } 50% { box-shadow: 0 4px 30px rgba(180,160,80,0.3); } }
      `}</style>

      <div className="min-h-[calc(100vh-8rem)] flex" style={{ color: 'var(--text)' }}>
        {/* Left atmosphere panel */}
        <div
          className="hidden lg:block w-[30%] fixed left-0 top-16 bottom-0"
          style={{
            backgroundImage: 'url(/img/forgottenheroesoftherealm.png)',
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-dungeon-900/60 via-dungeon-900/80 to-dungeon-900" />
        </div>

        {/* Right content panel */}
        <div className="flex-1 lg:w-[70%] lg:ml-[30%] px-6 lg:px-12 py-12 overflow-y-auto">
          <div style={{ maxWidth: 640 }}>

            {/* Hero */}
            <div style={{ marginBottom: 48, animation: 'fadeUp 0.5s ease both' }}>
              <h1 style={{
                fontFamily: 'var(--font-display)', fontSize: 30, fontWeight: 700,
                color: 'var(--text)', letterSpacing: '0.04em', marginBottom: 12,
              }}>
                Into the Adventure
              </h1>
              <p style={{
                fontFamily: 'var(--font-body)', fontSize: 17, color: 'var(--text-dim)',
                lineHeight: 1.6,
              }}>
                Play classic adventure modules solo, guided by an impartial AI Dungeon Master.
              </p>
              <p style={{
                fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--muted)',
                fontStyle: 'italic', marginTop: 6,
              }}>
                Compatible with B/X, Old-School Essentials, and most OSR modules.
              </p>
            </div>

            {/* ═══ UPLOAD ZONE ═══ */}
            <div style={{ marginBottom: 36, animation: 'fadeUp 0.4s ease 0.1s both' }}>
                <div
                  onDragOver={e => { e.preventDefault(); setDragActive(true); }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={handleDrop}
                  onClick={() => !uploadMutation.isPending && !uploadSuccess && fileInputRef.current?.click()}
                  style={{
                    padding: '28px 24px', borderRadius: 8,
                    border: `2px dashed ${dragActive ? 'var(--gold)' : 'rgba(180,160,100,0.15)'}`,
                    background: dragActive ? 'rgba(180,160,80,0.05)' : 'rgba(180,160,80,0.02)',
                    cursor: 'pointer', transition: 'all 0.25s',
                    display: 'flex', alignItems: 'center', gap: 18,
                    animation: dragActive ? 'dropGlow 1s ease infinite' : 'none',
                  }}
                  onMouseEnter={e => { if (!dragActive) e.currentTarget.style.borderColor = 'rgba(180,160,100,0.25)'; }}
                  onMouseLeave={e => { if (!dragActive) e.currentTarget.style.borderColor = 'rgba(180,160,100,0.15)'; }}
                >
                  <input ref={fileInputRef} type="file" accept=".pdf" hidden onChange={handleFileSelect} />
                  <div style={{
                    width: 48, height: 48, borderRadius: 10, flexShrink: 0,
                    background: dragActive ? 'rgba(180,160,80,0.1)' : 'var(--bg-card)',
                    border: `1px solid ${dragActive ? 'var(--gold-dim)' : 'var(--border)'}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 0.2s',
                  }}>
                    {uploadSuccess ? (
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#5a8a5a" strokeWidth="2" strokeLinecap="round"><polyline points="4 12 9 17 20 6" /></svg>
                    ) : uploadMutation.isPending ? (
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="1.5" strokeLinecap="round" style={{ animation: 'spin 1s linear infinite' }}>
                        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                      </svg>
                    ) : (
                      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={dragActive ? 'var(--gold)' : 'var(--muted)'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="17 8 12 3 7 8" />
                        <line x1="12" y1="3" x2="12" y2="15" />
                      </svg>
                    )}
                  </div>
                  <div>
                    <div style={{
                      fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 600,
                      color: dragActive ? 'var(--gold)' : 'var(--text)', marginBottom: 3,
                      letterSpacing: '0.03em',
                    }}>
                      {uploadSuccess ? 'Module Received' : uploadMutation.isPending ? 'Processing...' : dragActive ? 'Drop module PDF' : 'Into the Adventure'}
                    </div>
                    <div style={{ fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--text-dim)', marginBottom: 2 }}>
                      {uploadSuccess ? 'Proceeding to library...' : uploadMutation.isPending ? 'Reading the adventure...' : 'Place an adventure module PDF here, or choose one already in your library.'}
                    </div>
                    {!uploadSuccess && !uploadMutation.isPending && (
                      <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--muted)' }}>
                        B/X and compatible formats recommended.
                      </div>
                    )}
                    {uploadMutation.isError && (
                      <div style={{ fontFamily: 'var(--font-body)', fontSize: 12, color: '#c44', marginTop: 4 }}>
                        {(uploadMutation.error as Error).message}
                      </div>
                    )}
                  </div>
                </div>
                <div style={{
                  textAlign: 'center', marginTop: 10,
                  fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--muted)',
                }}>
                  or{' '}
                  <Link to="/sourcebooks" style={{
                    color: 'var(--gold)', textDecoration: 'underline',
                    textUnderlineOffset: 3,
                  }}>browse your library</Link>
                </div>
            </div>

            {/* ═══ JOURNEY PATH ═══ */}
            <div style={{ position: 'relative' }}>
              {/* Vertical path line */}
              <div style={{
                position: 'absolute', left: 27, top: 0, bottom: 0,
                width: 2, zIndex: 0,
                background: `linear-gradient(to bottom,
                  ${hasCharacter ? 'rgba(90,138,90,0.4)' : 'var(--border)'} 0%,
                  ${hasCharacter ? 'rgba(90,138,90,0.4)' : 'var(--border)'} 33%,
                  ${hasCampaign ? 'rgba(90,138,90,0.4)' : 'var(--border)'} 33%,
                  ${hasCampaign ? 'rgba(90,138,90,0.4)' : 'var(--border)'} 66%,
                  var(--border) 66%,
                  var(--border) 100%
                )`,
              }} />

              {/* Steps */}
              {steps.map((step, i) => (
                <div key={step.key} style={{
                  position: 'relative',
                  display: 'flex', gap: 20,
                  marginBottom: i < steps.length - 1 ? 12 : 0,
                  animation: `fadeUp 0.4s ease ${0.15 + i * 0.12}s both`,
                }}>
                  {/* Icon */}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 2 }}>
                    <StepIcon type={step.iconType} done={step.done} active={step.active} />
                  </div>

                  {/* Content */}
                  <div style={{
                    flex: 1,
                    padding: '16px 22px 20px', borderRadius: 8,
                    background: step.active ? 'rgba(180,160,80,0.03)' : step.done ? 'rgba(90,138,90,0.02)' : 'transparent',
                    border: `1px solid ${step.active ? 'rgba(180,160,80,0.12)' : step.done ? 'rgba(90,138,90,0.08)' : 'transparent'}`,
                    transition: 'all 0.3s ease',
                    opacity: (step.key === 'embark' && !step.active) ? 0.4 : 1,
                  }}>
                    {/* Step number + title */}
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 4 }}>
                      <span style={{
                        fontFamily: 'var(--font-display)', fontSize: 11, fontWeight: 600,
                        color: step.done ? 'rgba(90,138,90,0.5)' : step.active ? 'var(--gold-dim)' : 'var(--muted)',
                        letterSpacing: '0.08em',
                      }}>{step.num}</span>
                      <h2 style={{
                        fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 700,
                        color: step.done ? 'var(--text-dim)' : step.active ? 'var(--text)' : 'var(--text-dim)',
                        margin: 0,
                      }}>{step.title}</h2>
                    </div>

                    {/* Subtitle */}
                    <p style={{
                      fontFamily: 'var(--font-body)', fontSize: 14, fontStyle: 'italic',
                      color: step.done ? 'var(--muted)' : 'var(--text-dim)',
                      marginBottom: step.active ? 10 : 4,
                    }}>
                      {step.subtitle}
                    </p>

                    {/* Description (only for active step) */}
                    {step.active && (
                      <p style={{
                        fontFamily: 'var(--font-body)', fontSize: 14,
                        color: 'var(--text-dim)', lineHeight: 1.6,
                        marginBottom: 16,
                      }}>
                        {step.description}
                      </p>
                    )}

                    {/* Done state */}
                    {step.done && step.doneLabel && (
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '6px 12px', borderRadius: 4,
                        background: 'rgba(90,138,90,0.05)',
                        border: '1px solid rgba(90,138,90,0.1)',
                        marginTop: 6,
                      }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#5a8a5a" strokeWidth="2" strokeLinecap="round">
                          <polyline points="4 12 9 17 20 6" />
                        </svg>
                        <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: '#5a8a5a' }}>
                          {step.doneLabel}
                        </span>
                        <div style={{ flex: 1 }} />
                        <Link to={step.link} style={{
                          fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--muted)',
                          textDecoration: 'none', transition: 'color 0.15s',
                        }}>Change</Link>
                      </div>
                    )}

                    {/* Step 1: Create character button */}
                    {step.key === 'character' && step.active && (
                      <Link to="/characters/create" style={{ textDecoration: 'none' }}>
                        <button style={{
                          padding: '11px 28px', borderRadius: 6, cursor: 'pointer',
                          background: 'linear-gradient(135deg, #6a5020, #8a7030)',
                          border: '1px solid var(--gold)',
                          fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 600,
                          letterSpacing: '0.1em', color: '#f0e8d0',
                          transition: 'all 0.2s',
                          boxShadow: '0 2px 16px rgba(180,160,80,0.15)',
                          animation: 'glow 3s ease infinite',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'linear-gradient(135deg, #8a7030, #b8a060)'; e.currentTarget.style.boxShadow = '0 4px 24px rgba(180,160,80,0.3)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'linear-gradient(135deg, #6a5020, #8a7030)'; e.currentTarget.style.boxShadow = '0 2px 16px rgba(180,160,80,0.15)'; }}
                        >{step.actionLabel}</button>
                      </Link>
                    )}

                    {/* Step 2: Module — point to upload zone or library */}
                    {step.key === 'module' && step.active && (
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '8px 14px', borderRadius: 4,
                        background: 'rgba(180,160,80,0.03)',
                        border: '1px solid rgba(180,160,80,0.08)',
                        marginTop: 4,
                      }}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1.5" strokeLinecap="round">
                          <polyline points="17 11 12 6 7 11" />
                          <line x1="12" y1="6" x2="12" y2="18" />
                        </svg>
                        <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--text-dim)' }}>
                          Drop a PDF above, or{' '}
                          <Link to="/sourcebooks" style={{
                            color: 'var(--gold)', textDecoration: 'underline',
                            textUnderlineOffset: 3,
                          }}>browse your library</Link>
                        </span>
                      </div>
                    )}

                    {/* Step 3: Begin button */}
                    {step.key === 'embark' && step.active && readyToPlay && (
                      <Link to={step.link} style={{ textDecoration: 'none', display: 'block' }}>
                        <button style={{
                          padding: '14px 36px', borderRadius: 6, cursor: 'pointer',
                          background: 'linear-gradient(135deg, #6a5020, #8a7030)',
                          border: '1px solid var(--gold)',
                          fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 700,
                          letterSpacing: '0.1em', color: '#f0e8d0',
                          transition: 'all 0.25s',
                          animation: 'pulseReady 2s ease infinite',
                          width: '100%',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.background = 'linear-gradient(135deg, #8a7030, #b8a060)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = 'linear-gradient(135deg, #6a5020, #8a7030)'; }}
                        >
                          ▶ Begin Adventure
                        </button>
                      </Link>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* ═══ BOTTOM FLAVOUR ═══ */}
            <div style={{
              marginTop: 56, textAlign: 'center',
              animation: 'fadeUp 0.4s ease 0.6s both',
            }}>
              <div style={{ width: 40, height: 1, background: 'var(--border)', margin: '0 auto 20px' }} />

              <div style={{
                fontFamily: 'var(--font-body)', fontSize: 14,
                color: 'var(--muted)', fontStyle: 'italic', lineHeight: 1.7,
                maxWidth: 400, margin: '0 auto',
              }}>
                The AI Dungeon Master runs your module faithfully — rolling encounter tables, tracking light sources, enforcing morale checks. It does not invent content, fudge dice, or show mercy.
              </div>

              <div style={{
                marginTop: 24, display: 'flex', justifyContent: 'center', gap: 24,
              }}>
                {[
                  { label: 'Faithful to module', icon: '📖' },
                  { label: 'Real dice rolls', icon: '🎲' },
                  { label: 'Permanent death', icon: '💀' },
                ].map(f => (
                  <div key={f.label} style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    fontFamily: 'var(--font-mono)', fontSize: 10,
                    color: 'var(--muted)', letterSpacing: '0.04em',
                  }}>
                    <span style={{ fontSize: 12 }}>{f.icon}</span>
                    {f.label}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
