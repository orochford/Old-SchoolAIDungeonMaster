import { useState, useMemo, useRef } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Play, Trash2, Plus, X, Edit2, Save, BookOpen, Sword, Shield, ChevronDown, Heart, Swords, Star, Skull, Upload, Sparkles } from 'lucide-react'
import { api } from '@/services/api'
import { BX_EQUIPMENT, getItemDisplayName } from '@/game-systems/bx-dnd/data/equipment'

interface EquipmentItem {
  name: string
  quantity?: number
  value_gp?: number
}

interface Character {
  id: string
  name: string
  level: number
  experience_points: number
  status: string
  current_hp: number
  max_hp: number
  portrait_url?: string
  attributes: {
    character_class?: string
    race?: string
    alignment?: string
    armor_class?: number
    thac0?: number
    ability_scores?: {
      strength: number
      intelligence: number
      wisdom: number
      dexterity: number
      constitution: number
      charisma: number
    }
    equipment?: (string | EquipmentItem)[]
    gold?: number
    notes?: string
  }
}

interface JournalEntry {
  id: string
  entry_type: string
  title?: string
  content: string
  created_at: string
  campaign_id?: string
}

interface Campaign {
  id: string
  name: string
  description?: string
  adventure_document_id?: string
  status: string
}

/* ─── COMPONENTS ─── */

const StatBadge = ({ icon, value, label, color }: { icon: React.ReactNode; value: number | string; label: string; color: string }) => (
  <div
    className="flex items-center gap-1.5 px-2.5 py-1 rounded"
    style={{
      background: `${color}10`,
      border: `1px solid ${color}20`,
    }}
  >
    <span className="text-xs" style={{ color }}>{icon}</span>
    <span className="font-['IBM_Plex_Mono',monospace] text-sm font-semibold" style={{ color }}>{value}</span>
    <span className="font-['Crimson_Text',serif] text-[11px] text-[#6a6250]">{label}</span>
  </div>
)

const AbilityScore = ({ label, score, modifier }: { label: string; score: number; modifier: string }) => {
  const hue = {
    'STR': 0,
    'INT': 200,
    'WIS': 280,
    'DEX': 120,
    'CON': 30,
    'CHA': 320,
  }[label] || 0

  return (
    <div
      className="p-3 rounded-lg text-center transition-all duration-200 hover:-translate-y-0.5"
      style={{
        background: `linear-gradient(160deg, hsl(${hue}, 20%, 12%) 0%, hsl(${hue}, 15%, 8%) 100%)`,
        border: `1px solid hsl(${hue}, 25%, 20%)`,
      }}
    >
      <div className="font-['IBM_Plex_Mono',monospace] text-[10px] tracking-widest text-[#6a6250]">{label}</div>
      <div className="font-['Cinzel',serif] text-2xl font-bold text-[#c8c0aa] mt-0.5">{score}</div>
      <div
        className="font-['IBM_Plex_Mono',monospace] text-sm font-semibold mt-0.5"
        style={{ color: modifier.startsWith('+') ? '#5a8a5a' : modifier === '+0' ? '#6a6250' : '#c44' }}
      >
        {modifier}
      </div>
    </div>
  )
}

const SectionCard = ({ title, icon, children, action }: { title: string; icon?: React.ReactNode; children: React.ReactNode; action?: React.ReactNode }) => (
  <div
    className="rounded-lg p-5"
    style={{
      background: '#141210',
      border: '1px solid rgba(180,160,100,0.1)',
    }}
  >
    <div className="flex items-center justify-between mb-4">
      <h2 className="font-['Cinzel',serif] text-lg font-bold text-[#c8c0aa] flex items-center gap-2">
        {icon}
        {title}
      </h2>
      {action}
    </div>
    {children}
  </div>
)

export function CharacterSheetPage() {
  const { characterId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // State for editing
  const [isEditingEquipment, setIsEditingEquipment] = useState(false)
  const [newItemName, setNewItemName] = useState('')
  const [showItemDropdown, setShowItemDropdown] = useState(false)
  const [isEditingNotes, setIsEditingNotes] = useState(false)
  const [notesContent, setNotesContent] = useState('')
  const [isGeneratingPortrait, setIsGeneratingPortrait] = useState(false)
  const [showPromptModal, setShowPromptModal] = useState(false)
  const [promptDraft, setPromptDraft] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Filter equipment list based on search
  const filteredEquipment = useMemo(() => {
    if (!newItemName.trim()) return BX_EQUIPMENT
    const search = newItemName.toLowerCase()
    return BX_EQUIPMENT.filter(item =>
      item.name.toLowerCase().includes(search)
    )
  }, [newItemName])

  const { data: character, isLoading, error } = useQuery({
    queryKey: ['character', characterId],
    queryFn: () => api.get<Character>(`/characters/${characterId}`),
    enabled: !!characterId,
  })

  // Fetch journal entries for this character
  const { data: journalEntries } = useQuery({
    queryKey: ['journal', characterId],
    queryFn: () => api.get<JournalEntry[]>(`/journal/entries?character_id=${characterId}&limit=5`),
    enabled: !!characterId,
  })

  // Fetch campaigns for this character
  const { data: campaigns } = useQuery({
    queryKey: ['campaigns', characterId],
    queryFn: () => api.get<Campaign[]>(`/campaigns?character_id=${characterId}`),
    enabled: !!characterId,
  })

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/characters/${characterId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['characters'] })
      navigate('/characters')
    },
  })

  // Update character mutation
  const updateMutation = useMutation({
    mutationFn: (data: Partial<Character>) => api.patch(`/characters/${characterId}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character', characterId] })
    },
  })

  // Portrait upload mutation
  const uploadPortraitMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const response = await fetch(`/api/v1/characters/${characterId}/portrait/upload`, {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) throw new Error('Upload failed')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character', characterId] })
    },
  })

  // Portrait preview prompt mutation
  const previewPromptMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/v1/characters/${characterId}/portrait/preview-prompt`, {
        method: 'POST',
      })
      if (!response.ok) throw new Error('Failed to generate prompt')
      return response.json() as Promise<{ prompt: string }>
    },
    onSuccess: (data) => {
      setPromptDraft(data.prompt)
      setShowPromptModal(true)
    },
  })

  // Portrait generate mutation
  const generatePortraitMutation = useMutation({
    mutationFn: async (prompt?: string) => {
      setIsGeneratingPortrait(true)
      const response = await fetch(`/api/v1/characters/${characterId}/portrait/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt || undefined }),
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Generation failed')
      }
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character', characterId] })
      setIsGeneratingPortrait(false)
      setShowPromptModal(false)
    },
    onError: () => {
      setIsGeneratingPortrait(false)
    },
  })

  // Portrait delete mutation
  const deletePortraitMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/v1/characters/${characterId}/portrait`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('Delete failed')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['character', characterId] })
    },
  })

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      uploadPortraitMutation.mutate(file)
    }
  }

  // Add item to equipment
  const addItem = (itemName?: string) => {
    const nameToAdd = itemName || newItemName.trim()
    if (!nameToAdd || !character) return
    const currentEquipment = character.attributes.equipment || []
    const newEquipment = [...currentEquipment, { name: nameToAdd, quantity: 1 }]
    updateMutation.mutate({
      attributes: { ...character.attributes, equipment: newEquipment }
    } as Partial<Character>)
    setNewItemName('')
    setShowItemDropdown(false)
  }

  // Remove item from equipment
  const removeItem = (index: number) => {
    if (!character) return
    const currentEquipment = character.attributes.equipment || []
    const newEquipment = currentEquipment.filter((_, i) => i !== index)
    updateMutation.mutate({
      attributes: { ...character.attributes, equipment: newEquipment }
    } as Partial<Character>)
  }

  // Save notes
  const saveNotes = () => {
    if (!character) return
    updateMutation.mutate({
      attributes: { ...character.attributes, notes: notesContent }
    } as Partial<Character>)
    setIsEditingNotes(false)
  }

  if (isLoading) {
    return (
      <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center">
        <div className="font-['Crimson_Text',serif] text-[#8a8270] text-lg">Loading character...</div>
      </div>
    )
  }

  if (error || !character) {
    return (
      <div className="min-h-[calc(100vh-8rem)] flex items-center justify-center">
        <div className="font-['Crimson_Text',serif] text-red-400 text-lg">Character not found</div>
      </div>
    )
  }

  const abilityScores = character.attributes.ability_scores
  const isDead = character.status === 'dead'
  const hpPct = character.max_hp > 0 ? (character.current_hp / character.max_hp) * 100 : 0
  const hpColor = hpPct <= 25 ? '#c44' : hpPct <= 50 ? '#c90' : '#5a8a5a'

  const getModifier = (score: number) => {
    if (score <= 3) return -3
    if (score <= 5) return -2
    if (score <= 8) return -1
    if (score <= 12) return 0
    if (score <= 15) return 1
    if (score <= 17) return 2
    return 3
  }

  const formatMod = (mod: number) => (mod >= 0 ? `+${mod}` : `${mod}`)

  // Generate avatar hue from character name
  const avatarHue = character.name.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0) % 360

  return (
    <>
      <style>{`
        @keyframes cardIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div className="min-h-[calc(100vh-8rem)] flex">
        {/* Left atmosphere panel - fixed */}
        <div
          className="hidden lg:block w-[30%] fixed left-0 top-16 bottom-0"
          style={{
            backgroundImage: 'url(/img/tavern.png)',
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
        >
          <div className="absolute inset-0 bg-gradient-to-r from-dungeon-900/60 via-dungeon-900/80 to-dungeon-900" />

          {/* Character Portrait Card */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div
              className="w-56 rounded-xl overflow-hidden flex flex-col"
              style={{
                background: `linear-gradient(160deg, hsl(${avatarHue}, 20%, 12%) 0%, hsl(${avatarHue}, 15%, 6%) 100%)`,
                border: `1px solid hsl(${avatarHue}, 30%, 25%)`,
                boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
              }}
            >
              {/* Portrait Image Area */}
              <div
                className="w-full aspect-square relative flex items-center justify-center overflow-hidden"
                style={{
                  background: `hsl(${avatarHue}, 25%, 8%)`,
                }}
              >
                {character.portrait_url ? (
                  <img
                    src={character.portrait_url}
                    alt={character.name}
                    className="w-full h-full object-cover"
                  />
                ) : isDead ? (
                  <Skull className="w-16 h-16 text-red-500/50" />
                ) : (
                  <span className="font-['Cinzel',serif] text-6xl font-bold" style={{ color: `hsl(${avatarHue}, 40%, 30%)` }}>
                    {character.name.charAt(0)}
                  </span>
                )}

                {/* Portrait Action Buttons */}
                <div className="absolute bottom-2 right-2 flex gap-1">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    className="hidden"
                    onChange={handleFileSelect}
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadPortraitMutation.isPending}
                    className="p-1.5 rounded transition-all"
                    style={{
                      background: 'rgba(10,9,8,0.8)',
                      border: '1px solid rgba(180,160,100,0.2)',
                    }}
                    title="Upload portrait"
                  >
                    <Upload className="w-3.5 h-3.5 text-[#8a8270] hover:text-[#c8c0aa]" />
                  </button>
                  <button
                    onClick={() => previewPromptMutation.mutate()}
                    disabled={isGeneratingPortrait || previewPromptMutation.isPending}
                    className="p-1.5 rounded transition-all"
                    style={{
                      background: 'rgba(10,9,8,0.8)',
                      border: '1px solid rgba(180,160,100,0.2)',
                    }}
                    title="Generate portrait with AI"
                  >
                    {isGeneratingPortrait || previewPromptMutation.isPending ? (
                      <span className="w-3.5 h-3.5 block animate-spin text-[#b8a060]">...</span>
                    ) : (
                      <Sparkles className="w-3.5 h-3.5 text-[#8a8270] hover:text-[#b8a060]" />
                    )}
                  </button>
                  {character.portrait_url && (
                    <button
                      onClick={() => deletePortraitMutation.mutate()}
                      disabled={deletePortraitMutation.isPending}
                      className="p-1.5 rounded transition-all"
                      style={{
                        background: 'rgba(10,9,8,0.8)',
                        border: '1px solid rgba(180,160,100,0.2)',
                      }}
                      title="Remove portrait"
                    >
                      <X className="w-3.5 h-3.5 text-[#8a8270] hover:text-red-400" />
                    </button>
                  )}
                </div>

                {/* Generating overlay */}
                {isGeneratingPortrait && (
                  <div className="absolute inset-0 flex items-center justify-center bg-black/60">
                    <div className="text-center">
                      <Sparkles className="w-8 h-8 text-[#b8a060] mx-auto mb-2 animate-pulse" />
                      <div className="font-['Crimson_Text',serif] text-sm text-[#c8c0aa]">
                        Generating...
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Character Info */}
              <div className="p-3 text-center">
                <div className="font-['Cinzel',serif] text-lg font-bold text-[#c8c0aa] mb-0.5">
                  {character.name}
                </div>
                <div className="font-['Crimson_Text',serif] text-sm text-[#6a6250]">
                  Level {character.level}
                </div>
                {character.attributes.character_class && (
                  <div className="font-['Crimson_Text',serif] text-sm text-[#8a8270]">
                    {character.attributes.race && `${character.attributes.race} `}{character.attributes.character_class}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right content panel */}
        <div className="flex-1 lg:w-[70%] lg:ml-[30%] px-6 lg:px-12 py-12 overflow-y-auto">
          <div className="max-w-3xl mx-auto lg:mx-0">
            {/* Back nav */}
            <Link
              to="/characters"
              className="inline-flex items-center gap-2 font-['Crimson_Text',serif] text-sm text-[#6a6250] hover:text-[#c8c0aa] mb-8 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Characters
            </Link>

            {/* Header */}
            <div className="flex items-start justify-between mb-8">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h1 className="font-['Cinzel',serif] text-4xl text-[#c8c0aa] tracking-wide">{character.name}</h1>
                  {isDead && (
                    <span
                      className="px-2.5 py-1 rounded-full flex items-center gap-1.5 font-['IBM_Plex_Mono',monospace] text-[10px] tracking-wide"
                      style={{
                        background: 'rgba(196,68,68,0.1)',
                        border: '1px solid rgba(196,68,68,0.3)',
                        color: '#c44',
                      }}
                    >
                      <Skull className="w-3 h-3" />
                      FALLEN
                    </span>
                  )}
                </div>
                <p className="font-['Crimson_Text',serif] text-base text-[#6a6250] italic">
                  Level {character.level} {character.attributes.race || ''} {character.attributes.character_class || 'Adventurer'}
                  {character.attributes.alignment && ` • ${character.attributes.alignment}`}
                </p>
              </div>
              <div className="flex gap-2">
                {!isDead && (
                  <Link
                    to={`/play/${character.id}`}
                    className="flex items-center gap-2 px-4 py-2 rounded text-sm font-['Cinzel',serif] font-semibold text-[#f0e8d0] transition-all"
                    style={{
                      background: 'linear-gradient(135deg, #6a5020, #8a7030)',
                      border: '1px solid #b8a060',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.background = 'linear-gradient(135deg, #8a7030, #b8a060)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.background = 'linear-gradient(135deg, #6a5020, #8a7030)'
                    }}
                  >
                    <Play className="w-4 h-4" />
                    Play
                  </Link>
                )}
                <button
                  onClick={() => {
                    if (confirm('Are you sure you want to delete this character?')) {
                      deleteMutation.mutate()
                    }
                  }}
                  className="p-2 rounded text-[#6a6250] hover:text-red-400 transition-colors"
                  style={{
                    background: 'rgba(255,245,220,0.03)',
                    border: '1px solid rgba(180,160,100,0.1)',
                  }}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Stats Row */}
            <div className="flex flex-wrap gap-2 mb-8">
              <StatBadge
                icon={<Heart className="w-3 h-3" />}
                value={`${character.current_hp}/${character.max_hp}`}
                label="HP"
                color={hpColor}
              />
              <StatBadge
                icon={<Shield className="w-3 h-3" />}
                value={character.attributes.armor_class ?? 9}
                label="AC"
                color="#7a9ab8"
              />
              <StatBadge
                icon={<Swords className="w-3 h-3" />}
                value={character.attributes.thac0 ?? 19}
                label="THAC0"
                color="#c44"
              />
              <StatBadge
                icon={<Star className="w-3 h-3" />}
                value={character.experience_points}
                label="XP"
                color="#b8a060"
              />
              <StatBadge
                icon="💰"
                value={character.attributes.gold || 0}
                label="gp"
                color="#d4b870"
              />
            </div>

            {/* HP Bar */}
            <div className="mb-8">
              <div className="flex items-center justify-between mb-2">
                <span className="font-['IBM_Plex_Mono',monospace] text-[11px] tracking-wider text-[#6a6250]">HIT POINTS</span>
                <span className="font-['IBM_Plex_Mono',monospace] text-base font-semibold" style={{ color: hpColor }}>
                  {character.current_hp}<span className="opacity-40">/{character.max_hp}</span>
                </span>
              </div>
              <div className="h-2.5 bg-[#0a0908] rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${hpPct}%`, background: hpColor }}
                />
              </div>
            </div>

            {/* Main Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-5">
              {/* Ability Scores */}
              <SectionCard title="Ability Scores" icon={<Star className="w-4 h-4 text-[#6a6250]" />}>
                {abilityScores ? (
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { key: 'strength', label: 'STR' },
                      { key: 'intelligence', label: 'INT' },
                      { key: 'wisdom', label: 'WIS' },
                      { key: 'dexterity', label: 'DEX' },
                      { key: 'constitution', label: 'CON' },
                      { key: 'charisma', label: 'CHA' },
                    ].map(({ key, label }) => {
                      const score = abilityScores[key as keyof typeof abilityScores]
                      const mod = getModifier(score)
                      return (
                        <AbilityScore
                          key={key}
                          label={label}
                          score={score}
                          modifier={formatMod(mod)}
                        />
                      )
                    })}
                  </div>
                ) : (
                  <p className="font-['Crimson_Text',serif] text-[#6a6250]">No ability scores recorded</p>
                )}
              </SectionCard>

              {/* Equipment */}
              <SectionCard
                title="Equipment"
                icon={<Sword className="w-4 h-4 text-[#6a6250]" />}
                action={
                  <button
                    onClick={() => setIsEditingEquipment(!isEditingEquipment)}
                    className="text-[#6a6250] hover:text-[#c8c0aa] transition-colors"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                }
              >
                {character.attributes.equipment && character.attributes.equipment.length > 0 ? (
                  <ul className="space-y-2 max-h-64 overflow-y-auto">
                    {character.attributes.equipment.map((item, i) => {
                      const itemNameRaw = typeof item === 'string' ? item : item.name
                      const itemName = getItemDisplayName(itemNameRaw)
                      const quantity = typeof item === 'object' && item.quantity && item.quantity > 1
                        ? ` ×${item.quantity}`
                        : ''
                      return (
                        <li
                          key={i}
                          className="flex items-center justify-between py-1.5 px-2 rounded transition-colors hover:bg-[rgba(255,245,220,0.02)]"
                        >
                          <div className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 bg-[#6a6250] rounded-full" />
                            <span className="font-['Crimson_Text',serif] text-[#c8c0aa]">
                              {itemName}
                              {quantity && <span className="text-[#6a6250]">{quantity}</span>}
                            </span>
                          </div>
                          {isEditingEquipment && (
                            <button
                              onClick={() => removeItem(i)}
                              className="text-red-400/60 hover:text-red-400 transition-colors"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                ) : (
                  <p className="font-['Crimson_Text',serif] text-[#6a6250]">No equipment</p>
                )}

                {isEditingEquipment && (
                  <div className="mt-4 relative">
                    <div className="flex gap-2">
                      <div className="flex-1 relative">
                        <input
                          type="text"
                          value={newItemName}
                          onChange={(e) => {
                            setNewItemName(e.target.value)
                            setShowItemDropdown(true)
                          }}
                          onFocus={() => setShowItemDropdown(true)}
                          placeholder="Search or type item name..."
                          className="w-full px-3 py-2 rounded font-['Crimson_Text',serif] text-[#c8c0aa] placeholder-[#6a6250]"
                          style={{
                            background: '#0a0908',
                            border: '1px solid rgba(180,160,100,0.2)',
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              addItem()
                            } else if (e.key === 'Escape') {
                              setShowItemDropdown(false)
                            }
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => setShowItemDropdown(!showItemDropdown)}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-[#6a6250]"
                        >
                          <ChevronDown className="w-4 h-4" />
                        </button>
                      </div>
                      <button
                        onClick={() => addItem()}
                        disabled={!newItemName.trim()}
                        className="px-3 py-2 rounded text-[#c8c0aa] disabled:opacity-40 transition-colors"
                        style={{
                          background: 'rgba(255,245,220,0.05)',
                          border: '1px solid rgba(180,160,100,0.2)',
                        }}
                      >
                        <Plus className="w-4 h-4" />
                      </button>
                    </div>
                    {showItemDropdown && (
                      <div
                        className="absolute z-10 mt-1 w-full max-h-60 overflow-auto rounded shadow-xl"
                        style={{
                          background: '#1a1816',
                          border: '1px solid rgba(180,160,100,0.2)',
                        }}
                      >
                        {/* Custom item option when typing */}
                        {newItemName.trim() && !BX_EQUIPMENT.some(e => e.name.toLowerCase() === newItemName.toLowerCase()) && (
                          <button
                            onClick={() => addItem(newItemName.trim())}
                            className="w-full px-3 py-2 text-left text-[#c8c0aa] hover:bg-[rgba(255,245,220,0.05)] flex items-center border-b border-[rgba(180,160,100,0.1)]"
                            style={{ background: '#141210' }}
                          >
                            <Plus className="w-4 h-4 mr-2 text-[#5a8a5a]" />
                            <span className="font-['Crimson_Text',serif]">
                              Add custom: <strong>"{newItemName.trim()}"</strong>
                            </span>
                          </button>
                        )}
                        {filteredEquipment.length > 0 ? (
                          <>
                            {['weapon', 'armor', 'gear', 'ammo'].map(category => {
                              const items = filteredEquipment.filter(i => i.category === category)
                              if (items.length === 0) return null
                              return (
                                <div key={category}>
                                  <div
                                    className="px-3 py-1 font-['IBM_Plex_Mono',monospace] text-[10px] tracking-wider text-[#6a6250] uppercase sticky top-0"
                                    style={{ background: '#141210' }}
                                  >
                                    {category}
                                  </div>
                                  {items.map(item => (
                                    <button
                                      key={item.id}
                                      onClick={() => addItem(item.name)}
                                      className="w-full px-3 py-2 text-left hover:bg-[rgba(255,245,220,0.05)] flex justify-between items-center transition-colors"
                                    >
                                      <span className="font-['Crimson_Text',serif] text-[#c8c0aa]">{item.name}</span>
                                      <span className="font-['IBM_Plex_Mono',monospace] text-sm text-[#6a6250]">{item.costGp} gp</span>
                                    </button>
                                  ))}
                                </div>
                              )
                            })}
                          </>
                        ) : (
                          <div className="px-3 py-2 font-['Crimson_Text',serif] text-[#6a6250]">
                            No matching items in equipment list
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </SectionCard>
            </div>

            {/* Notes & Journal Section */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {/* Character Notes */}
              <SectionCard
                title="Notes"
                icon={<Edit2 className="w-4 h-4 text-[#6a6250]" />}
                action={
                  <button
                    onClick={() => {
                      if (isEditingNotes) {
                        saveNotes()
                      } else {
                        setNotesContent(character.attributes.notes || '')
                        setIsEditingNotes(true)
                      }
                    }}
                    className="text-[#6a6250] hover:text-[#c8c0aa] transition-colors"
                  >
                    {isEditingNotes ? <Save className="w-4 h-4" /> : <Edit2 className="w-4 h-4" />}
                  </button>
                }
              >
                {isEditingNotes ? (
                  <textarea
                    value={notesContent}
                    onChange={(e) => setNotesContent(e.target.value)}
                    placeholder="Add notes about your character..."
                    className="w-full h-40 rounded px-3 py-2 font-['Crimson_Text',serif] text-[#c8c0aa] placeholder-[#6a6250] resize-none"
                    style={{
                      background: '#0a0908',
                      border: '1px solid rgba(180,160,100,0.2)',
                    }}
                  />
                ) : (
                  <p className="font-['Crimson_Text',serif] text-[#8a8270] whitespace-pre-wrap">
                    {character.attributes.notes || 'No notes yet. Click edit to add some.'}
                  </p>
                )}
              </SectionCard>

              {/* Campaigns & Journal */}
              <SectionCard
                title="Adventures"
                icon={<Sword className="w-4 h-4 text-[#6a6250]" />}
              >
                {/* Active Campaigns */}
                {campaigns && campaigns.length > 0 ? (
                  <div className="space-y-3 mb-4">
                    {campaigns.map((campaign) => (
                      <div
                        key={campaign.id}
                        className="rounded p-3"
                        style={{
                          background: '#0a0908',
                          border: '1px solid rgba(180,160,100,0.1)',
                        }}
                      >
                        <div className="flex justify-between items-start">
                          <div>
                            <h3 className="font-['Cinzel',serif] text-[#c8c0aa] font-medium">{campaign.name}</h3>
                            {campaign.description && (
                              <p className="font-['Crimson_Text',serif] text-[#6a6250] text-sm mt-1">{campaign.description}</p>
                            )}
                          </div>
                          <span
                            className="font-['IBM_Plex_Mono',monospace] text-[10px] px-2 py-1 rounded"
                            style={{
                              background: campaign.status === 'active' ? 'rgba(90,138,90,0.1)' : 'rgba(100,100,100,0.1)',
                              color: campaign.status === 'active' ? '#5a8a5a' : '#6a6250',
                              border: `1px solid ${campaign.status === 'active' ? 'rgba(90,138,90,0.2)' : 'rgba(100,100,100,0.2)'}`,
                            }}
                          >
                            {campaign.status}
                          </span>
                        </div>
                        <div className="mt-2">
                          <Link
                            to={`/play/${characterId}?campaign=${campaign.id}`}
                            className="font-['Crimson_Text',serif] text-sm text-[#8a8270] hover:text-[#c8c0aa] transition-colors"
                          >
                            Continue →
                          </Link>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="font-['Crimson_Text',serif] text-[#6a6250] mb-4">
                    No adventures yet. Start playing to begin your journey!
                  </p>
                )}

                {/* Recent Journal Entries */}
                <div className="border-t border-[rgba(180,160,100,0.1)] pt-4">
                  <div className="flex justify-between items-center mb-3">
                    <h3 className="font-['Cinzel',serif] text-sm text-[#8a8270] flex items-center gap-2">
                      <BookOpen className="w-3 h-3" />
                      Recent Journal
                    </h3>
                    <Link
                      to={`/journal/${characterId}`}
                      className="font-['Crimson_Text',serif] text-[#6a6250] hover:text-[#c8c0aa] text-xs transition-colors"
                    >
                      View All
                    </Link>
                  </div>
                  {journalEntries && journalEntries.length > 0 ? (
                    <ul className="space-y-2">
                      {journalEntries.slice(0, 3).map((entry) => (
                        <li key={entry.id} className="text-sm">
                          <div className="font-['IBM_Plex_Mono',monospace] text-[#6a6250] text-[10px]">
                            {new Date(entry.created_at).toLocaleDateString()}
                            {entry.title && ` • ${entry.title}`}
                          </div>
                          <p className="font-['Crimson_Text',serif] text-[#8a8270] line-clamp-1">
                            {entry.content}
                          </p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="font-['Crimson_Text',serif] text-[#6a6250] text-sm">No journal entries yet.</p>
                  )}
                </div>
              </SectionCard>
            </div>
          </div>
        </div>
      </div>

      {/* Portrait Prompt Modal */}
      {showPromptModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.7)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setShowPromptModal(false) }}
        >
          <div
            className="w-full max-w-lg mx-4 rounded-xl p-6"
            style={{
              background: '#1a1816',
              border: '1px solid rgba(180,160,100,0.2)',
              boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
            }}
          >
            <h3 className="font-['Cinzel',serif] text-lg font-bold text-[#c8c0aa] mb-1">
              Portrait Prompt
            </h3>
            <p className="font-['Crimson_Text',serif] text-sm text-[#6a6250] mb-4">
              Edit the prompt below before generating with DALL-E.
            </p>
            <textarea
              value={promptDraft}
              onChange={(e) => setPromptDraft(e.target.value)}
              rows={8}
              className="w-full rounded px-3 py-2 font-['Crimson_Text',serif] text-sm text-[#c8c0aa] placeholder-[#6a6250] resize-none mb-4"
              style={{
                background: '#0a0908',
                border: '1px solid rgba(180,160,100,0.2)',
              }}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowPromptModal(false)}
                className="px-4 py-2 rounded font-['Cinzel',serif] text-sm text-[#6a6250] transition-colors hover:text-[#c8c0aa]"
                style={{
                  background: 'rgba(255,245,220,0.03)',
                  border: '1px solid rgba(180,160,100,0.1)',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => generatePortraitMutation.mutate(promptDraft)}
                disabled={isGeneratingPortrait || !promptDraft.trim()}
                className="px-4 py-2 rounded font-['Cinzel',serif] text-sm font-semibold text-[#f0e8d0] transition-all disabled:opacity-40 flex items-center gap-2"
                style={{
                  background: 'linear-gradient(135deg, #6a5020, #8a7030)',
                  border: '1px solid #b8a060',
                }}
              >
                {isGeneratingPortrait ? (
                  <>
                    <Sparkles className="w-4 h-4 animate-pulse" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    Generate
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
