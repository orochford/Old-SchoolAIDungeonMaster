import { useState, useRef, useEffect, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/services/api";
import DiceBoardPanel, { DiceBoardPanelHandle } from "./DiceBoardPanel";
import { PlayerMapPanel } from "@/components/graph/PlayerMapPanel";
import { BottomControlPanel } from "./BottomControlPanel";

const AeyeLogo = ({ size = 28, color = "#b8a060" }: { size?: number; color?: string }) => (
  <svg width={size} height={size} viewBox="0 0 80 80" fill="none" style={{ flexShrink: 0 }}>
    <path d="M4,40 Q40,8 76,40 Q40,72 4,40Z" stroke={color} strokeWidth="2.5" fill="none" />
    <polygon points="40,22 56,31 56,49 40,58 24,49 24,31" stroke={color} strokeWidth="1.8" fill="none" />
    <line x1="40" y1="22" x2="40" y2="58" stroke={color} strokeWidth="0.7" opacity="0.25" />
    <line x1="24" y1="31" x2="56" y2="49" stroke={color} strokeWidth="0.7" opacity="0.25" />
    <line x1="56" y1="31" x2="24" y2="49" stroke={color} strokeWidth="0.7" opacity="0.25" />
    <circle cx="40" cy="40" r="5" fill={color} opacity="0.85" />
    <circle cx="38" cy="38" r="1.5" fill="#0f0d0a" opacity="0.4" />
  </svg>
);

/* ─── TYPE DEFINITIONS ─── */
export interface CharacterData {
  name: string;
  class: string;
  level: number;
  alignment?: string;
  race?: string;
  hp: { current: number; max: number };
  ac: number;
  thac0: number;
  xp: { current: number; next: number };
  movement?: number;
  abilities: Record<string, { score: number; mod: string }>;
  saves: Record<string, number>;
  weapons: { name: string; damage: string; speed?: number; melee?: boolean; thrown?: boolean }[];
  armor?: string;
  gold?: number;
  equipment: string[];
  conditions?: string[];
  languages?: string[];
  spells?: {
    slotsPerLevel: Record<string, { total: number; used: number }>;
    prepared: { name: string; level: number; prepared: boolean; cast: boolean; description: string }[];
    known: { name: string; level: number; description: string }[];
  };
}

export interface CompanionData {
  name: string;
  type: string;
  detail: string;
  hp: string;
  loyalty: string;
  status: string;
  notes: string;
}

export interface NPCData {
  name: string;
  disposition: string;
  location: string;
  lastSeen: string;
  notes: string;
}

export interface LocationData {
  name: string;
  status: string;
  notes: string;
}

export interface MessageData {
  id: string | number;
  type: "dm" | "player" | "roll" | "system" | "tool";
  text?: string;
  content?: string;
  label?: string;
  target?: string;
  roll?: string;
  result?: number;
  success?: boolean;
  timestamp?: string;
  toolName?: string;
}

export interface GameLogEntry {
  type: "location" | "event" | "combat" | "loot" | "danger";
  text: string;
}

export interface TimeData {
  formatted_date?: string;
  formatted_time?: string;
  time_of_day?: string;
  weather?: string;
}

export interface MapData {
  map_id: string;
  map_name: string;
  rendered_map: string;
  width: number;
  height: number;
  player_position: { x: number; y: number } | null;
  markers: { id: string; x: number; y: number; symbol: string; label: string; type: string }[];
  exploration_progress?: string;
}

export interface OSRPlayInterfaceProps {
  character: CharacterData;
  companions?: CompanionData[];
  npcs?: NPCData[];
  locations?: LocationData[];
  messages: MessageData[];
  gameLog?: GameLogEntry[];
  timeData?: TimeData | null;
  mapData?: MapData | null;
  isConnected?: boolean;
  isLoading?: boolean;
  streamingContent?: string;
  currentLocation?: string;
  onSendMessage: (text: string) => void;
  onLeave?: () => void;
  onRoll?: (notation: string) => void;
  adventureTitle?: string;
  campaignName?: string;
  onOpenConfig?: () => void;
  sessionId?: string;
  adventureDocumentId?: string;
}

/* ─── COMPONENTS ─── */

const HPBar = ({ current, max }: { current: number; max: number }) => {
  const pct = Math.max(0, (current / max) * 100);
  const critical = pct <= 25;
  const wounded = pct <= 50;
  return (
    <div style={{ marginBottom: 2 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 5 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "#c44", fontSize: 14 }}>♥</span>
          <span style={{ fontFamily: "var(--font-label)", fontSize: 11, letterSpacing: "0.15em", color: "var(--muted)" }}>HIT POINTS</span>
        </div>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600, color: critical ? "#c44" : wounded ? "#c90" : "var(--text)" }}>
          {current}<span style={{ opacity: 0.4, fontSize: 13 }}>/{max}</span>
        </span>
      </div>
      <div style={{ height: 6, background: "var(--bg-deep)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{
          height: "100%", width: `${pct}%`, borderRadius: 3,
          background: critical ? "linear-gradient(90deg, #8b0000, #c44)" : wounded ? "linear-gradient(90deg, #6b4c00, #c90)" : "linear-gradient(90deg, #7a3030, #c44)",
          transition: "width 0.8s ease",
          boxShadow: critical ? "0 0 8px rgba(204,68,68,0.3)" : "none",
        }} />
      </div>
    </div>
  );
};

const StatBox = ({ label, value, icon }: { label: string; value: number | string; icon: string }) => (
  <div style={{
    flex: 1, textAlign: "center", padding: "10px 4px",
    background: "var(--bg-card)", border: "1px solid var(--border)",
    borderRadius: 4,
  }}>
    <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>{icon}</div>
    <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 600, color: "var(--text)", lineHeight: 1 }}>{value}</div>
    <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.18em", color: "var(--muted)", marginTop: 4 }}>{label}</div>
  </div>
);

const AbilityScore = ({ name, score, mod }: { name: string; score: number; mod: string }) => (
  <div style={{ textAlign: "center", padding: "6px 0" }}>
    <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.18em", color: "var(--muted)", marginBottom: 3 }}>{name}</div>
    <div style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600, color: "var(--text)", lineHeight: 1 }}>{score}</div>
    <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: mod === "0" ? "var(--muted)" : mod.startsWith("+") ? "var(--gold)" : "#c44", marginTop: 2 }}>{mod}</div>
  </div>
);

const WeaponSlot = ({ weapon, onAttack }: { weapon: CharacterData["weapons"][0]; onAttack: () => void }) => (
  <div style={{
    display: "flex", alignItems: "center", justifyContent: "space-between",
    padding: "8px 10px", marginBottom: 4,
    background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4,
  }}>
    <div>
      <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text)" }}>{weapon.name}</div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>Dmg: {weapon.damage}</div>
    </div>
    <button onClick={onAttack} style={{
      padding: "4px 12px", borderRadius: 4, cursor: "pointer",
      background: "linear-gradient(135deg, #6b2020, #8b3030)", border: "1px solid #9a4040",
      fontFamily: "var(--font-label)", fontSize: 10, letterSpacing: "0.1em",
      color: "#e8c8c8", transition: "all 0.15s",
    }}
    onMouseEnter={e => e.currentTarget.style.background = "linear-gradient(135deg, #8b3030, #ab4040)"}
    onMouseLeave={e => e.currentTarget.style.background = "linear-gradient(135deg, #6b2020, #8b3030)"}
    >⚔ Attack</button>
  </div>
);


const RollResult = ({ msg }: { msg: MessageData }) => (
  <div className="msg-enter" style={{
    display: "flex", alignItems: "center", justifyContent: "center", gap: 16,
    padding: "10px 20px", margin: "6px auto", maxWidth: 460, borderRadius: 4,
    background: "rgba(20,18,14,0.7)",
    border: `1px solid ${msg.success ? "rgba(180,160,80,0.2)" : "rgba(140,60,60,0.25)"}`,
  }}>
    <span style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--muted)" }}>{msg.label}</span>
    <span style={{ fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--text)" }}>
      {msg.roll}: <strong>{msg.result}</strong>
      <span style={{ opacity: 0.5 }}> (need {msg.target})</span>
    </span>
    <span style={{
      fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
      letterSpacing: "0.1em", textTransform: "uppercase",
      color: msg.success ? "var(--gold)" : "#c44",
      padding: "2px 8px", borderRadius: 3,
      background: msg.success ? "rgba(180,160,80,0.12)" : "rgba(140,60,60,0.12)",
    }}>{msg.success ? "Success" : "Failure"}</span>
  </div>
);

const GameLogEntryComponent = ({ entry }: { entry: GameLogEntry }) => {
  const colors: Record<string, string> = { location: "#7a9ab8", event: "var(--text-dim)", combat: "#c44", loot: "var(--gold)", danger: "#c44" };
  const icons: Record<string, string> = { location: "▸", event: "◦", combat: "⚔", loot: "◈", danger: "▲" };
  return (
    <div style={{ padding: "4px 0", display: "flex", gap: 8, alignItems: "flex-start" }}>
      <span style={{ color: colors[entry.type], fontSize: 10, marginTop: 3, flexShrink: 0 }}>{icons[entry.type]}</span>
      <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: colors[entry.type], lineHeight: 1.4 }}>{entry.text}</span>
    </div>
  );
};

const CompanionCard = ({ companion, expanded, onToggle }: { companion: CompanionData; expanded: boolean; onToggle: () => void }) => (
  <div style={{ marginBottom: 4 }}>
    <button onClick={onToggle} style={{
      width: "100%", textAlign: "left",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "8px 10px", borderRadius: 4, cursor: "pointer",
      background: "var(--bg-card)", border: "1px solid var(--border)",
      transition: "all 0.15s",
    }}
    onMouseEnter={e => e.currentTarget.style.borderColor = "var(--border-strong)"}
    onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 12 }}>{companion.type === "War Dog" ? "🐕" : "👤"}</span>
        <div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text)" }}>{companion.name}</div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{companion.detail}</div>
        </div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: companion.hp.split("/")[0] === companion.hp.split("/")[1] ? "var(--text-dim)" : "#c44" }}>
          ♥ {companion.hp}
        </div>
      </div>
    </button>
    {expanded && (
      <div style={{
        padding: "8px 12px", marginTop: 2, borderRadius: "0 0 4px 4px",
        background: "rgba(180,160,80,0.03)", borderLeft: "2px solid var(--gold-dim)",
        marginLeft: 8,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontFamily: "var(--font-body)", fontSize: 11, color: "var(--muted)" }}>Loyalty</span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: companion.loyalty === "Loyal" ? "var(--gold)" : "var(--text-dim)" }}>{companion.loyalty}</span>
        </div>
        <div style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--text-dim)", fontStyle: "italic", lineHeight: 1.4 }}>
          {companion.notes}
        </div>
      </div>
    )}
  </div>
);

const NPCCard = ({ npc, expanded, onToggle }: { npc: NPCData; expanded: boolean; onToggle: () => void }) => {
  const dispColors: Record<string, string> = { Friendly: "#5a8a5a", Helpful: "var(--gold)", Neutral: "var(--text-dim)", Wary: "#c90", Hostile: "#c44" };
  return (
    <div style={{ marginBottom: 4 }}>
      <button onClick={onToggle} style={{
        width: "100%", textAlign: "left",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "7px 10px", borderRadius: 4, cursor: "pointer",
        background: "transparent", border: "1px solid transparent",
        transition: "all 0.15s",
      }}
      onMouseEnter={e => e.currentTarget.style.background = "rgba(180,160,100,0.04)"}
      onMouseLeave={e => e.currentTarget.style.background = "transparent"}
      >
        <div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text)" }}>{npc.name}</div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{npc.location}</div>
        </div>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.06em",
          color: dispColors[npc.disposition] || "var(--text-dim)",
          padding: "2px 6px", borderRadius: 3,
          background: `${dispColors[npc.disposition] || "var(--text-dim)"}15`,
        }}>{npc.disposition}</span>
      </button>
      {expanded && (
        <div style={{
          padding: "6px 12px 8px", marginLeft: 8,
          borderLeft: `2px solid ${dispColors[npc.disposition] || "var(--border)"}40`,
        }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", marginBottom: 4 }}>
            Last seen: {npc.lastSeen}
          </div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--text-dim)", fontStyle: "italic", lineHeight: 1.4 }}>
            {npc.notes}
          </div>
        </div>
      )}
    </div>
  );
};

const LocationEntry = ({ loc }: { loc: LocationData }) => {
  const statusColors: Record<string, string> = { Safe: "#5a8a5a", Cleared: "var(--text-dim)", Unexplored: "var(--muted)", Active: "var(--gold)" };
  const statusIcons: Record<string, string> = { Safe: "🏠", Cleared: "✓", Unexplored: "?", Active: "⚑" };
  return (
    <div style={{
      padding: "6px 10px", marginBottom: 3, borderRadius: 3,
      borderLeft: `2px solid ${statusColors[loc.status] || "var(--border)"}`,
      background: loc.status === "Active" ? "rgba(180,160,80,0.04)" : "transparent",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontFamily: "var(--font-body)", fontSize: 13, color: loc.status === "Active" ? "var(--text)" : "var(--text-dim)" }}>{loc.name}</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: statusColors[loc.status] }}>{statusIcons[loc.status]} {loc.status}</span>
      </div>
      <div style={{ fontFamily: "var(--font-body)", fontSize: 11, color: "var(--muted)", fontStyle: "italic", marginTop: 2 }}>{loc.notes}</div>
    </div>
  );
};

/* ─── MAIN COMPONENT ─── */
export function OSRPlayInterface({
  character,
  companions = [],
  npcs = [],
  locations = [],
  messages,
  gameLog = [],
  timeData,
  mapData,
  isConnected = false,
  isLoading = false,
  streamingContent = "",
  currentLocation = "Unknown",
  onSendMessage,
  onLeave,
  onRoll: _onRoll,
  adventureTitle = "",
  campaignName: _campaignName = "",
  onOpenConfig,
  sessionId,
  adventureDocumentId,
}: OSRPlayInterfaceProps) {
  const [leftTab, setLeftTab] = useState("character");
  const [rightTab, setRightTab] = useState("world");
  const [expandedSpell, setExpandedSpell] = useState<string | null>(null);
  const [expandedNPC, setExpandedNPC] = useState<string | null>(null);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [editingEquipIndex, setEditingEquipIndex] = useState<number | null>(null);
  const [editingEquipValue, setEditingEquipValue] = useState("");
  const [showAddEquip, setShowAddEquip] = useState(false);
  const [newEquipValue, setNewEquipValue] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const dicePanelRef = useRef<DiceBoardPanelHandle>(null);
  const suppressDiceChat = useRef(false);

  // Resolve module ID from adventure document ID for player map
  const { data: adventureModule } = useQuery({
    queryKey: ["adventure-module-by-doc", adventureDocumentId],
    queryFn: () => api.get<{ id: string }>(`/adventures/by-document/${adventureDocumentId}`),
    enabled: !!adventureDocumentId,
  });
  const moduleId = adventureModule?.id;

  // Load theme from localStorage
  useEffect(() => {
    const savedTheme = localStorage.getItem("osr-theme");
    if (savedTheme === "light" || savedTheme === "dark") {
      setTheme(savedTheme);
    }
  }, []);

  // Toggle theme
  const toggleTheme = () => {
    const newTheme = theme === "dark" ? "light" : "dark";
    setTheme(newTheme);
    localStorage.setItem("osr-theme", newTheme);
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Render markdown bold text
  const renderBold = (text: string): ReactNode => {
    return text.split(/(\*\*.*?\*\*)/).map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={i} style={{ color: "var(--gold-bright)", fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
      }
      return <span key={i}>{part}</span>;
    });
  };

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700&family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400&family=IBM+Plex+Mono:wght@300;400;500;600&display=swap');

        :root, [data-theme="dark"] {
          --bg: #0f0d0a;
          --bg-panel: #141210;
          --bg-card: rgba(255,245,220,0.03);
          --bg-deep: #0a0908;
          --bg-input: #1a1816;
          --border: rgba(180,160,100,0.1);
          --border-strong: rgba(180,160,100,0.2);
          --text: #c8c0aa;
          --text-dim: #8a8270;
          --muted: #6a6250;
          --gold: #b8a060;
          --gold-dim: rgba(180,160,80,0.4);
          --gold-bright: #d4b870;
          --dm-accent: rgba(180,160,80,0.06);
          --player-accent: rgba(100,140,180,0.06);
          --font-display: 'Cinzel', serif;
          --font-body: 'Crimson Text', serif;
          --font-label: 'Cinzel', serif;
          --font-mono: 'IBM Plex Mono', monospace;
        }

        [data-theme="light"] {
          --bg: #f5f0e6;
          --bg-panel: #ebe5d8;
          --bg-card: rgba(100,80,40,0.05);
          --bg-deep: #e0d8c8;
          --bg-input: #fff9ee;
          --border: rgba(100,80,40,0.15);
          --border-strong: rgba(100,80,40,0.25);
          --text: #3a3428;
          --text-dim: #6a6050;
          --muted: #8a8070;
          --gold: #8a6a20;
          --gold-dim: rgba(140,110,40,0.3);
          --gold-bright: #6a4a10;
          --dm-accent: rgba(140,110,40,0.08);
          --player-accent: rgba(60,100,140,0.08);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(180,160,100,0.12); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: rgba(180,160,100,0.22); }

        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .msg-enter { animation: fadeUp 0.35s ease forwards; }

        textarea { font-family: var(--font-body); color: var(--text); background: transparent; resize: none; border: none; }
        textarea::placeholder { color: rgba(180,160,100,0.25); }
        textarea:focus { outline: none; }

        .panel-tab {
          background: none; border: none; cursor: pointer;
          font-family: var(--font-label); font-size: 10px;
          letter-spacing: 0.14em; text-transform: uppercase;
          padding: 8px 12px; color: var(--muted);
          border-bottom: 1.5px solid transparent;
          transition: all 0.2s;
        }
        .panel-tab:hover { color: var(--text-dim); }
        .panel-tab.active { color: var(--gold); border-bottom-color: var(--gold); }
      `}</style>

      {/* NOISE TEXTURE */}
      <div style={{
        position: "fixed", inset: 0, pointerEvents: "none", zIndex: 9999, opacity: 0.025,
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        backgroundSize: "128px 128px",
      }} />

      <div data-theme={theme} style={{
        position: "fixed",
        top: 0, left: 0, right: 0, bottom: 0,
        display: "grid",
        gridTemplateColumns: "250px 1fr 270px",
        gridTemplateRows: "50px 1fr",
        background: "var(--bg)",
        overflow: "hidden",
        zIndex: 50,
      }}>

        {/* ═══ TOP BAR ═══ */}
        <header style={{
          gridColumn: "1 / -1",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 20px",
          background: "var(--bg-panel)",
          borderBottom: "1px solid var(--border)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button
              onClick={onLeave}
              style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontFamily: "var(--font-body)", fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}
            >
              ← Leave
            </button>
            <div style={{ width: 1, height: 22, background: "var(--border)" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <AeyeLogo size={26} />
              <span style={{ fontFamily: "var(--font-display)", fontSize: 15, fontWeight: 600, letterSpacing: "0.08em", color: "var(--text)" }}>
                OSR <span style={{ color: "var(--gold)" }}>AEYE</span>
              </span>
            </div>
            {adventureTitle && (
              <>
                <div style={{ width: 1, height: 22, background: "var(--border)" }} />
                <span style={{ fontFamily: "var(--font-body)", fontSize: 14, fontStyle: "italic", color: "var(--muted)" }}>
                  {adventureTitle}
                </span>
              </>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* Settings button */}
            {onOpenConfig && (
              <button
                onClick={onOpenConfig}
                style={{
                  background: "none", border: "1px solid var(--border)", borderRadius: 4,
                  padding: "4px 8px", cursor: "pointer", fontSize: 12,
                  color: "var(--muted)", fontFamily: "var(--font-mono)",
                }}
                title="Game settings"
              >
                ⚙️
              </button>
            )}
            {/* Theme toggle */}
            <button
              onClick={toggleTheme}
              style={{
                background: "none", border: "1px solid var(--border)", borderRadius: 4,
                padding: "4px 8px", cursor: "pointer", fontSize: 12,
                color: "var(--muted)", fontFamily: "var(--font-mono)",
              }}
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            >
              {theme === "dark" ? "☀️" : "🌙"}
            </button>
            {isConnected ? (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#5a5" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#5a5" }}>Connected</span>
              </div>
            ) : (
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#c44" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#c44" }}>Disconnected</span>
              </div>
            )}
          </div>
        </header>

        {/* ═══ LEFT PANEL — CHARACTER SHEET ═══ */}
        <aside style={{
          background: "var(--bg-panel)",
          borderRight: "1px solid var(--border)",
          overflowY: "auto", overflowX: "hidden",
          display: "flex", flexDirection: "column",
        }}>
          {/* Tab bar */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
            {[["character", "Stats"], ["spells", "Spells"], ["equip", "Gear"], ["dice", "Dice"]].map(([key, label]) => (
              <button key={key} className={`panel-tab ${leftTab === key ? "active" : ""}`} onClick={() => setLeftTab(key)} style={{ flex: 1 }}>
                {label}
              </button>
            ))}
          </div>

          <div style={{ padding: "16px 14px", flex: 1, overflowY: "auto" }}>
            {leftTab === "character" && (
              <>
                {/* Name & Class */}
                <div style={{ marginBottom: 16, paddingBottom: 14, borderBottom: "1px solid var(--border)" }}>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: 16, fontWeight: 600, color: "var(--text)", marginBottom: 2 }}>
                    {character.name}
                  </div>
                  <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--gold)", fontStyle: "italic" }}>
                    Level {character.level} {character.race} {character.class} · {character.alignment}
                  </div>
                </div>

                {/* HP */}
                <HPBar current={character.hp.current} max={character.hp.max} />

                {/* XP Bar */}
                <div style={{ marginTop: 10, marginBottom: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)" }}>EXPERIENCE</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-dim)" }}>
                      {character.xp.current.toLocaleString()}<span style={{ opacity: 0.4 }}>/{character.xp.next.toLocaleString()}</span>
                    </span>
                  </div>
                  <div style={{ height: 3, background: "var(--bg-deep)", borderRadius: 2, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", width: `${Math.min(100, (character.xp.current / character.xp.next) * 100)}%`, borderRadius: 2,
                      background: "linear-gradient(90deg, rgba(180,160,80,0.3), var(--gold))",
                    }} />
                  </div>
                </div>

                {/* AC & THAC0 */}
                <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
                  <StatBox label="AC" value={character.ac} icon="🛡" />
                  <StatBox label="THAC0" value={character.thac0} icon="⚔" />
                  <StatBox label="MV" value={character.movement || 120} icon="👣" />
                </div>

                {/* Ability Scores */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>ABILITY SCORES</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4, padding: 6 }}>
                    {Object.entries(character.abilities).map(([name, { score, mod }]) => (
                      <AbilityScore key={name} name={name} score={score} mod={mod} />
                    ))}
                  </div>
                </div>

                {/* Saving Throws */}
                <div>
                  <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>SAVING THROWS</div>
                  <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4, padding: "8px 10px" }}>
                    {Object.entries(character.saves).map(([name, val], i, arr) => (
                      <div key={name} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: i < arr.length - 1 ? "1px solid rgba(180,160,100,0.04)" : "none" }}>
                        <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--text-dim)", textTransform: "capitalize" }}>{name}</span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)" }}>{val}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {leftTab === "spells" && character.spells && (
              <>
                {/* Spell Slots */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>SPELL SLOTS</div>
                  <div style={{ display: "flex", gap: 8 }}>
                    {Object.entries(character.spells.slotsPerLevel).map(([lvl, { total, used }]) => (
                      <div key={lvl} style={{
                        flex: 1, textAlign: "center", padding: "10px 6px",
                        background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4,
                      }}>
                        <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.12em", color: "var(--muted)", marginBottom: 6 }}>LEVEL {lvl}</div>
                        <div style={{ display: "flex", justifyContent: "center", gap: 4 }}>
                          {Array.from({ length: total }).map((_, i) => (
                            <div key={i} style={{
                              width: 12, height: 12, borderRadius: "50%",
                              border: `1.5px solid ${i < used ? "var(--muted)" : "var(--gold)"}`,
                              background: i < used ? "transparent" : "var(--gold)",
                              opacity: i < used ? 0.4 : 1,
                              transition: "all 0.2s",
                            }} />
                          ))}
                        </div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-dim)", marginTop: 4 }}>
                          {total - used}/{total}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Prepared Spells */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>PREPARED</div>
                  {character.spells.prepared.map((spell, i) => (
                    <div key={i} style={{ marginBottom: 4 }}>
                      <button
                        onClick={() => setExpandedSpell(expandedSpell === `p-${i}` ? null : `p-${i}`)}
                        style={{
                          width: "100%", textAlign: "left",
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "8px 10px", borderRadius: 4, cursor: "pointer",
                          background: spell.cast ? "rgba(140,60,60,0.06)" : "rgba(180,160,80,0.06)",
                          border: `1px solid ${spell.cast ? "rgba(140,60,60,0.15)" : "rgba(180,160,80,0.12)"}`,
                          transition: "all 0.15s",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 11 }}>{spell.cast ? "○" : "✦"}</span>
                          <div>
                            <div style={{
                              fontFamily: "var(--font-body)", fontSize: 13,
                              color: spell.cast ? "var(--muted)" : "var(--text)",
                              textDecoration: spell.cast ? "line-through" : "none",
                              textDecorationColor: "rgba(140,60,60,0.4)",
                            }}>{spell.name}</div>
                          </div>
                        </div>
                        <span style={{
                          fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)",
                          padding: "1px 6px", borderRadius: 3,
                          background: "rgba(180,160,100,0.06)",
                        }}>Lv.{spell.level}</span>
                      </button>
                      {expandedSpell === `p-${i}` && (
                        <div style={{
                          padding: "8px 10px 8px 30px", marginTop: 2,
                          fontFamily: "var(--font-body)", fontSize: 12, fontStyle: "italic",
                          color: "var(--text-dim)", lineHeight: 1.5,
                          borderLeft: "2px solid rgba(180,160,80,0.15)",
                          marginLeft: 10,
                        }}>
                          {spell.description}
                          {!spell.cast && (
                            <button style={{
                              display: "block", marginTop: 6,
                              padding: "3px 10px", borderRadius: 3, cursor: "pointer",
                              background: "rgba(180,160,80,0.1)", border: "1px solid rgba(180,160,80,0.2)",
                              fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.08em",
                              color: "var(--gold)", transition: "all 0.15s",
                            }}
                            onMouseEnter={e => e.currentTarget.style.background = "rgba(180,160,80,0.18)"}
                            onMouseLeave={e => e.currentTarget.style.background = "rgba(180,160,80,0.1)"}
                            onClick={(e) => { e.stopPropagation(); onSendMessage(`I cast ${spell.name}`); }}
                            >✦ Cast</button>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Spell Book / Known */}
                <div>
                  <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>SPELL BOOK</div>
                  {[1, 2, 3, 4, 5].map(level => {
                    const spells = character.spells?.known.filter(s => s.level === level) || [];
                    if (spells.length === 0) return null;
                    return (
                      <div key={level} style={{ marginBottom: 12 }}>
                        <div style={{
                          fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)",
                          marginBottom: 4, padding: "2px 0",
                          borderBottom: "1px solid rgba(180,160,100,0.06)",
                        }}>Level {level}</div>
                        {spells.map((spell, i) => (
                          <div key={i}>
                            <button
                              onClick={() => setExpandedSpell(expandedSpell === `k-${level}-${i}` ? null : `k-${level}-${i}`)}
                              style={{
                                width: "100%", textAlign: "left",
                                display: "flex", alignItems: "center", justifyContent: "space-between",
                                padding: "5px 8px", borderRadius: 3, cursor: "pointer",
                                background: "transparent", border: "1px solid transparent",
                                transition: "all 0.15s",
                              }}
                              onMouseEnter={e => e.currentTarget.style.background = "rgba(180,160,100,0.04)"}
                              onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                            >
                              <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--text-dim)" }}>{spell.name}</span>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)", transform: expandedSpell === `k-${level}-${i}` ? "rotate(90deg)" : "none", transition: "transform 0.15s" }}>▸</span>
                            </button>
                            {expandedSpell === `k-${level}-${i}` && (
                              <div style={{
                                padding: "4px 8px 8px 16px",
                                fontFamily: "var(--font-body)", fontSize: 11, fontStyle: "italic",
                                color: "var(--muted)", lineHeight: 1.4,
                              }}>
                                {spell.description}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            {/* Spells tab empty state */}
            {leftTab === "spells" && !character.spells && (
              <div style={{ textAlign: "center", padding: "20px 10px" }}>
                <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.3 }}>📖</div>
                <div style={{ fontFamily: "var(--font-body)", fontSize: 13, fontStyle: "italic", color: "var(--muted)", marginBottom: 8 }}>
                  No spellcasting ability
                </div>
                <div style={{ fontFamily: "var(--font-body)", fontSize: 11, color: "var(--text-dim)" }}>
                  This character cannot cast spells.
                </div>
              </div>
            )}

            {leftTab === "equip" && (
              <>
                {/* Gold */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>GOLD</div>
                  <div style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "10px 12px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4
                  }}>
                    <span style={{ fontSize: 16 }}>🪙</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600, color: "var(--gold)" }}>
                      {(character.gold || 0).toLocaleString()}
                    </span>
                    <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--muted)" }}>gp</span>
                  </div>
                </div>

                {/* Armor */}
                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>ARMOR</div>
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 12px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 14 }}>🛡</span>
                      <span style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text)" }}>
                        {character.armor || "Unarmored"}
                      </span>
                    </div>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" }}>
                      AC {character.ac}
                    </span>
                  </div>
                </div>

                {/* Equipment */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)" }}>EQUIPMENT</div>
                    <button
                      onClick={() => setShowAddEquip(!showAddEquip)}
                      style={{
                        background: showAddEquip ? "rgba(180,160,80,0.15)" : "transparent",
                        border: `1px dashed ${showAddEquip ? "var(--gold)" : "var(--border)"}`,
                        borderRadius: 3,
                        padding: "2px 8px",
                        cursor: "pointer",
                        fontFamily: "var(--font-mono)",
                        fontSize: 10,
                        color: showAddEquip ? "var(--gold)" : "var(--muted)",
                        transition: "all 0.15s",
                      }}
                      onMouseEnter={e => { if (!showAddEquip) e.currentTarget.style.color = "var(--gold)"; }}
                      onMouseLeave={e => { if (!showAddEquip) e.currentTarget.style.color = "var(--muted)"; }}
                    >
                      + Add
                    </button>
                  </div>

                  {/* Add Item Form */}
                  {showAddEquip && (
                    <div style={{
                      display: "flex", gap: 6, marginBottom: 8,
                      padding: "8px", background: "rgba(180,160,80,0.04)",
                      border: "1px solid rgba(180,160,80,0.12)", borderRadius: 4,
                    }}>
                      <input
                        value={newEquipValue}
                        onChange={e => setNewEquipValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === "Enter" && newEquipValue.trim()) {
                            onSendMessage(`[SYSTEM: Add item to inventory: ${newEquipValue.trim()}]`);
                            setNewEquipValue("");
                            setShowAddEquip(false);
                          }
                        }}
                        placeholder="New item..."
                        style={{
                          flex: 1, padding: "4px 8px", borderRadius: 3,
                          background: "var(--bg-input)", border: "1px solid var(--border)",
                          fontFamily: "var(--font-body)", fontSize: 12, color: "var(--text)",
                        }}
                        autoFocus
                      />
                      <button
                        onClick={() => {
                          if (newEquipValue.trim()) {
                            onSendMessage(`[SYSTEM: Add item to inventory: ${newEquipValue.trim()}]`);
                            setNewEquipValue("");
                            setShowAddEquip(false);
                          }
                        }}
                        style={{
                          padding: "4px 10px", borderRadius: 3, cursor: "pointer",
                          background: "rgba(180,160,80,0.15)", border: "1px solid var(--gold-dim)",
                          fontFamily: "var(--font-label)", fontSize: 9, color: "var(--gold)",
                        }}
                      >ADD</button>
                    </div>
                  )}

                  <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4, padding: "6px 10px" }}>
                    {character.equipment.length === 0 ? (
                      <div style={{
                        padding: "12px 0", textAlign: "center",
                        fontFamily: "var(--font-body)", fontSize: 12, fontStyle: "italic", color: "var(--muted)",
                      }}>No equipment</div>
                    ) : (
                      character.equipment.map((item, i) => (
                        <div key={i} style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "5px 0", borderBottom: i < character.equipment.length - 1 ? "1px solid rgba(180,160,100,0.04)" : "none",
                        }}>
                          {editingEquipIndex === i ? (
                            <input
                              value={editingEquipValue}
                              onChange={e => setEditingEquipValue(e.target.value)}
                              onKeyDown={e => {
                                if (e.key === "Enter") {
                                  if (editingEquipValue.trim()) {
                                    onSendMessage(`[SYSTEM: Update inventory item from "${item}" to "${editingEquipValue.trim()}"]`);
                                  }
                                  setEditingEquipIndex(null);
                                } else if (e.key === "Escape") {
                                  setEditingEquipIndex(null);
                                }
                              }}
                              onBlur={() => setEditingEquipIndex(null)}
                              style={{
                                flex: 1, padding: "2px 6px", borderRadius: 3,
                                background: "var(--bg-input)", border: "1px solid var(--gold-dim)",
                                fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text)",
                              }}
                              autoFocus
                            />
                          ) : (
                            <span
                              onClick={() => {
                                setEditingEquipIndex(i);
                                setEditingEquipValue(item);
                              }}
                              style={{
                                fontFamily: "var(--font-body)", fontSize: 13, color: "var(--text-dim)",
                                cursor: "pointer", flex: 1,
                              }}
                              title="Click to edit"
                            >{item}</span>
                          )}
                          <button
                            onClick={() => onSendMessage(`[SYSTEM: Remove item from inventory: ${item}]`)}
                            style={{
                              background: "transparent", border: "none",
                              color: "var(--muted)", cursor: "pointer",
                              fontSize: 12, padding: "0 4px",
                              opacity: 0.5, transition: "all 0.15s",
                            }}
                            onMouseEnter={e => { e.currentTarget.style.color = "#c44"; e.currentTarget.style.opacity = "1"; }}
                            onMouseLeave={e => { e.currentTarget.style.color = "var(--muted)"; e.currentTarget.style.opacity = "0.5"; }}
                            title="Remove item"
                          >×</button>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}

            <div style={{ display: leftTab === "dice" ? "block" : "none" }}>
              <DiceBoardPanel ref={dicePanelRef} onRollResult={(notation, total, rolls, mod) => {
                if (suppressDiceChat.current) {
                  suppressDiceChat.current = false;
                  return;
                }
                const rollDetail = rolls.length > 1 ? ` [${rolls.join(", ")}]` : "";
                const modDetail = mod !== 0 ? (mod > 0 ? ` +${mod}` : ` ${mod}`) : "";
                onSendMessage(`[ROLL] ${notation}: ${total}${rollDetail}${modDetail}`);
              }} />
            </div>
          </div>
        </aside>

        {/* ═══ CENTER — NARRATIVE ═══ */}
        <main style={{ display: "flex", flexDirection: "column", overflow: "hidden", background: "var(--bg)" }}>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "20px 28px" }}>
            {messages.map((msg) => {
              if (msg.type === "roll") return <RollResult key={msg.id} msg={msg} />;
              if (msg.type === "tool") return null; // Hide tool messages or show differently

              const isDM = msg.type !== "player";
              const text = msg.text || msg.content || "";

              return (
                <div key={msg.id} className="msg-enter" style={{
                  marginBottom: 20, padding: "16px 20px",
                  background: isDM ? "var(--dm-accent)" : "var(--player-accent)",
                  borderLeft: `3px solid ${isDM ? "var(--gold-dim)" : "rgba(100,140,180,0.3)"}`,
                  borderRadius: "0 4px 4px 0",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <span style={{
                      fontFamily: "var(--font-label)", fontSize: 10, letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: isDM ? "var(--gold)" : "#7a9ab8",
                    }}>
                      {isDM ? "Dungeon Master" : "You"}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{msg.timestamp}</span>
                  </div>
                  <div style={{
                    fontFamily: "var(--font-body)", fontSize: 15, lineHeight: 1.7,
                    color: "var(--text)", whiteSpace: "pre-wrap",
                  }}>
                    {renderBold(text)}
                  </div>
                </div>
              );
            })}

            {/* Thinking indicator - shows when loading but no streaming yet */}
            {isLoading && !streamingContent && (
              <div className="msg-enter" style={{
                marginBottom: 20, padding: "16px 20px",
                background: "var(--dm-accent)",
                borderLeft: "3px solid var(--gold-dim)",
                borderRadius: "0 4px 4px 0",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{
                    fontFamily: "var(--font-label)", fontSize: 10, letterSpacing: "0.14em",
                    textTransform: "uppercase", color: "var(--gold)",
                  }}>
                    Dungeon Master
                  </span>
                  <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                    <span className="thinking-dot" style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--gold)", animation: "pulse 1.4s ease-in-out infinite" }} />
                    <span className="thinking-dot" style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--gold)", animation: "pulse 1.4s ease-in-out 0.2s infinite" }} />
                    <span className="thinking-dot" style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--gold)", animation: "pulse 1.4s ease-in-out 0.4s infinite" }} />
                  </div>
                </div>
              </div>
            )}

            {/* Streaming content */}
            {streamingContent && (
              <div className="msg-enter" style={{
                marginBottom: 20, padding: "16px 20px",
                background: "var(--dm-accent)",
                borderLeft: "3px solid var(--gold-dim)",
                borderRadius: "0 4px 4px 0",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                  <span style={{
                    fontFamily: "var(--font-label)", fontSize: 10, letterSpacing: "0.14em",
                    textTransform: "uppercase", color: "var(--gold)",
                  }}>
                    Dungeon Master
                  </span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>typing...</span>
                </div>
                <div style={{
                  fontFamily: "var(--font-body)", fontSize: 15, lineHeight: 1.7,
                  color: "var(--text)", whiteSpace: "pre-wrap",
                }}>
                  {renderBold(streamingContent)}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Bottom Control Panel */}
          <BottomControlPanel
            onSendMessage={onSendMessage}
            isLoading={isLoading}
            weapons={character.weapons}
          />
        </main>

        {/* ═══ RIGHT PANEL — WORLD STATE ═══ */}
        <aside style={{
          background: "var(--bg-panel)",
          borderLeft: "1px solid var(--border)",
          overflowY: "auto", overflowX: "hidden",
          display: "flex", flexDirection: "column",
        }}>
          {/* Tab bar */}
          <div style={{ display: "flex", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
            {[["world", "World"], ["log", "Log"], ["map", "Map"]].map(([key, label]) => (
              <button key={key} className={`panel-tab ${rightTab === key ? "active" : ""}`} onClick={() => setRightTab(key)} style={{ flex: 1 }}>
                {label}
              </button>
            ))}
          </div>

          <div style={{ padding: "14px", flex: 1, overflowY: "auto" }}>
            {rightTab === "world" && (
              <>
                {/* Session Status */}
                <div style={{ marginBottom: 16, padding: "10px 12px", background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 4 }}>
                  {/* Connection Status */}
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                    <div style={{ width: 6, height: 6, borderRadius: "50%", background: isConnected ? "#5a5" : "#c44" }} />
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: isConnected ? "#5a5" : "#c44" }}>
                      {isConnected ? "Connected" : "Disconnected"}
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--muted)" }}>Location</span>
                    <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--text)" }}>{currentLocation}</span>
                  </div>
                  {/* Dungeon Turn */}
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--muted)" }}>Dungeon Turn</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)" }}>—</span>
                  </div>
                  {/* Torch Timer */}
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--muted)" }}>Torch</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "#c90" }}>—</span>
                  </div>
                  {timeData && (
                    <>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--muted)" }}>Time</span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)" }}>{timeData.formatted_time || timeData.time_of_day}</span>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between" }}>
                        <span style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--muted)" }}>Weather</span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-dim)" }}>{timeData.weather || "Clear"}</span>
                      </div>
                    </>
                  )}
                </div>

                {/* Companions */}
                {companions.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>COMPANIONS</div>
                    {companions.map((c, i) => (
                      <CompanionCard
                        key={i}
                        companion={c}
                        expanded={expandedNPC === `c-${i}`}
                        onToggle={() => setExpandedNPC(expandedNPC === `c-${i}` ? null : `c-${i}`)}
                      />
                    ))}
                  </div>
                )}

                {/* NPCs */}
                {npcs.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>KNOWN NPCS</div>
                    {npcs.map((npc, i) => (
                      <NPCCard
                        key={i}
                        npc={npc}
                        expanded={expandedNPC === `n-${i}`}
                        onToggle={() => setExpandedNPC(expandedNPC === `n-${i}` ? null : `n-${i}`)}
                      />
                    ))}
                  </div>
                )}

                {/* Locations */}
                {locations.length > 0 && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 8 }}>LOCATIONS</div>
                    {locations.map((loc, i) => (
                      <LocationEntry key={i} loc={loc} />
                    ))}
                  </div>
                )}

                {/* Empty state for World tab */}
                {companions.length === 0 && npcs.length === 0 && locations.length === 0 && (
                  <div style={{ marginTop: 16, padding: "12px", background: "var(--bg-card)", border: "1px dashed var(--border)", borderRadius: 4, textAlign: "center" }}>
                    <div style={{ fontFamily: "var(--font-body)", fontSize: 13, fontStyle: "italic", color: "var(--muted)", marginBottom: 8 }}>
                      No encounters recorded yet.
                    </div>
                    <div style={{ fontFamily: "var(--font-body)", fontSize: 11, color: "var(--text-dim)" }}>
                      NPCs, companions, and discovered locations will appear here as you explore.
                    </div>
                  </div>
                )}
              </>
            )}

            {rightTab === "log" && (
              <div>
                <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 10 }}>SESSION LOG</div>
                {gameLog.length > 0 ? (
                  gameLog.map((entry, i) => <GameLogEntryComponent key={i} entry={entry} />)
                ) : (
                  <div style={{ fontFamily: "var(--font-body)", fontSize: 12, fontStyle: "italic", color: "var(--muted)", padding: "8px 0" }}>
                    No events logged yet.
                  </div>
                )}
              </div>
            )}

            {rightTab === "map" && (
              <div style={{ height: "100%", minHeight: 300 }}>
                {moduleId && sessionId ? (
                  <PlayerMapPanel
                    moduleId={moduleId}
                    sessionId={sessionId}
                    currentLocationKey={undefined}
                  />
                ) : mapData && mapData.rendered_map ? (
                  <div>
                    <div style={{ fontFamily: "var(--font-label)", fontSize: 9, letterSpacing: "0.15em", color: "var(--muted)", marginBottom: 10 }}>{mapData.map_name || "AREA MAP"}</div>
                    <div style={{
                      background: "var(--bg-deep)",
                      border: "1px solid var(--border)",
                      borderRadius: 4,
                      padding: 16,
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      lineHeight: 1.4,
                      whiteSpace: "pre",
                      overflow: "auto",
                      color: "var(--text-dim)",
                    }}>
                      {mapData.rendered_map}
                    </div>
                    {mapData.exploration_progress && (
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", marginTop: 8, textAlign: "center" }}>
                        {mapData.exploration_progress}
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{
                    background: "var(--bg-deep)",
                    border: "1px dashed var(--border)",
                    borderRadius: 4,
                    padding: 24,
                    textAlign: "center",
                  }}>
                    <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.3 }}>🗺️</div>
                    <div style={{ fontFamily: "var(--font-body)", fontSize: 12, fontStyle: "italic", color: "var(--muted)" }}>
                      No map data available yet.
                    </div>
                    <div style={{ fontFamily: "var(--font-body)", fontSize: 11, color: "var(--text-dim)", marginTop: 6 }}>
                      Map will appear as you explore the dungeon.
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
          40% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </>
  );
}

export default OSRPlayInterface;
