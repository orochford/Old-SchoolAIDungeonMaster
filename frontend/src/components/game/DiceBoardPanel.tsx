import React, { useState, useCallback, useRef, forwardRef, useImperativeHandle } from "react";

/* ─── DICE SHAPES ─── */
const DiceShape = ({ type, value, size = 40, color = "#b8a060" }: { type: string; value: string | number; size?: number; color?: string }) => {
  const textStyle = {
    fontFamily: "'Cinzel', serif", fontWeight: 700, fill: "#0f0d0a",
    textAnchor: "middle" as const, dominantBaseline: "central" as const,
  };
  const fs = size < 30 ? 10 : size < 40 ? 13 : 16;

  const shapes: Record<string, React.ReactNode> = {
    d4: <polygon points="30,5 55,53 5,53" fill={color} stroke="#0f0d0a" strokeWidth="1.5" />,
    d6: <rect x="7" y="7" width="46" height="46" rx="5" fill={color} stroke="#0f0d0a" strokeWidth="1.5" />,
    d8: <polygon points="30,4 56,30 30,56 4,30" fill={color} stroke="#0f0d0a" strokeWidth="1.5" />,
    d10: <polygon points="30,3 55,24 48,54 12,54 5,24" fill={color} stroke="#0f0d0a" strokeWidth="1.5" />,
    d12: <polygon points="30,3 49,10 57,28 49,47 37,56 23,56 11,47 3,28 11,10" fill={color} stroke="#0f0d0a" strokeWidth="1.5" />,
    d20: (
      <>
        <polygon points="30,3 54,18 54,42 30,57 6,42 6,18" fill={color} stroke="#0f0d0a" strokeWidth="1.5" />
        <line x1="30" y1="3" x2="30" y2="57" stroke="#0f0d0a" strokeWidth="0.3" opacity="0.15" />
        <line x1="6" y1="18" x2="54" y2="42" stroke="#0f0d0a" strokeWidth="0.3" opacity="0.15" />
        <line x1="54" y1="18" x2="6" y2="42" stroke="#0f0d0a" strokeWidth="0.3" opacity="0.15" />
      </>
    ),
    d100: (
      <>
        <polygon points="30,3 55,24 48,54 12,54 5,24" fill={color} stroke="#0f0d0a" strokeWidth="1.5" />
        <text x="30" y="46" fontSize="6" fill="#0f0d0a" textAnchor="middle" fontFamily="'IBM Plex Mono', monospace" opacity="0.4">%</text>
      </>
    ),
  };

  return (
    <svg width={size} height={size} viewBox="0 0 60 60" fill="none">
      <defs>
        <linearGradient id={`g-${type}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="rgba(255,255,255,0.12)" />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
      {shapes[type]}
      <text x="30" y={type === "d4" ? 38 : type === "d100" ? 30 : 31} fontSize={fs} {...textStyle}>{value}</text>
    </svg>
  );
};

/* ─── LOGIC ─── */
const rollDie = (sides: number) => Math.floor(Math.random() * sides) + 1;

interface DiceType {
  type: string;
  sides: number;
  color: string;
}

const DICE_TYPES: DiceType[] = [
  { type: "d4", sides: 4, color: "#8a9a6a" },
  { type: "d6", sides: 6, color: "#b8a060" },
  { type: "d8", sides: 8, color: "#9a7a5a" },
  { type: "d10", sides: 10, color: "#7a8a9a" },
  { type: "d12", sides: 12, color: "#9a6a7a" },
  { type: "d20", sides: 20, color: "#b8a060" },
  { type: "d100", sides: 100, color: "#7a7a8a" },
];

interface BoardDieData {
  id: number;
  type: string;
  value: number;
  color: string;
}

/* ─── BOARD DIE ─── */
const BoardDie = ({ die, index, total }: { die: BoardDieData; index: number; total: number }) => {
  const seed1 = ((die.id * 7 + 13) % 100) / 100;
  const seed2 = ((die.id * 11 + 37) % 100) / 100;
  const seed3 = ((die.id * 3 + 71) % 100) / 100;

  const cols = Math.min(Math.ceil(Math.sqrt(total)), 3);
  const row = Math.floor(index / cols);
  const col = index % cols;
  const baseX = 18 + (col / Math.max(cols, 1)) * 64;
  const baseY = 14 + (row / Math.max(Math.ceil(total / cols), 1)) * 64;
  const x = baseX + (seed1 - 0.5) * 14;
  const y = baseY + (seed2 - 0.5) * 10;
  const rot = (seed3 - 0.5) * 25;

  const isCrit = die.type === "d20" && die.value === 20;
  const isFumble = die.type === "d20" && die.value === 1;
  const dieSize = total > 6 ? 30 : total > 3 ? 36 : total > 1 ? 42 : 50;

  return (
    <div style={{
      position: "absolute",
      left: `${x}%`, top: `${y}%`,
      transform: `translate(-50%, -50%) rotate(${rot}deg)`,
      animation: `dieAppear 0.4s ease ${index * 0.05}s both`,
      filter: isCrit ? "drop-shadow(0 0 6px rgba(212,184,112,0.6))" : isFumble ? "drop-shadow(0 0 6px rgba(204,68,68,0.5))" : "drop-shadow(1px 2px 3px rgba(0,0,0,0.5))",
      zIndex: 10 + index,
    }}>
      <DiceShape
        type={die.type}
        value={die.value}
        size={dieSize}
        color={isCrit ? "#d4b870" : isFumble ? "#c44" : die.color}
      />
    </div>
  );
};

interface RollHistory {
  notation: string;
  dice: BoardDieData[];
  total: number;
  modifier: number;
  ts: number;
}

/* ─── MAIN COMPONENT ─── */
export interface DiceBoardPanelHandle {
  roll: (typeStr: string, count: number, mod: number) => void;
}

interface DiceBoardPanelProps {
  onRollResult?: (notation: string, total: number, rolls: number[], mod: number) => void;
}

const DiceBoardPanel = forwardRef(function DiceBoardPanel(
  { onRollResult }: DiceBoardPanelProps,
  ref: React.ForwardedRef<DiceBoardPanelHandle>
) {
  const [selectedType, setSelectedType] = useState(DICE_TYPES[5]);
  const [count, setCount] = useState(1);
  const [modifier, setModifier] = useState(0);
  const [boardDice, setBoardDice] = useState<BoardDieData[]>([]);
  const [rolling, setRolling] = useState(false);
  const [total, setTotal] = useState<number | null>(null);
  const [history, setHistory] = useState<RollHistory[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [customInput, setCustomInput] = useState("");
  const dieIdRef = useRef(0);

  const doRoll = useCallback((type: DiceType, cnt: number, mod: number) => {
    setRolling(true);
    setBoardDice([]);
    setTotal(null);

    let frame = 0;
    const interval = setInterval(() => {
      setBoardDice(Array.from({ length: cnt }, (_, i) => ({
        id: dieIdRef.current + i, type: type.type,
        value: rollDie(type.sides), color: type.color,
      })));
      frame++;
      if (frame >= 5) {
        clearInterval(interval);
        const finalDice = Array.from({ length: cnt }, (_, i) => ({
          id: dieIdRef.current + i, type: type.type,
          value: rollDie(type.sides), color: type.color,
        }));
        dieIdRef.current += cnt;
        const sum = finalDice.reduce((a, d) => a + d.value, 0) + mod;
        setBoardDice(finalDice);
        setTotal(sum);
        setRolling(false);
        const notation = `${cnt > 1 ? cnt : ""}${type.type}${mod > 0 ? `+${mod}` : mod < 0 ? mod : ""}`;
        setHistory(prev => [{ notation, dice: finalDice, total: sum, modifier: mod, ts: Date.now() }, ...prev].slice(0, 15));
        onRollResult?.(notation, sum, finalDice.map(d => d.value), mod);
      }
    }, 55);
  }, [onRollResult]);

  useImperativeHandle(ref, () => ({
    roll: (typeStr: string, cnt: number, mod: number) => {
      const dt = DICE_TYPES.find(d => d.type === typeStr) || DICE_TYPES[5];
      setSelectedType(dt);
      setCount(cnt);
      setModifier(mod);
      doRoll(dt, cnt, mod);
    },
  }), [doRoll]);

  const handleRoll = () => doRoll(selectedType, count, modifier);

  const handleCustomRoll = () => {
    const m = customInput.trim().match(/^(\d+)?d(\d+)([+-]\d+)?$/i);
    if (!m) return;
    const cnt = parseInt(m[1] || "1");
    const sides = parseInt(m[2]);
    const mod = parseInt(m[3] || "0");
    const dt = DICE_TYPES.find(d => d.sides === sides) || { type: `d${sides}`, sides, color: "#b8a060" };
    doRoll(dt, Math.min(cnt, 12), mod);
    setCustomInput("");
  };

  const notation = `${count > 1 ? count : ""}${selectedType.type}${modifier > 0 ? `+${modifier}` : modifier < 0 ? modifier : ""}`;

  return (
    <>
      <style>{`
        @keyframes dieAppear {
          0% { opacity: 0; transform: translate(-50%,-50%) scale(0.3) rotate(0deg); }
          50% { opacity: 1; transform: translate(-50%,-50%) scale(1.1) rotate(var(--r,10deg)); }
          100% { opacity: 1; transform: translate(-50%,-50%) scale(1) rotate(var(--r,10deg)); }
        }
        @keyframes totalPop {
          0% { transform: translateX(-50%) scale(0.5); opacity: 0; }
          60% { transform: translateX(-50%) scale(1.1); }
          100% { transform: translateX(-50%) scale(1); opacity: 1; }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        .dt-btn {
          display: flex; flex-direction: column; align-items: center; gap: 1px;
          padding: 4px 2px; border-radius: 4px; cursor: pointer;
          background: transparent; border: 1.5px solid transparent;
          transition: all 0.15s; flex: 1; min-width: 0;
        }
        .dt-btn:hover { background: rgba(180,160,80,0.04); border-color: rgba(180,160,80,0.08); }
        .dt-btn.active { background: rgba(180,160,80,0.08); border-color: rgba(180,160,80,0.2); }

        .qk-btn {
          padding: 3px 8px; border-radius: 10px; cursor: pointer;
          background: transparent; border: 1px solid rgba(180,160,100,0.1);
          font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: #8a8270;
          transition: all 0.15s;
        }
        .qk-btn:hover { border-color: rgba(180,160,80,0.4); color: #b8a060; }
      `}</style>

      <div style={{
        background: "#141210",
        borderRadius: 8,
        border: "1px solid rgba(180,160,100,0.1)",
        overflow: "hidden",
        display: "flex", flexDirection: "column",
      }}>
        {/* ── Header ── */}
        <div style={{
          padding: "10px 14px",
          borderBottom: "1px solid rgba(180,160,100,0.1)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{
            fontFamily: "'Cinzel', serif", fontSize: 9, letterSpacing: "0.15em", color: "#6a6250",
          }}>DICE TRAY</span>
          {history.length > 0 && (
            <button
              onClick={() => setShowHistory(!showHistory)}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontFamily: "'IBM Plex Mono', monospace", fontSize: 9, color: "#6a6250",
              }}
            >{showHistory ? "Hide" : "History"} ({history.length})</button>
          )}
        </div>

        {/* ── Die Type Selector ── */}
        <div style={{
          padding: "8px 10px 4px",
          display: "flex", gap: 2,
        }}>
          {DICE_TYPES.map(dt => (
            <button
              key={dt.type}
              className={`dt-btn ${selectedType.type === dt.type ? "active" : ""}`}
              onClick={() => setSelectedType(dt)}
            >
              <DiceShape
                type={dt.type}
                value={dt.type.replace("d", "")}
                size={22}
                color={selectedType.type === dt.type ? dt.color : "rgba(180,160,100,0.2)"}
              />
              <span style={{
                fontFamily: "'IBM Plex Mono', monospace", fontSize: 8,
                color: selectedType.type === dt.type ? "#b8a060" : "#6a6250",
              }}>{dt.type}</span>
            </button>
          ))}
        </div>

        {/* ── Rolling Tray ── */}
        <div style={{
          margin: "8px 10px",
          height: 170,
          borderRadius: 8,
          position: "relative",
          overflow: "hidden",
          background: `
            radial-gradient(ellipse at 30% 40%, rgba(40,55,35,0.5) 0%, transparent 60%),
            radial-gradient(ellipse at 70% 65%, rgba(30,45,30,0.3) 0%, transparent 50%),
            linear-gradient(145deg, #1a2418, #151e14, #1a2418)
          `,
          border: "2px solid #2a2218",
          boxShadow: "inset 0 2px 8px rgba(0,0,0,0.5), inset 0 0 20px rgba(0,0,0,0.2)",
        }}>
          {/* Corner marks */}
          {[
            { top: 6, left: 6, bt: true, bl: true },
            { top: 6, right: 6, bt: true, br: true },
            { bottom: 6, left: 6, bb: true, bl: true },
            { bottom: 6, right: 6, bb: true, br: true },
          ].map((c, i) => (
            <div key={i} style={{
              position: "absolute", width: 10, height: 10,
              top: c.top, right: c.right, bottom: c.bottom, left: c.left,
              borderTop: c.bt ? "1px solid rgba(180,160,100,0.06)" : "none",
              borderBottom: c.bb ? "1px solid rgba(180,160,100,0.06)" : "none",
              borderLeft: c.bl ? "1px solid rgba(180,160,100,0.06)" : "none",
              borderRight: c.br ? "1px solid rgba(180,160,100,0.06)" : "none",
            } as React.CSSProperties} />
          ))}

          {/* Dice */}
          {boardDice.map((die, i) => (
            <BoardDie key={die.id} die={die} index={i} total={boardDice.length} />
          ))}

          {/* Empty state */}
          {boardDice.length === 0 && (
            <div style={{
              position: "absolute", inset: 0,
              display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center",
            }}>
              <DiceShape type="d20" value="?" size={44} color="rgba(180,160,100,0.07)" />
              <span style={{
                fontFamily: "'Crimson Text', serif", fontSize: 11, fontStyle: "italic",
                marginTop: 4, color: "rgba(180,160,100,0.12)",
              }}>Roll the bones</span>
            </div>
          )}

          {/* Total */}
          {total !== null && !rolling && (
            <div style={{
              position: "absolute", bottom: 6, left: "50%",
              transform: "translateX(-50%)",
              display: "flex", alignItems: "center", gap: 6,
              padding: "4px 14px", borderRadius: 14,
              background: "rgba(10,9,8,0.85)", backdropFilter: "blur(6px)",
              border: "1px solid rgba(180,160,80,0.2)",
              animation: "totalPop 0.3s ease",
              boxShadow: "0 2px 10px rgba(0,0,0,0.4)",
            }}>
              <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#6a6250" }}>
                {notation}
              </span>
              <span style={{
                fontFamily: "'IBM Plex Mono', monospace", fontSize: 20, fontWeight: 700, color: "#d4b870",
              }}>{total}</span>
            </div>
          )}
        </div>

        {/* ── Controls ── */}
        <div style={{ padding: "4px 10px 8px", display: "flex", alignItems: "center", gap: 6 }}>
          {/* Count stepper */}
          <div style={{
            display: "flex", alignItems: "center",
            background: "#0a0908", borderRadius: 4,
            border: "1px solid rgba(180,160,100,0.1)", overflow: "hidden",
          }}>
            <button
              onClick={() => setCount(Math.max(1, count - 1))}
              style={{
                width: 24, height: 28, cursor: "pointer",
                background: "transparent", border: "none",
                color: count > 1 ? "#8a8270" : "rgba(180,160,100,0.15)",
                fontFamily: "'IBM Plex Mono', monospace", fontSize: 14,
                borderRight: "1px solid rgba(180,160,100,0.1)",
              }}
            >−</button>
            <span style={{
              width: 24, textAlign: "center",
              fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, fontWeight: 600, color: "#c8c0aa",
            }}>{count}</span>
            <button
              onClick={() => setCount(Math.min(12, count + 1))}
              style={{
                width: 24, height: 28, cursor: "pointer",
                background: "transparent", border: "none",
                color: count < 12 ? "#8a8270" : "rgba(180,160,100,0.15)",
                fontFamily: "'IBM Plex Mono', monospace", fontSize: 14,
                borderLeft: "1px solid rgba(180,160,100,0.1)",
              }}
            >+</button>
          </div>

          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "#b8a060", fontWeight: 600 }}>
            {selectedType.type}
          </span>

          {/* Modifier stepper */}
          <div style={{
            display: "flex", alignItems: "center",
            background: "#0a0908", borderRadius: 4,
            border: "1px solid rgba(180,160,100,0.1)", overflow: "hidden",
          }}>
            <button
              onClick={() => setModifier(modifier - 1)}
              style={{
                width: 22, height: 28, cursor: "pointer",
                background: "transparent", border: "none",
                color: "#8a8270", fontFamily: "'IBM Plex Mono', monospace", fontSize: 14,
                borderRight: "1px solid rgba(180,160,100,0.1)",
              }}
            >−</button>
            <span style={{
              minWidth: 28, textAlign: "center",
              fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, fontWeight: 500,
              color: modifier === 0 ? "#6a6250" : modifier > 0 ? "#5a8a5a" : "#c44",
            }}>
              {modifier > 0 ? `+${modifier}` : modifier}
            </span>
            <button
              onClick={() => setModifier(modifier + 1)}
              style={{
                width: 22, height: 28, cursor: "pointer",
                background: "transparent", border: "none",
                color: "#8a8270", fontFamily: "'IBM Plex Mono', monospace", fontSize: 14,
                borderLeft: "1px solid rgba(180,160,100,0.1)",
              }}
            >+</button>
          </div>

          <div style={{ flex: 1 }} />

          {/* ROLL button */}
          <button
            onClick={handleRoll}
            disabled={rolling}
            style={{
              padding: "6px 18px", borderRadius: 4, cursor: rolling ? "default" : "pointer",
              background: rolling ? "rgba(255,245,220,0.03)" : "linear-gradient(135deg, #6a5020, #8a7030)",
              border: `1px solid ${rolling ? "rgba(180,160,100,0.1)" : "#b8a060"}`,
              fontFamily: "'Cinzel', serif", fontSize: 10, fontWeight: 600,
              letterSpacing: "0.1em", color: rolling ? "#6a6250" : "#f0e8d0",
              transition: "all 0.2s",
              boxShadow: rolling ? "none" : "0 1px 8px rgba(180,160,80,0.12)",
            }}
            onMouseEnter={e => { if (!rolling) e.currentTarget.style.background = "linear-gradient(135deg, #8a7030, #b8a060)"; }}
            onMouseLeave={e => { if (!rolling) e.currentTarget.style.background = "linear-gradient(135deg, #6a5020, #8a7030)"; }}
          >{rolling ? "..." : "ROLL"}</button>
        </div>

        {/* ── Custom input + Quick rolls ── */}
        <div style={{ padding: "0 10px 10px" }}>
          {/* Custom notation */}
          <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
            <input
              value={customInput}
              onChange={e => setCustomInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleCustomRoll(); }}
              placeholder="2d6+3"
              style={{
                flex: 1, padding: "5px 8px", borderRadius: 4,
                background: "#0a0908", border: "1px solid rgba(180,160,100,0.1)",
                fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "#c8c0aa",
                textAlign: "center",
              }}
              onFocus={e => e.currentTarget.style.borderColor = "rgba(180,160,80,0.4)"}
              onBlur={e => e.currentTarget.style.borderColor = "rgba(180,160,100,0.1)"}
            />
            <button
              onClick={handleCustomRoll}
              style={{
                padding: "5px 10px", borderRadius: 4, cursor: "pointer",
                background: "rgba(255,245,220,0.03)", border: "1px solid rgba(180,160,100,0.1)",
                fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#8a8270",
                transition: "all 0.15s",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = "rgba(180,160,80,0.4)"; e.currentTarget.style.color = "#b8a060"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "rgba(180,160,100,0.1)"; e.currentTarget.style.color = "#8a8270"; }}
            >GO</button>
          </div>

          {/* Quick presets */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {["1d20", "2d6", "1d8+2", "1d100", "3d6", "4d6"].map(n => (
              <button key={n} className="qk-btn" onClick={() => {
                const m = n.match(/^(\d+)?d(\d+)([+-]\d+)?$/i);
                if (!m) return;
                const cnt = parseInt(m[1] || "1");
                const sides = parseInt(m[2]);
                const mod = parseInt(m[3] || "0");
                const dt = DICE_TYPES.find(d => d.sides === sides) || { type: `d${sides}`, sides, color: "#b8a060" };
                doRoll(dt, cnt, mod);
              }}>{n}</button>
            ))}
          </div>
        </div>

        {/* ── History ── */}
        {showHistory && history.length > 0 && (
          <div style={{
            borderTop: "1px solid rgba(180,160,100,0.1)",
            padding: "8px 12px 10px",
            maxHeight: 160, overflowY: "auto",
            animation: "fadeIn 0.2s ease",
          }}>
            {history.map((roll, i) => {
              const isCrit = roll.dice.length === 1 && roll.dice[0].type === "d20" && roll.dice[0].value === 20;
              const isFumble = roll.dice.length === 1 && roll.dice[0].type === "d20" && roll.dice[0].value === 1;
              return (
                <div key={roll.ts} style={{
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                  padding: "4px 0",
                  borderBottom: i < history.length - 1 ? "1px solid rgba(180,160,100,0.03)" : "none",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, color: "#6a6250", minWidth: 38 }}>
                      {roll.notation}
                    </span>
                    {roll.dice.length > 1 && (
                      <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 9, color: "rgba(180,160,100,0.2)" }}>
                        [{roll.dice.map(d => d.value).join(",")}]
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    {isCrit && <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 8, color: "#d4b870", letterSpacing: "0.05em" }}>NAT20</span>}
                    {isFumble && <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 8, color: "#c44", letterSpacing: "0.05em" }}>FUMBLE</span>}
                    <span style={{
                      fontFamily: "'IBM Plex Mono', monospace", fontSize: 13, fontWeight: 600,
                      color: isCrit ? "#d4b870" : isFumble ? "#c44" : "#c8c0aa",
                    }}>{roll.total}</span>
                  </div>
                </div>
              );
            })}
            <button
              onClick={() => { setHistory([]); setBoardDice([]); setTotal(null); }}
              style={{
                display: "block", width: "100%", marginTop: 6, padding: "4px 0",
                background: "none", border: "none", cursor: "pointer",
                fontFamily: "'Crimson Text', serif", fontSize: 11, color: "#6a6250",
                textAlign: "center",
              }}
              onMouseEnter={e => e.currentTarget.style.color = "#8a8270"}
              onMouseLeave={e => e.currentTarget.style.color = "#6a6250"}
            >Clear all</button>
          </div>
        )}
      </div>
    </>
  );
});

export default DiceBoardPanel;
