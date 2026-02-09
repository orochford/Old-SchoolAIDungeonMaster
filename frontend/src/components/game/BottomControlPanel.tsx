import { useState, useRef, useEffect, useCallback } from "react";

/* ─── TYPES ─── */
interface WeaponData {
  name: string;
  damage: string;
  speed?: number;
  melee?: boolean;
  thrown?: boolean;
}

interface BottomControlPanelProps {
  onSendMessage: (text: string) => void;
  isLoading?: boolean;
  weapons?: WeaponData[];
}

interface ActionItem {
  icon: string;
  label: string;
  prompt: string;
  category: string;
  custom?: boolean;
}

interface DirEntry { k: string; a: number }
type DirectionMode = "cardinal" | "relative";
type DieType = "d4" | "d6" | "d8" | "d10" | "d12" | "d20";

/* ─── TINY DIE SVG ─── */
const TinyDie = ({ type, size = 20, color = "#b8a060", active = false }: {
  type: DieType; size?: number; color?: string; active?: boolean;
}) => {
  const shapes: Record<DieType, React.ReactNode> = {
    d4:  <polygon points="10,2 18,18 2,18" />,
    d6:  <rect x="2" y="2" width="16" height="16" rx="2.5" />,
    d8:  <polygon points="10,1 19,10 10,19 1,10" />,
    d10: <polygon points="10,1 19,8 16,18 4,18 1,8" />,
    d12: <polygon points="10,1 17,4 19,11 15,18 5,18 1,11 3,4" />,
    d20: <polygon points="10,1 18,6 18,14 10,19 2,14 2,6" />,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none">
      <g stroke={color} strokeWidth="1.2" fill={active ? `${color}20` : "none"}>
        {shapes[type]}
      </g>
    </svg>
  );
};

/* ─── MINI COMPASS ─── */
const MiniCompass = ({ onRoll, result, spinning, mode, onModeToggle, onSelect, disabled }: {
  onRoll: () => void;
  result: DirEntry | null;
  spinning: boolean;
  mode: DirectionMode;
  onModeToggle: () => void;
  onSelect: (d: DirEntry) => void;
  disabled?: boolean;
}) => {
  const dirs: DirEntry[] = mode === "cardinal"
    ? [{ k: "N", a: 0 }, { k: "E", a: 90 }, { k: "S", a: 180 }, { k: "W", a: 270 }]
    : [{ k: "F", a: 0 }, { k: "R", a: 90 }, { k: "B", a: 180 }, { k: "L", a: 270 }];

  const needleAngle = result ? result.a : -1;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      {/* Mode toggle */}
      <button onClick={onModeToggle} style={{
        background: "none", border: "none", cursor: "pointer",
        fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.08em",
        color: "var(--muted)", padding: "2px 0",
        transition: "color 0.15s", lineHeight: 1,
      }}
      onMouseEnter={e => e.currentTarget.style.color = "var(--gold)"}
      onMouseLeave={e => e.currentTarget.style.color = "var(--muted)"}
      title={mode === "cardinal" ? "Switch to Front/Right/Back/Left" : "Switch to North/East/South/West"}
      >
        {mode === "cardinal" ? "NESW" : "FRBL"}
      </button>

      {/* Compass */}
      <div style={{ position: "relative", width: 52, height: 52, flexShrink: 0 }}>
        <svg width="52" height="52" viewBox="0 0 52 52">
          {/* Ring */}
          <circle cx="26" cy="26" r="24" stroke="rgba(180,160,100,0.12)" strokeWidth="1" fill="none" />
          {/* Ticks */}
          {Array.from({ length: 8 }).map((_, i) => {
            const angle = (i * 45 - 90) * Math.PI / 180;
            const major = i % 2 === 0;
            return <line key={i}
              x1={26 + Math.cos(angle) * (major ? 18 : 20)} y1={26 + Math.sin(angle) * (major ? 18 : 20)}
              x2={26 + Math.cos(angle) * 23} y2={26 + Math.sin(angle) * 23}
              stroke="rgba(180,160,100,0.12)" strokeWidth={major ? 1 : 0.5} />;
          })}
          {/* Needle */}
          {needleAngle >= 0 && (
            <g style={{
              transform: `rotate(${needleAngle}deg)`, transformOrigin: "26px 26px",
              transition: spinning ? "transform 0.05s linear" : "transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
            }}>
              <polygon points="26,8 24.5,26 27.5,26" fill="var(--gold)" opacity="0.9" />
              <polygon points="26,44 24.5,26 27.5,26" fill="rgba(180,160,100,0.12)" />
            </g>
          )}
          <circle cx="26" cy="26" r="2" fill="var(--bg-deep)" stroke="rgba(180,160,100,0.2)" strokeWidth="0.8" />
        </svg>

        {/* Direction labels */}
        {dirs.map((d, i) => {
          const pos = [
            { top: 0, left: "50%", transform: "translateX(-50%)" },
            { top: "50%", right: -1, transform: "translateY(-50%)" },
            { bottom: 0, left: "50%", transform: "translateX(-50%)" },
            { top: "50%", left: -1, transform: "translateY(-50%)" },
          ][i] as React.CSSProperties;
          const isActive = result && result.k === d.k && !spinning;
          return (
            <button key={d.k} onClick={() => !disabled && onSelect(d)} style={{
              position: "absolute", ...pos,
              width: 16, height: 14, borderRadius: 2,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: isActive ? "rgba(180,160,80,0.15)" : "transparent",
              border: "none", cursor: disabled ? "default" : "pointer", padding: 0,
              fontFamily: "var(--font-display)", fontSize: 8, fontWeight: 700,
              color: isActive ? "var(--gold)" : "var(--muted)",
              transition: "all 0.15s", zIndex: 5,
            }}
            onMouseEnter={e => e.currentTarget.style.color = "var(--text)"}
            onMouseLeave={e => e.currentTarget.style.color = isActive ? "var(--gold)" : "var(--muted)"}
            >{d.k}</button>
          );
        })}

        {/* Centre roll button */}
        <button onClick={() => !disabled && onRoll()} disabled={spinning || disabled} style={{
          position: "absolute", top: "50%", left: "50%",
          transform: "translate(-50%, -50%)",
          width: 22, height: 22, borderRadius: "50%",
          background: "var(--bg-deep)", border: "1px solid rgba(180,160,100,0.15)",
          cursor: spinning || disabled ? "default" : "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 6, fontFamily: "var(--font-mono)", letterSpacing: "0.05em",
          color: "var(--muted)", transition: "all 0.15s", zIndex: 10,
        }}
        onMouseEnter={e => { if (!spinning && !disabled) { e.currentTarget.style.borderColor = "var(--gold-dim)"; e.currentTarget.style.color = "var(--gold)"; }}}
        onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(180,160,100,0.15)"; e.currentTarget.style.color = "var(--muted)"; }}
        title="Roll random direction"
        >{spinning ? "·" : "⟳"}</button>
      </div>
    </div>
  );
};

/* ─── COMMAND PALETTE ACTIONS ─── */
const ACTIONS: ActionItem[] = [
  { icon: "🔍", label: "Search", prompt: "I carefully search the area", category: "explore" },
  { icon: "👂", label: "Listen", prompt: "I stop and listen carefully", category: "explore" },
  { icon: "🚪", label: "Open door", prompt: "I open the door", category: "explore" },
  { icon: "👁", label: "Look around", prompt: "I look around the room", category: "explore" },
  { icon: "🪤", label: "Check traps", prompt: "I check for traps", category: "explore" },
  { icon: "💀", label: "Examine body", prompt: "I examine the body", category: "explore" },
  { icon: "🏺", label: "Loot", prompt: "I search for treasure and loot", category: "explore" },
  { icon: "🎒", label: "Check inventory", prompt: "I check my inventory and equipment", category: "manage" },
  { icon: "🛡", label: "Check stats", prompt: "Show my current stats and condition", category: "manage" },
  { icon: "🗺", label: "Check map", prompt: "I review what I know of the map so far", category: "manage" },
  { icon: "⛺", label: "Rest", prompt: "I want to rest and recover", category: "action" },
  { icon: "🗣", label: "Talk", prompt: "I want to talk to", category: "action" },
  { icon: "🔥", label: "Light torch", prompt: "I light a fresh torch", category: "action" },
  { icon: "🧗", label: "Climb", prompt: "I attempt to climb", category: "action" },
  { icon: "🤫", label: "Sneak", prompt: "I try to move silently", category: "action" },
  { icon: "🗝", label: "Pick lock", prompt: "I attempt to pick the lock", category: "action" },
  { icon: "⚔", label: "Attack", prompt: "I attack", category: "combat" },
  { icon: "🏃", label: "Flee", prompt: "I flee from combat", category: "combat" },
  { icon: "🛡", label: "Defend", prompt: "I take a defensive stance", category: "combat" },
  { icon: "📖", label: "Cast spell", prompt: "I cast", category: "combat" },
];

const CATEGORIES = [
  { key: "all", label: "All" },
  { key: "explore", label: "Explore" },
  { key: "action", label: "Action" },
  { key: "combat", label: "Combat" },
  { key: "manage", label: "Manage" },
];

/* ─── DICE SIDES ─── */
const DICE_SIDES: Record<DieType, number> = {
  d4: 4, d6: 6, d8: 8, d10: 10, d12: 12, d20: 20,
};

/* ─── DIRECTION PROMPTS ─── */
const DIR_PROMPTS: Record<string, string> = {
  N: "I go north", E: "I go east", S: "I go south", W: "I go west",
  F: "I move forward", R: "I move to the right", B: "I move backward", L: "I move to the left",
};

/* ─── MAIN COMPONENT ─── */
export function BottomControlPanel({ onSendMessage, isLoading = false, weapons = [] }: BottomControlPanelProps) {
  // Dice state
  const [selectedDie, setSelectedDie] = useState<DieType>("d20");
  const [diceCount, setDiceCount] = useState(1);
  const [diceMod, setDiceMod] = useState(0);
  const [lastRoll, setLastRoll] = useState<{
    dice: number[]; total: number; settling: boolean;
    type?: DieType; count?: number; mod?: number;
  } | null>(null);
  const [diceRolling, setDiceRolling] = useState(false);

  // Direction state
  const [dirMode, setDirMode] = useState<DirectionMode>("cardinal");
  const [dirResult, setDirResult] = useState<DirEntry | null>(null);
  const [dirSpinning, setDirSpinning] = useState(false);

  // Command palette state
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteSearch, setPaletteSearch] = useState("");
  const [paletteCat, setPaletteCat] = useState("all");
  const [customActions, setCustomActions] = useState<ActionItem[]>([]);
  const [addingCustom, setAddingCustom] = useState(false);
  const [newIcon, setNewIcon] = useState("⚡");
  const [newLabel, setNewLabel] = useState("");
  const [newPrompt, setNewPrompt] = useState("");
  const [newCategory, setNewCategory] = useState("action");

  // Text input
  const [inputText, setInputText] = useState("");
  const textRef = useRef<HTMLTextAreaElement>(null);
  const paletteRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const newLabelRef = useRef<HTMLInputElement>(null);

  // Load custom actions from localStorage
  useEffect(() => {
    const saved = localStorage.getItem("osr-custom-actions");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        setCustomActions(parsed.map((a: { icon: string; label: string; prompt: string; category?: string }) => ({
          ...a,
          category: a.category || "action",
          custom: true,
        })));
      } catch (e) {
        console.error("Failed to load custom actions:", e);
      }
    }
  }, []);

  // Save custom actions to localStorage
  useEffect(() => {
    const toSave = customActions.map(a => ({
      icon: a.icon, label: a.label, prompt: a.prompt, category: a.category,
    }));
    localStorage.setItem("osr-custom-actions", JSON.stringify(toSave));
  }, [customActions]);

  // Close palette on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (paletteRef.current && !paletteRef.current.contains(e.target as Node)) {
        setPaletteOpen(false);
        setAddingCustom(false);
      }
    };
    if (paletteOpen) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [paletteOpen]);

  // Focus search when palette opens
  useEffect(() => {
    if (paletteOpen && !addingCustom && searchRef.current) searchRef.current.focus();
  }, [paletteOpen, addingCustom]);
  useEffect(() => {
    if (addingCustom && newLabelRef.current) newLabelRef.current.focus();
  }, [addingCustom]);

  /* ─── HANDLERS ─── */

  // Dice roll with animated preview
  const handleDiceRoll = useCallback(() => {
    if (diceRolling || isLoading) return;
    setDiceRolling(true);
    setLastRoll(null);
    let frame = 0;
    const sides = DICE_SIDES[selectedDie];
    const count = diceCount;
    const mod = diceMod;
    const interval = setInterval(() => {
      const preview = Array.from({ length: count }, () => Math.floor(Math.random() * sides) + 1);
      setLastRoll({ dice: preview, total: preview.reduce((a, b) => a + b, 0) + mod, settling: false });
      frame++;
      if (frame >= 6) {
        clearInterval(interval);
        const final = Array.from({ length: count }, () => Math.floor(Math.random() * sides) + 1);
        const total = final.reduce((a, b) => a + b, 0) + mod;
        setLastRoll({ dice: final, total, settling: true, type: selectedDie, count, mod });
        setDiceRolling(false);
        // Send in [ROLL] format
        const notation = `${count > 1 ? count : ""}${selectedDie}${mod > 0 ? `+${mod}` : mod < 0 ? `${mod}` : ""}`;
        const rollDetail = final.length > 1 ? ` [${final.join(", ")}]` : "";
        const modDetail = mod !== 0 ? (mod > 0 ? ` +${mod}` : ` ${mod}`) : "";
        onSendMessage(`[ROLL] ${notation}: ${total}${rollDetail}${modDetail}`);
      }
    }, 60);
  }, [selectedDie, diceCount, diceMod, diceRolling, isLoading, onSendMessage]);

  // Direction roll with animated needle spin
  const handleDirRoll = useCallback(() => {
    if (dirSpinning || isLoading) return;
    setDirSpinning(true);
    setDirResult(null);
    const dirs: DirEntry[] = dirMode === "cardinal"
      ? [{ k: "N", a: 0 }, { k: "E", a: 90 }, { k: "S", a: 180 }, { k: "W", a: 270 }]
      : [{ k: "F", a: 0 }, { k: "R", a: 90 }, { k: "B", a: 180 }, { k: "L", a: 270 }];
    let frame = 0;
    const total = 8 + Math.floor(Math.random() * 5);
    const interval = setInterval(() => {
      setDirResult(dirs[frame % 4]);
      frame++;
      if (frame >= total) {
        clearInterval(interval);
        const chosen = dirs[Math.floor(Math.random() * 4)];
        setDirResult(chosen);
        setDirSpinning(false);
        onSendMessage(DIR_PROMPTS[chosen.k]);
      }
    }, 65 + frame * 6);
  }, [dirSpinning, dirMode, isLoading, onSendMessage]);

  // Direction click
  const handleDirSelect = (d: DirEntry) => {
    if (isLoading) return;
    setDirResult(d);
    onSendMessage(DIR_PROMPTS[d.k]);
  };

  // Command palette action
  const handleAction = (action: ActionItem) => {
    setPaletteOpen(false);
    setPaletteSearch("");
    setPaletteCat("all");
    setAddingCustom(false);
    onSendMessage(action.prompt);
  };

  // Add custom action
  const handleAddCustom = () => {
    if (!newLabel.trim()) return;
    const action: ActionItem = {
      icon: newIcon || "⚡",
      label: newLabel.trim(),
      prompt: newPrompt.trim() || newLabel.trim(),
      category: newCategory,
      custom: true,
    };
    setCustomActions(prev => [...prev, action]);
    setNewIcon("⚡");
    setNewLabel("");
    setNewPrompt("");
    setNewCategory("action");
    setAddingCustom(false);
  };

  // Delete custom action
  const handleDeleteCustom = (index: number) => {
    setCustomActions(prev => prev.filter((_, i) => i !== index));
  };

  // Filter actions
  const allActions = [...ACTIONS, ...customActions];
  const filteredActions = allActions.filter(a => {
    const matchCat = paletteCat === "all" || a.category === paletteCat;
    const matchSearch = !paletteSearch || a.label.toLowerCase().includes(paletteSearch.toLowerCase());
    return matchCat && matchSearch;
  });

  const handleSend = useCallback(() => {
    if (!inputText.trim() || isLoading) return;
    onSendMessage(inputText.trim());
    setInputText("");
    textRef.current?.focus();
  }, [inputText, isLoading, onSendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
    if (e.key === "/" && inputText === "") { e.preventDefault(); setPaletteOpen(true); }
  };

  const diceNotation = `${diceCount > 1 ? diceCount : ""}${selectedDie}${diceMod > 0 ? `+${diceMod}` : diceMod < 0 ? diceMod : ""}`;

  return (
    <>
      <style>{`
        @keyframes paletteUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes resultPop { 0% { transform: scale(0.7); opacity: 0; } 60% { transform: scale(1.1); } 100% { transform: scale(1); opacity: 1; } }

        .die-btn {
          padding: 3px 2px; border-radius: 3px; cursor: pointer;
          background: transparent; border: 1px solid transparent;
          transition: all 0.12s; display: flex; align-items: center; justify-content: center;
        }
        .die-btn:hover { border-color: rgba(180,160,80,0.12); }
        .die-btn.active { border-color: rgba(180,160,80,0.25); background: rgba(180,160,80,0.06); }

        .action-btn {
          display: flex; align-items: center; gap: 8; width: 100%;
          padding: 8px 12px; border-radius: 4px; cursor: pointer;
          background: transparent; border: none; text-align: left;
          font-family: var(--font-body); font-size: 14px; color: var(--text);
          transition: background 0.1s;
        }
        .action-btn:hover { background: rgba(180,160,80,0.06); }

        .cat-btn {
          padding: 3px 10px; border-radius: 10px; cursor: pointer;
          background: transparent; border: 1px solid transparent;
          font-family: var(--font-mono); font-size: 10px;
          color: var(--muted); transition: all 0.12s;
        }
        .cat-btn:hover { color: var(--text-dim); }
        .cat-btn.active { color: var(--gold); border-color: rgba(180,160,80,0.3); background: rgba(180,160,80,0.06); }

        .cp-count-btn {
          width: 18px; height: 24px; cursor: pointer;
          background: transparent; border: none;
          color: var(--text-dim); font-family: var(--font-mono); font-size: 12px;
          display: flex; align-items: center; justify-content: center;
          transition: color 0.15s;
        }
        .cp-count-btn:hover { color: var(--gold); }

        .cp-delete-btn {
          position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
          width: 20px; height: 20px; border-radius: 50%;
          background: transparent; border: none;
          cursor: pointer; display: flex; align-items: center; justify-content: center;
          font-family: var(--font-mono); font-size: 11px; color: transparent;
          transition: all 0.15s;
        }
        .cp-delete-btn:hover { color: #c44; background: rgba(204,68,68,0.08); }
        .action-row:hover .cp-delete-btn { color: var(--muted); }
      `}</style>

      {/* ═══ BOTTOM PANEL ═══ */}
      <div style={{
        background: "var(--bg-panel)",
        borderTop: "1px solid var(--border)",
        position: "relative",
      }}>
        {/* ── Command Palette (opens upward) ── */}
        {paletteOpen && (
          <div ref={paletteRef} style={{
            position: "absolute", bottom: "100%", left: 0, right: 0,
            background: "var(--bg-panel)",
            borderTop: "1px solid var(--border)",
            borderBottom: "1px solid var(--border)",
            boxShadow: "0 -12px 40px rgba(0,0,0,0.4)",
            animation: "paletteUp 0.2s ease",
            maxHeight: 360, display: "flex", flexDirection: "column",
          }}>
            {/* Search bar */}
            <div style={{
              padding: "10px 16px",
              borderBottom: "1px solid var(--border)",
              display: "flex", alignItems: "center", gap: 10,
            }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--gold)", fontWeight: 600 }}>/</span>
              <input
                ref={searchRef}
                value={paletteSearch}
                onChange={e => setPaletteSearch(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Escape") { setPaletteOpen(false); textRef.current?.focus(); }
                  if (e.key === "Enter" && filteredActions.length > 0) handleAction(filteredActions[0]);
                }}
                placeholder="Search actions…"
                style={{
                  flex: 1, padding: "4px 0", background: "transparent",
                  border: "none", fontFamily: "var(--font-body)", fontSize: 15,
                  color: "var(--text)", outline: "none",
                }}
              />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", padding: "2px 6px", borderRadius: 3, background: "var(--bg-deep)" }}>ESC</span>
            </div>

            {/* Category filters + add button */}
            <div style={{ padding: "8px 16px 4px", display: "flex", alignItems: "center", gap: 4 }}>
              {CATEGORIES.map(c => (
                <button key={c.key}
                  className={`cat-btn ${paletteCat === c.key ? "active" : ""}`}
                  onClick={() => { setPaletteCat(c.key); setAddingCustom(false); }}
                >{c.label}</button>
              ))}
              <div style={{ flex: 1 }} />
              <button
                onClick={() => setAddingCustom(!addingCustom)}
                style={{
                  width: 24, height: 24, borderRadius: 4,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: addingCustom ? "rgba(180,160,80,0.1)" : "transparent",
                  border: `1px solid ${addingCustom ? "var(--gold-dim)" : "var(--border)"}`,
                  cursor: "pointer",
                  fontFamily: "var(--font-mono)", fontSize: 14,
                  color: addingCustom ? "var(--gold)" : "var(--muted)",
                  transition: "all 0.15s",
                }}
                onMouseEnter={e => { if (!addingCustom) { e.currentTarget.style.borderColor = "var(--border-strong)"; e.currentTarget.style.color = "var(--text-dim)"; }}}
                onMouseLeave={e => { if (!addingCustom) { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--muted)"; }}}
                title="Add custom action"
              >{addingCustom ? "×" : "+"}</button>
            </div>

            {/* Add custom action form */}
            {addingCustom && (
              <div style={{
                margin: "4px 12px 6px", padding: "12px 14px",
                borderRadius: 6,
                background: "rgba(180,160,80,0.03)",
                border: "1px solid rgba(180,160,80,0.1)",
                animation: "paletteUp 0.15s ease",
              }}>
                <div style={{
                  fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.12em",
                  color: "var(--muted)", marginBottom: 10,
                }}>NEW CUSTOM ACTION</div>

                {/* Row 1: Icon + Label */}
                <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
                  <input
                    value={newIcon}
                    onChange={e => setNewIcon(e.target.value)}
                    maxLength={2}
                    style={{
                      width: 36, padding: "5px 4px", borderRadius: 4, textAlign: "center",
                      background: "var(--bg-input)", border: "1px solid var(--border)",
                      fontFamily: "var(--font-body)", fontSize: 14, color: "var(--text)",
                    }}
                    onFocus={e => e.currentTarget.style.borderColor = "var(--gold-dim)"}
                    onBlur={e => e.currentTarget.style.borderColor = "var(--border)"}
                  />
                  <input
                    ref={newLabelRef}
                    value={newLabel}
                    onChange={e => setNewLabel(e.target.value)}
                    placeholder="Action name"
                    onKeyDown={e => { if (e.key === "Enter") handleAddCustom(); if (e.key === "Escape") setAddingCustom(false); }}
                    style={{
                      flex: 1, padding: "5px 8px", borderRadius: 4,
                      background: "var(--bg-input)", border: "1px solid var(--border)",
                      fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text)",
                    }}
                    onFocus={e => e.currentTarget.style.borderColor = "var(--gold-dim)"}
                    onBlur={e => e.currentTarget.style.borderColor = "var(--border)"}
                  />
                </div>

                {/* Row 2: Prompt */}
                <div style={{ marginBottom: 8 }}>
                  <input
                    value={newPrompt}
                    onChange={e => setNewPrompt(e.target.value)}
                    placeholder="Prompt text (defaults to name)"
                    onKeyDown={e => { if (e.key === "Enter") handleAddCustom(); if (e.key === "Escape") setAddingCustom(false); }}
                    style={{
                      width: "100%", padding: "5px 8px", borderRadius: 4,
                      background: "var(--bg-input)", border: "1px solid var(--border)",
                      fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text)",
                    }}
                    onFocus={e => e.currentTarget.style.borderColor = "var(--gold-dim)"}
                    onBlur={e => e.currentTarget.style.borderColor = "var(--border)"}
                  />
                </div>

                {/* Row 3: Category + Save */}
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ display: "flex", gap: 3 }}>
                    {["explore", "action", "combat", "manage"].map(cat => (
                      <button key={cat} onClick={() => setNewCategory(cat)} style={{
                        padding: "2px 8px", borderRadius: 8, cursor: "pointer",
                        background: newCategory === cat ? "rgba(180,160,80,0.1)" : "transparent",
                        border: `1px solid ${newCategory === cat ? "var(--gold-dim)" : "transparent"}`,
                        fontFamily: "var(--font-mono)", fontSize: 9,
                        color: newCategory === cat ? "var(--gold)" : "var(--muted)",
                        transition: "all 0.1s", textTransform: "capitalize",
                      }}>{cat}</button>
                    ))}
                  </div>
                  <div style={{ flex: 1 }} />
                  <button
                    onClick={handleAddCustom}
                    disabled={!newLabel.trim()}
                    style={{
                      padding: "4px 14px", borderRadius: 4, cursor: newLabel.trim() ? "pointer" : "default",
                      background: newLabel.trim() ? "rgba(180,160,80,0.12)" : "transparent",
                      border: `1px solid ${newLabel.trim() ? "var(--gold-dim)" : "var(--border)"}`,
                      fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.08em",
                      color: newLabel.trim() ? "var(--gold)" : "var(--muted)",
                      transition: "all 0.15s",
                    }}
                  >SAVE</button>
                </div>
              </div>
            )}

            {/* Action list */}
            <div style={{ flex: 1, overflowY: "auto", padding: "4px 8px 8px" }}>
              {filteredActions.map((action, i) => {
                const customIndex = action.custom ? customActions.indexOf(action) : -1;
                return (
                  <div key={`${action.label}-${i}`} className="action-row" style={{ position: "relative", display: "flex", alignItems: "center" }}>
                    <button className="action-btn" onClick={() => handleAction(action)} style={{ flex: 1 }}>
                      <span style={{ fontSize: 14, width: 22, textAlign: "center", flexShrink: 0 }}>{action.icon}</span>
                      <span style={{ flex: 1 }}>{action.label}</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", opacity: 0.5, display: "flex", alignItems: "center", gap: 4 }}>
                        {action.custom && (
                          <span style={{
                            fontSize: 8, padding: "1px 4px", borderRadius: 3,
                            background: "rgba(180,160,80,0.08)", color: "var(--gold-dim)",
                            letterSpacing: "0.05em",
                          }}>custom</span>
                        )}
                        {action.category}
                      </span>
                    </button>
                    {action.custom && customIndex >= 0 && (
                      <button
                        className="cp-delete-btn"
                        onClick={(e) => { e.stopPropagation(); handleDeleteCustom(customIndex); }}
                        title="Remove custom action"
                      >×</button>
                    )}
                  </div>
                );
              })}
              {filteredActions.length === 0 && (
                <div style={{ padding: "20px 0", textAlign: "center", fontFamily: "var(--font-body)", fontSize: 13, color: "var(--muted)", fontStyle: "italic" }}>
                  No actions match "{paletteSearch}"
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Tools Row: Compass + Weapons + Dice + Result ── */}
        <div style={{
          padding: "8px 16px",
          display: "flex", alignItems: "center", gap: 12,
          borderBottom: "1px solid rgba(180,160,100,0.04)",
        }}>
          {/* Compass */}
          <MiniCompass
            mode={dirMode}
            result={dirResult}
            spinning={dirSpinning}
            onRoll={handleDirRoll}
            onModeToggle={() => { setDirMode(m => m === "cardinal" ? "relative" : "cardinal"); setDirResult(null); }}
            onSelect={handleDirSelect}
            disabled={isLoading}
          />

          {/* Divider */}
          <div style={{ width: 1, height: 36, background: "var(--border)", flexShrink: 0 }} />

          {/* ── Weapon Attack Buttons ── */}
          {weapons.length > 0 && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {weapons.map((w, i) => (
                  <button
                    key={i}
                    onClick={() => { if (!isLoading) onSendMessage(`I attack with my ${w.name}`); }}
                    disabled={isLoading}
                    style={{
                      padding: "4px 10px", borderRadius: 4, cursor: isLoading ? "default" : "pointer",
                      background: "linear-gradient(135deg, #6b2020, #8b3030)", border: "1px solid #9a4040",
                      fontFamily: "var(--font-label)", fontSize: 10, letterSpacing: "0.08em",
                      color: "#e8c8c8", transition: "all 0.15s",
                      display: "flex", alignItems: "center", gap: 6,
                      whiteSpace: "nowrap",
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = "linear-gradient(135deg, #8b3030, #ab4040)"}
                    onMouseLeave={e => e.currentTarget.style.background = "linear-gradient(135deg, #6b2020, #8b3030)"}
                    title={`${w.name} (${w.damage})`}
                  >
                    <span style={{ fontSize: 12 }}>⚔</span>
                    <span>{w.name}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, opacity: 0.7 }}>{w.damage}</span>
                  </button>
                ))}
              </div>
              {/* Divider */}
              <div style={{ width: 1, height: 36, background: "var(--border)", flexShrink: 0 }} />
            </>
          )}

          {/* Dice selector */}
          <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
            {(Object.keys(DICE_SIDES) as DieType[]).map(dt => (
              <button key={dt}
                className={`die-btn ${selectedDie === dt ? "active" : ""}`}
                onClick={() => setSelectedDie(dt)}
                title={dt}
              >
                <TinyDie type={dt} size={20} color={selectedDie === dt ? "#b8a060" : "rgba(180,160,100,0.25)"} active={selectedDie === dt} />
              </button>
            ))}
          </div>

          {/* Count / mod / roll */}
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {/* Count */}
            <div style={{
              display: "flex", alignItems: "center",
              background: "var(--bg-deep)", borderRadius: 3,
              border: "1px solid var(--border)", overflow: "hidden",
            }}>
              <button className="cp-count-btn" onClick={() => setDiceCount(Math.max(1, diceCount - 1))}
                style={{ borderRight: "1px solid var(--border)", color: diceCount > 1 ? "var(--text-dim)" : "rgba(180,160,100,0.12)" }}
              >−</button>
              <span style={{ width: 18, textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: "var(--text)" }}>{diceCount}</span>
              <button className="cp-count-btn" onClick={() => setDiceCount(Math.min(8, diceCount + 1))}
                style={{ borderLeft: "1px solid var(--border)" }}
              >+</button>
            </div>

            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--gold)", fontWeight: 600 }}>{selectedDie}</span>

            {/* Modifier */}
            <div style={{
              display: "flex", alignItems: "center",
              background: "var(--bg-deep)", borderRadius: 3,
              border: "1px solid var(--border)", overflow: "hidden",
            }}>
              <button className="cp-count-btn" onClick={() => setDiceMod(diceMod - 1)}
                style={{ width: 16, borderRight: "1px solid var(--border)" }}
              >−</button>
              <span style={{
                minWidth: 22, textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 500,
                color: diceMod === 0 ? "var(--muted)" : diceMod > 0 ? "#5a8a5a" : "#c44",
              }}>{diceMod > 0 ? `+${diceMod}` : diceMod}</span>
              <button className="cp-count-btn" onClick={() => setDiceMod(diceMod + 1)}
                style={{ width: 16, borderLeft: "1px solid var(--border)" }}
              >+</button>
            </div>

            {/* Roll button */}
            <button onClick={handleDiceRoll} disabled={diceRolling || isLoading} style={{
              padding: "4px 14px", borderRadius: 3, cursor: diceRolling || isLoading ? "default" : "pointer",
              background: diceRolling ? "var(--bg-card)" : "linear-gradient(135deg, #5a4018, #7a6028)",
              border: `1px solid ${diceRolling ? "var(--border)" : "var(--gold-dim)"}`,
              fontFamily: "var(--font-label)", fontSize: 9, fontWeight: 600,
              letterSpacing: "0.1em", color: diceRolling ? "var(--muted)" : "#e0d8c0",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => { if (!diceRolling && !isLoading) e.currentTarget.style.background = "linear-gradient(135deg, #7a6028, #9a8038)"; }}
            onMouseLeave={e => { if (!diceRolling && !isLoading) e.currentTarget.style.background = "linear-gradient(135deg, #5a4018, #7a6028)"; }}
            >ROLL</button>
          </div>

          {/* Result display */}
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6, minWidth: 0 }}>
            {lastRoll && lastRoll.settling && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, animation: "resultPop 0.25s ease" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{diceNotation}:</span>
                {lastRoll.dice.length > 1 && (
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "rgba(180,160,100,0.25)" }}>
                    [{lastRoll.dice.join(",")}]
                  </span>
                )}
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 700,
                  color: (lastRoll.type === "d20" && lastRoll.dice[0] === 20) ? "var(--gold-bright)" :
                         (lastRoll.type === "d20" && lastRoll.dice[0] === 1) ? "#c44" : "var(--text)",
                }}>{lastRoll.total}</span>
                {lastRoll.type === "d20" && lastRoll.dice[0] === 20 && (
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--gold-bright)", letterSpacing: "0.06em" }}>NAT20</span>
                )}
                {lastRoll.type === "d20" && lastRoll.dice[0] === 1 && (
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "#c44", letterSpacing: "0.06em" }}>FUMBLE</span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* ── Input Row ── */}
        <div style={{
          padding: "10px 16px 14px",
          display: "flex", alignItems: "flex-end", gap: 8,
        }}>
          {/* Command palette trigger */}
          <button
            onClick={() => { setPaletteOpen(!paletteOpen); setPaletteSearch(""); }}
            style={{
              width: 36, height: 36, borderRadius: 6, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              background: paletteOpen ? "rgba(180,160,80,0.1)" : "var(--bg-card)",
              border: `1px solid ${paletteOpen ? "var(--gold-dim)" : "var(--border)"}`,
              cursor: "pointer", transition: "all 0.15s",
              fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 600,
              color: paletteOpen ? "var(--gold)" : "var(--muted)",
            }}
            onMouseEnter={e => { if (!paletteOpen) { e.currentTarget.style.borderColor = "var(--border-strong)"; e.currentTarget.style.color = "var(--text-dim)"; }}}
            onMouseLeave={e => { if (!paletteOpen) { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.color = "var(--muted)"; }}}
            title="Command palette ( / )"
          >/</button>

          {/* Text input */}
          <textarea
            ref={textRef}
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder='What do you do?  ( / for actions )'
            rows={1}
            disabled={isLoading}
            style={{
              flex: 1, padding: "8px 12px", borderRadius: 6,
              background: "var(--bg-input)", border: "1px solid var(--border)",
              fontFamily: "var(--font-body)", fontSize: 15, lineHeight: 1.5,
              color: "var(--text)", minHeight: 38, maxHeight: 100,
              opacity: isLoading ? 0.6 : 1,
              resize: "none",
            }}
            onFocus={e => e.currentTarget.style.borderColor = "var(--gold-dim)"}
            onBlur={e => e.currentTarget.style.borderColor = "var(--border)"}
          />

          {/* Send */}
          <button onClick={handleSend} disabled={isLoading || !inputText.trim()} style={{
            width: 36, height: 36, borderRadius: 6, cursor: isLoading ? "wait" : "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            background: inputText.trim() && !isLoading ? "linear-gradient(135deg, #7a6028, #b8a060)" : "var(--bg-card)",
            border: inputText.trim() && !isLoading ? "1px solid var(--gold)" : "1px solid var(--border)",
            transition: "all 0.2s", flexShrink: 0,
          }}>
            {isLoading ? (
              <div style={{
                width: 16, height: 16,
                border: "2px solid var(--muted)", borderTopColor: "transparent",
                borderRadius: "50%", animation: "spin 1s linear infinite",
              }} />
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                stroke={inputText.trim() ? "#1a1a14" : "var(--muted)"}
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
              >
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </>
  );
}

export default BottomControlPanel;
