import { Heart, Shield, Swords, Star, ChevronDown, ChevronRight, Weight, Footprints, Trash2, Target, Dices } from 'lucide-react'
import { useState, useMemo } from 'react'
import {
  calculateBXModifier,
  calculateArmorClass,
  getEquippedWeapon,
  calculateTotalEncumbrance,
  getMovementFromEncumbrance,
  EquippedItem,
  rollDice,
} from '@/game-systems/bx-dnd/utils/calculations'
import { BX_EQUIPMENT, getEquipmentById } from '@/game-systems/bx-dnd/data/equipment'

interface Character {
  id: string
  name: string
  level: number
  current_hp: number
  max_hp: number
  experience_points: number
  attributes: {
    character_class?: string
    ability_scores?: Record<string, number>
    saving_throws?: Record<string, number>
    thac0?: number
    armor_class?: number
    alignment?: string
    gold?: number
    equipment?: string[] // Legacy: simple string list
    equipped_items?: EquippedItem[] // New: full equipment tracking
    equipped_weapons?: { primary?: string; secondary?: string } // Weapon slot selections
    // Character description fields
    description?: {
      sex?: string
      height?: string
      hair?: string
      eyes?: string
      demeanor?: string
      notes?: string
    }
  }
}

interface AttackRollResult {
  weapon: string
  attackRoll: number
  damageRoll: { rolls: number[]; modifier: number; total: number }
  thac0: number
  strMod: number
}

interface AbilityCheckResult {
  type: 'ability' | 'save'
  name: string
  roll: number
  modifier?: number
  target?: number
  success?: boolean
}

interface Props {
  character: Character | undefined
  onAttackRoll?: (result: AttackRollResult) => void
  onAbilityCheck?: (result: AbilityCheckResult) => void
  onDropItem?: (itemId: string, itemName: string) => void
  onToggleEquipped?: (itemId: string, equipped: boolean, updatedItems: EquippedItem[]) => void
  onWeaponSelectionChange?: (primary: string | null, secondary: string | null) => void
}

export function CharacterSidebar({ character, onAttackRoll, onAbilityCheck, onDropItem, onToggleEquipped, onWeaponSelectionChange }: Props) {
  const [equipmentOpen, setEquipmentOpen] = useState(true)
  const [savesOpen, setSavesOpen] = useState(false)
  const [confirmDrop, setConfirmDrop] = useState<{ id: string; name: string } | null>(null)

  // Persist weapon selections - load from DB first, fallback to localStorage
  const storageKey = character ? `weapons-${character.id}` : null

  // Get initial values from DB or localStorage
  const getInitialPrimary = () => {
    if (character?.attributes?.equipped_weapons?.primary) {
      return character.attributes.equipped_weapons.primary
    }
    if (storageKey) {
      try {
        const saved = localStorage.getItem(storageKey)
        if (saved) {
          const parsed = JSON.parse(saved)
          return parsed.primary || null
        }
      } catch {}
    }
    return null
  }

  const getInitialSecondary = () => {
    if (character?.attributes?.equipped_weapons?.secondary) {
      return character.attributes.equipped_weapons.secondary
    }
    if (storageKey) {
      try {
        const saved = localStorage.getItem(storageKey)
        if (saved) {
          const parsed = JSON.parse(saved)
          return parsed.secondary || null
        }
      } catch {}
    }
    return null
  }

  const [primaryWeaponId, setPrimaryWeaponId] = useState<string | null>(getInitialPrimary)
  const [secondaryWeaponId, setSecondaryWeaponId] = useState<string | null>(getInitialSecondary)

  // Handle weapon selection change - saves to localStorage and DB
  const handlePrimaryChange = (weaponId: string | null) => {
    setPrimaryWeaponId(weaponId)
    // Save to localStorage immediately
    if (storageKey) {
      localStorage.setItem(storageKey, JSON.stringify({ primary: weaponId, secondary: secondaryWeaponId }))
    }
    // Save to DB
    onWeaponSelectionChange?.(weaponId, secondaryWeaponId)
  }

  const handleSecondaryChange = (weaponId: string | null) => {
    setSecondaryWeaponId(weaponId)
    // Save to localStorage immediately
    if (storageKey) {
      localStorage.setItem(storageKey, JSON.stringify({ primary: primaryWeaponId, secondary: weaponId }))
    }
    // Save to DB
    onWeaponSelectionChange?.(primaryWeaponId, weaponId)
  }

  if (!character) return null

  const attrs = character.attributes
  const abilities = attrs.ability_scores || {}
  const saves = attrs.saving_throws || {}
  const hpPercent = (character.current_hp / character.max_hp) * 100

  // Convert legacy equipment strings to EquippedItem format
  const equippedItems: EquippedItem[] = useMemo(() => {
    // If we have the new format, use it
    if (attrs.equipped_items && attrs.equipped_items.length > 0) {
      return attrs.equipped_items
    }

    // Convert legacy string array or new object format to EquippedItem format
    if (attrs.equipment && attrs.equipment.length > 0) {
      return attrs.equipment
        .filter((item) => {
          if (typeof item === 'string') return item.length > 0
          if (typeof item === 'object' && item !== null) return item.name && item.name.length > 0
          return false
        })
        .map((item) => {
          // Extract name from string or object
          const itemName = typeof item === 'string' ? item : item.name
          const quantity = typeof item === 'object' ? (item.quantity || 1) : 1

          // Try to find item in database by name (case insensitive)
          const dbItem = BX_EQUIPMENT.find(
            (e) => e.name.toLowerCase() === itemName.toLowerCase() ||
                   e.id === itemName.toLowerCase().replace(/\s+/g, '_')
          )

          if (dbItem) {
            return {
              id: dbItem.id,
              name: quantity > 1 ? `${dbItem.name} x${quantity}` : dbItem.name,
              category: dbItem.category,
              equipped: dbItem.category === 'weapon' || dbItem.category === 'armor', // Auto-equip weapons and armor
              damage: dbItem.damage,
              ac: dbItem.ac,
              acBonus: dbItem.acBonus,
              weight: dbItem.weight * quantity,
            }
          }

          // Unknown item - return as gear
          return {
            id: itemName.toLowerCase().replace(/\s+/g, '_'),
            name: quantity > 1 ? `${itemName} x${quantity}` : itemName,
            category: 'gear' as const,
            equipped: false,
            weight: 10 * quantity, // Default weight
          }
        })
    }

    return []
  }, [attrs.equipment, attrs.equipped_items])

  // Calculate derived stats
  const dexMod = calculateBXModifier(abilities.dexterity || abilities.dex || 10)
  const strMod = calculateBXModifier(abilities.strength || abilities.str || 10)
  const calculatedAC = calculateArmorClass(equippedItems, dexMod)
  // Gold adds to encumbrance (1 gp = 1 cn in B/X D&D)
  const goldWeight = attrs.gold || 0
  const equipmentWeight = calculateTotalEncumbrance(equippedItems)
  const totalEncumbrance = equipmentWeight + goldWeight
  const movement = getMovementFromEncumbrance(totalEncumbrance)

  // Use calculated AC when we have equipment tracking, otherwise fall back to stored value
  // This ensures AC updates when armor is equipped/unequipped
  const displayAC = (attrs.equipped_items && attrs.equipped_items.length > 0)
    ? calculatedAC
    : (attrs.armor_class ?? calculatedAC)

  // Get all weapons
  const weapons = equippedItems.filter((i) => i.category === 'weapon')

  // Auto-select primary weapon if not set
  const primaryWeapon = weapons.find((w) => w.id === primaryWeaponId) || weapons[0] || null
  const secondaryWeapon = weapons.find((w) => w.id === secondaryWeaponId && w.id !== primaryWeapon?.id) || null

  // Handle attack roll
  const handleAttackRoll = (weapon: EquippedItem) => {
    if (!weapon.damage || !onAttackRoll) return

    // Roll d20 for attack
    const attackRoll = Math.floor(Math.random() * 20) + 1

    // Roll damage
    const damageResult = rollDice(weapon.damage)

    onAttackRoll({
      weapon: weapon.name,
      attackRoll,
      damageRoll: damageResult,
      thac0: attrs.thac0 || 19,
      strMod,
    })
  }

  // Handle drop item
  const handleDropItem = (itemId: string, itemName: string) => {
    setConfirmDrop({ id: itemId, name: itemName })
  }

  const confirmDropItem = () => {
    if (confirmDrop && onDropItem) {
      onDropItem(confirmDrop.id, confirmDrop.name)
    }
    setConfirmDrop(null)
  }

  // Handle armor equip/unequip toggle
  const handleToggleEquipped = (itemId: string) => {
    if (!onToggleEquipped) return

    const updatedItems = equippedItems.map((item) => {
      if (item.id === itemId && item.category === 'armor') {
        return { ...item, equipped: !item.equipped }
      }
      return item
    })

    const toggledItem = updatedItems.find((item) => item.id === itemId)
    if (toggledItem) {
      onToggleEquipped(itemId, toggledItem.equipped, updatedItems)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Character Card */}
      <div className="card">
        <h2 className="font-display text-xl text-parchment-100 mb-1">
          {character.name}
        </h2>
        <p className="text-parchment-400 text-sm mb-2">
          Level {character.level} {attrs.character_class}
          {attrs.alignment && <span className="text-parchment-500"> ({attrs.alignment})</span>}
        </p>

        {/* Character Description */}
        {attrs.description && (
          <div className="text-xs text-parchment-500 mb-3 space-y-0.5">
            {(attrs.description.sex || attrs.description.height || attrs.description.hair || attrs.description.eyes) && (
              <p>
                {[
                  attrs.description.sex,
                  attrs.description.height,
                  attrs.description.hair && `${attrs.description.hair} hair`,
                  attrs.description.eyes && `${attrs.description.eyes} eyes`,
                ].filter(Boolean).join(', ')}
              </p>
            )}
            {attrs.description.demeanor && (
              <p className="italic">{attrs.description.demeanor}</p>
            )}
            {attrs.description.notes && (
              <p className="text-parchment-600">{attrs.description.notes}</p>
            )}
          </div>
        )}

        {/* HP Bar */}
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1">
            <div className="flex items-center text-parchment-300">
              <Heart className="w-4 h-4 mr-1 text-red-500" />
              <span className="text-sm">HP</span>
            </div>
            <span className="text-parchment-200 font-semibold text-sm">
              {character.current_hp} / {character.max_hp}
            </span>
          </div>
          <div className="h-3 bg-dungeon-700 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                hpPercent > 50 ? 'bg-green-600' : hpPercent > 25 ? 'bg-yellow-600' : 'bg-red-600'
              }`}
              style={{ width: `${hpPercent}%` }}
            />
          </div>
        </div>

        {/* XP */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center text-parchment-300">
            <Star className="w-4 h-4 mr-1 text-yellow-500" />
            <span>XP</span>
          </div>
          <span className="text-parchment-200 font-semibold">
            {character.experience_points.toLocaleString()}
          </span>
        </div>

        {/* Combat Stats */}
        <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-dungeon-600">
          <div className="bg-dungeon-700 rounded p-2 text-center">
            <Shield className="w-4 h-4 mx-auto mb-1 text-parchment-400" />
            <div className="text-xs text-parchment-500">AC</div>
            <div className="text-lg font-bold text-parchment-100">{displayAC}</div>
            {attrs.armor_class === undefined && equippedItems.length > 0 && (
              <div className="text-[9px] text-parchment-600">(calculated)</div>
            )}
          </div>
          {attrs.thac0 !== undefined && (
            <div className="bg-dungeon-700 rounded p-2 text-center">
              <Swords className="w-4 h-4 mx-auto mb-1 text-parchment-400" />
              <div className="text-xs text-parchment-500">THAC0</div>
              <div className="text-lg font-bold text-parchment-100">{attrs.thac0}</div>
            </div>
          )}
        </div>

        {/* Weapon Slots with Attack Buttons */}
        {weapons.length > 0 && (
          <div className="mt-3 pt-3 border-t border-dungeon-600 space-y-2">
            {/* Primary Weapon */}
            <div className="bg-dungeon-700 rounded p-2">
              <div className="text-[10px] uppercase text-parchment-500 mb-1">Primary Weapon</div>
              <div className="flex items-center gap-2">
                <select
                  value={primaryWeapon?.id || ''}
                  onChange={(e) => handlePrimaryChange(e.target.value || null)}
                  className="flex-1 bg-dungeon-600 text-parchment-200 text-xs rounded px-2 py-1 border border-dungeon-500"
                >
                  {weapons.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name} ({w.damage || 'no damage'})
                    </option>
                  ))}
                </select>
                {primaryWeapon && (
                  <button
                    onClick={() => handleAttackRoll(primaryWeapon)}
                    className="bg-red-700 hover:bg-red-600 text-white text-xs px-2 py-1 rounded flex items-center gap-1"
                    title="Roll attack"
                  >
                    <Target className="w-3 h-3" />
                    Attack
                  </button>
                )}
              </div>
              {primaryWeapon?.damage && (
                <div className="text-xs text-parchment-400 mt-1">
                  Damage: <span className="text-parchment-200 font-mono">{primaryWeapon.damage}</span>
                  {strMod !== 0 && <span className="text-parchment-500"> ({strMod > 0 ? '+' : ''}{strMod} STR)</span>}
                </div>
              )}
            </div>

            {/* Secondary Weapon (only if more than one weapon) */}
            {weapons.length > 1 && (
              <div className="bg-dungeon-700 rounded p-2">
                <div className="text-[10px] uppercase text-parchment-500 mb-1">Secondary Weapon</div>
                <div className="flex items-center gap-2">
                  <select
                    value={secondaryWeapon?.id || ''}
                    onChange={(e) => handleSecondaryChange(e.target.value || null)}
                    className="flex-1 bg-dungeon-600 text-parchment-200 text-xs rounded px-2 py-1 border border-dungeon-500"
                  >
                    <option value="">-- None --</option>
                    {weapons
                      .filter((w) => w.id !== primaryWeapon?.id)
                      .map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.name} ({w.damage || 'no damage'})
                        </option>
                      ))}
                  </select>
                  {secondaryWeapon && (
                    <button
                      onClick={() => handleAttackRoll(secondaryWeapon)}
                      className="bg-red-700 hover:bg-red-600 text-white text-xs px-2 py-1 rounded flex items-center gap-1"
                      title="Roll attack"
                    >
                      <Target className="w-3 h-3" />
                      Attack
                    </button>
                  )}
                </div>
                {secondaryWeapon?.damage && (
                  <div className="text-xs text-parchment-400 mt-1">
                    Damage: <span className="text-parchment-200 font-mono">{secondaryWeapon.damage}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Gold */}
        {attrs.gold !== undefined && (
          <div className="flex items-center justify-between text-sm mt-3 pt-3 border-t border-dungeon-600">
            <span className="text-parchment-300">Gold</span>
            <span className="text-parchment-200 font-semibold">{attrs.gold} gp</span>
          </div>
        )}
      </div>

      {/* Ability Scores */}
      {Object.keys(abilities).length > 0 && (
        <div className="card">
          <h3 className="font-display text-sm text-parchment-100 mb-2">Ability Scores</h3>
          <div className="grid grid-cols-3 gap-1">
            {Object.entries(abilities).map(([key, value]) => {
              const modifier = calculateBXModifier(value)
              const handleAbilityRoll = () => {
                if (!onAbilityCheck) return
                const roll = Math.floor(Math.random() * 20) + 1
                onAbilityCheck({
                  type: 'ability',
                  name: key,
                  roll,
                  modifier,
                })
              }
              return (
                <div key={key} className="bg-dungeon-700 rounded p-1.5 text-center relative group">
                  <div className="text-[10px] uppercase text-parchment-500">
                    {key.substring(0, 3)}
                  </div>
                  <div className="text-lg font-bold text-parchment-100">{value}</div>
                  <div className="text-xs text-parchment-400">
                    {formatModifier(modifier)}
                  </div>
                  {onAbilityCheck && (
                    <button
                      onClick={handleAbilityRoll}
                      className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity text-parchment-400 hover:text-parchment-200"
                      title={`Roll ${key} check`}
                    >
                      <Dices className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Saving Throws (Collapsible) */}
      {Object.keys(saves).length > 0 && (
        <div className="card">
          <button
            onClick={() => setSavesOpen(!savesOpen)}
            className="flex items-center justify-between w-full text-left"
          >
            <h3 className="font-display text-sm text-parchment-100">Saving Throws</h3>
            {savesOpen ? (
              <ChevronDown className="w-4 h-4 text-parchment-400" />
            ) : (
              <ChevronRight className="w-4 h-4 text-parchment-400" />
            )}
          </button>
          {savesOpen && (
            <div className="mt-2 space-y-1 text-sm">
              {Object.entries(saves).map(([key, value]) => {
                const handleSaveRoll = () => {
                  if (!onAbilityCheck) return
                  const roll = Math.floor(Math.random() * 20) + 1
                  const success = roll >= value
                  onAbilityCheck({
                    type: 'save',
                    name: formatSaveLabel(key),
                    roll,
                    target: value,
                    success,
                  })
                }
                return (
                  <div key={key} className="flex justify-between text-parchment-300 group">
                    <span className="flex items-center gap-1">
                      {formatSaveLabel(key)}
                      {onAbilityCheck && (
                        <button
                          onClick={handleSaveRoll}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-parchment-400 hover:text-parchment-200"
                          title={`Roll ${formatSaveLabel(key)} save`}
                        >
                          <Dices className="w-3 h-3" />
                        </button>
                      )}
                    </span>
                    <span className="text-parchment-200 font-semibold">{value}+</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Equipment (Collapsible) */}
      {equippedItems.length > 0 && (
        <div className="card">
          <button
            onClick={() => setEquipmentOpen(!equipmentOpen)}
            className="flex items-center justify-between w-full text-left"
          >
            <h3 className="font-display text-sm text-parchment-100">Equipment</h3>
            {equipmentOpen ? (
              <ChevronDown className="w-4 h-4 text-parchment-400" />
            ) : (
              <ChevronRight className="w-4 h-4 text-parchment-400" />
            )}
          </button>
          {equipmentOpen && (
            <div className="mt-2 space-y-1">
              {/* Weapons */}
              {equippedItems.filter((i) => i.category === 'weapon').length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] uppercase text-parchment-500 mb-1">Weapons</div>
                  {equippedItems
                    .filter((i) => i.category === 'weapon')
                    .map((item) => (
                      <div
                        key={item.id}
                        className={`flex items-center justify-between text-xs p-1 rounded group ${
                          item.equipped ? 'bg-dungeon-600 text-parchment-200' : 'text-parchment-400'
                        }`}
                      >
                        <span>{item.name}</span>
                        <div className="flex items-center gap-2">
                          {item.damage && <span className="text-parchment-300 font-mono">{item.damage}</span>}
                          {onDropItem && (
                            <button
                              onClick={() => handleDropItem(item.id, item.name)}
                              className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 transition-opacity"
                              title="Drop item"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                </div>
              )}

              {/* Armor */}
              {equippedItems.filter((i) => i.category === 'armor').length > 0 && (
                <div className="mb-2">
                  <div className="text-[10px] uppercase text-parchment-500 mb-1">Armor</div>
                  {equippedItems
                    .filter((i) => i.category === 'armor')
                    .map((item) => (
                      <div
                        key={item.id}
                        className={`flex items-center justify-between text-xs p-1 rounded group ${
                          item.equipped ? 'bg-dungeon-600 text-parchment-200' : 'bg-dungeon-800 text-parchment-500'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          {/* Equip/Unequip toggle button */}
                          <button
                            onClick={() => handleToggleEquipped(item.id)}
                            className={`w-5 h-5 flex items-center justify-center rounded text-[10px] font-bold transition-colors ${
                              item.equipped
                                ? 'bg-green-600 text-white hover:bg-green-500'
                                : 'bg-dungeon-600 text-parchment-400 hover:bg-dungeon-500'
                            }`}
                            title={item.equipped ? 'Click to unequip' : 'Click to equip'}
                          >
                            {item.equipped ? 'E' : 'U'}
                          </button>
                          <span className={item.equipped ? '' : 'line-through'}>{item.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`font-mono ${item.equipped ? 'text-parchment-300' : 'text-parchment-600'}`}>
                            {item.ac !== undefined ? `AC ${item.ac}` : item.acBonus !== undefined ? `+${item.acBonus}` : ''}
                          </span>
                          {onDropItem && (
                            <button
                              onClick={() => handleDropItem(item.id, item.name)}
                              className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 transition-opacity"
                              title="Drop item"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                </div>
              )}

              {/* Gear */}
              {equippedItems.filter((i) => i.category === 'gear' || i.category === 'ammo').length > 0 && (
                <div>
                  <div className="text-[10px] uppercase text-parchment-500 mb-1">Gear</div>
                  <div className="space-y-1">
                    {equippedItems
                      .filter((i) => i.category === 'gear' || i.category === 'ammo')
                      .map((item) => (
                        <div
                          key={item.id}
                          className="flex items-center justify-between text-xs p-1 rounded group hover:bg-dungeon-700"
                        >
                          <span className="text-parchment-400">
                            {item.name}
                            {item.quantity && item.quantity > 1 && ` (${item.quantity})`}
                          </span>
                          {onDropItem && (
                            <button
                              onClick={() => handleDropItem(item.id, item.name)}
                              className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 transition-opacity"
                              title="Drop item"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* Encumbrance */}
              <div className="mt-3 pt-2 border-t border-dungeon-600">
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center text-parchment-400">
                    <Weight className="w-3 h-3 mr-1" />
                    <span>Encumbrance</span>
                  </div>
                  <span className="text-parchment-300">{totalEncumbrance} cn</span>
                </div>
                {goldWeight > 0 && (
                  <div className="text-[10px] text-parchment-500 text-right">
                    (Gear: {equipmentWeight} + Gold: {goldWeight})
                  </div>
                )}
                <div className="flex items-center justify-between text-xs mt-1">
                  <div className="flex items-center text-parchment-400">
                    <Footprints className="w-3 h-3 mr-1" />
                    <span>Movement</span>
                  </div>
                  <span className={`${movement.dungeon === 0 ? 'text-red-400' : 'text-parchment-300'}`}>
                    {movement.dungeon}'/turn
                  </span>
                </div>
                <div className="text-[10px] text-parchment-500 text-right">{movement.description}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Drop Item Confirmation Dialog */}
      {confirmDrop && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-dungeon-800 border border-dungeon-600 rounded-lg p-4 max-w-sm mx-4 shadow-xl">
            <h3 className="text-parchment-100 font-display text-lg mb-2">Drop Item?</h3>
            <p className="text-parchment-300 text-sm mb-4">
              Are you sure you want to drop <span className="text-parchment-100 font-semibold">{confirmDrop.name}</span>?
              This action cannot be undone.
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setConfirmDrop(null)}
                className="px-3 py-1.5 text-sm text-parchment-300 hover:text-parchment-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDropItem}
                className="px-3 py-1.5 text-sm bg-red-700 hover:bg-red-600 text-white rounded transition-colors"
              >
                Drop Item
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function formatModifier(mod: number): string {
  if (mod >= 0) return `+${mod}`
  return `${mod}`
}

function formatSaveLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}
