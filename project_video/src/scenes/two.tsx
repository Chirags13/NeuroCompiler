import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { C, Chip, Logo, MONO, Panel, Rise, SANS, SceneFrame, Stopwatch, Title, count, cue, lin, prog } from "../lib";
import data from "../data.json";

/* ---------- 5. Tune: the funnel ---------- */
const N = 937, RLN = 24;
const rnd = (i: number, k: number) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
const DOT = Array.from({ length: N }, (_, i) => ({ rl: i < RLN, rank: rnd(i, 1) }));
const ranks = DOT.map((d, i) => ({ i, r: d.rl ? d.rank * 0.5 : d.rank })).sort((a, b) => a.r - b.r);
const rankOf: number[] = []; ranks.forEach((x, j) => (rankOf[x.i] = j));

export const Tune: React.FC = () => {
  const f = useCurrentFrame();
  const c0 = cue("tune", 0), c1 = cue("tune", 1), c2 = cue("tune", 2), c3 = cue("tune", 3), c4 = cue("tune", 4), c5 = cue("tune", 5);
  const rankP = prog(f, c1 + 6, 40);
  const pick = prog(f, c2 - 2, 20);
  const cols = 46, gx = 16, x0 = 114, y0 = 322;
  const stages = ["compile", "verify output", "time vs -O3"];
  const finalShow = prog(f, c5 - 4, 14);
  return (
    <SceneFrame>
      <Title kicker="Tune mode · for a new program">Propose · rank · measure · confirm</Title>
      <svg style={{ position: "absolute", left: 0, top: 0, opacity: 1 - finalShow * 0.9 }} width="1920" height="1080">
        {DOT.map((d, i) => {
          const start = d.rl ? c0 + 6 + i * 1.2 : c1 + (i % 40) * 0.4;
          const a = prog(f, start, 10);
          const r0 = i, r1 = rankOf[i];
          const r = r0 + (r1 - r0) * rankP;
          const hx = x0 + (r % cols) * gx, hy = y0 + Math.floor(r / cols) * gx;
          const top = r1 < 8;
          const tx = 1000, ty = 332 + r1 * 52;
          const x = top ? hx + (tx - hx) * pick : hx, y = top ? hy + (ty - hy) * pick : hy;
          const fade = top ? 1 : 1 - pick * 0.8;
          return <circle key={i} cx={x} cy={y} r={d.rl ? 7.5 : 5} fill={d.rl ? C.rl : C.lib} opacity={a * fade} />;
        })}
        {[0, 1, 2, 3, 4, 5, 6, 7].map((k) => {
          const w = lin(f, c2 + 16 + k * 2, 42);
          return <g key={k} opacity={pick}><rect x="1020" y={316 + k * 52} width="450" height="32" rx="7" fill={C.panel2} stroke={C.line} /><rect x="1020" y={316 + k * 52} width={450 * w} height="32" rx="7" fill={k === 2 ? C.ok : C.acc} opacity={k === 2 ? 0.95 : 0.45 + 0.05 * k} /></g>;
        })}
      </svg>
      <div style={{ opacity: 1 - finalShow * 0.9 }}>
        <Rise at={c0 + 4} style={{ position: "absolute", left: 110, top: 232, display: "flex", gap: 26, fontFamily: MONO, fontSize: 26 }}>
          <span style={{ color: C.rl }}>● 24 PPO proposals</span>
          <span style={{ color: C.lib, opacity: prog(f, c1, 10) }}>● ≈913 library pipelines</span>
        </Rise>
        <Rise at={c1 + 14} until={c2 - 4} style={{ position: "absolute", left: 110, top: 700, fontFamily: MONO, fontSize: 32, color: C.acc2 }}>LightGBM sorts them, best predicted first</Rise>
        <Rise at={c2} style={{ position: "absolute", left: 1020, top: 240, display: "flex", gap: 10 }}>
          {stages.map((s, i) => <span key={s} style={{ opacity: prog(f, c2 + i * 12, 10) }}><Chip color={C.ok} style={{ fontSize: 20, padding: "6px 12px" }}>{s}</Chip></span>)}
        </Rise>
        <Panel style={{ left: 1510, top: 316, width: 310, height: 400, padding: 26, opacity: prog(f, c3 - 2, 12), fontFamily: SANS }}>
          <div style={{ display: "flex", justifyContent: "center" }}><Stopwatch size={92} speed={14} /></div>
          <div style={{ fontWeight: 700, fontSize: 30, color: C.text, textAlign: "center", marginTop: 12 }}>Confirm</div>
          <div style={{ fontFamily: MONO, fontSize: 22, color: C.mute, textAlign: "center", marginTop: 8, lineHeight: 1.45 }}>fresh {count(f, c3, 24, 20)} rounds<br />+ A/A control<br />CI low &gt; 1.01</div>
          <div style={{ marginTop: 18, textAlign: "center", opacity: prog(f, c4, 10) }}><Chip color={C.ok} style={{ fontSize: 20, padding: "6px 10px" }}>pick</Chip><span style={{ color: C.mute, fontFamily: MONO, fontSize: 20 }}> or </span><Chip color={C.o3} style={{ fontSize: 20, padding: "6px 10px" }}>-O3</Chip></div>
        </Panel>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, top: 350, textAlign: "center", fontFamily: SANS, fontWeight: 700, color: C.text, opacity: finalShow, transform: `scale(${0.96 + finalShow * 0.04})` }}>
        <div style={{ fontSize: 76 }}>The models <span style={{ color: C.lib }}>shortlist</span>.</div>
        <div style={{ fontSize: 76, marginTop: 8, opacity: prog(f, c5 + 28, 12) }}>The stopwatch <span style={{ color: C.ok }}>decides</span>.</div>
      </div>
    </SceneFrame>
  );
};

/* ---------- 6. Results ---------- */
const pc = (v: number) => `${v >= 1 ? "+" : "−"}${Math.abs((v - 1) * 100).toFixed(2)}%`;
export const Results: React.FC = () => {
  const f = useCurrentFrame();
  const c1 = cue("results", 1), c2 = cue("results", 2), c3 = cue("results", 3), c4 = cue("results", 4);
  const h = data.headline;
  const off = prog(f, c4 - 6, 14);
  const X = 340, W = 760, lo = 0.93, hi = 1.18;
  const sx = (v: number) => X + ((v - lo) / (hi - lo)) * W;
  const race = lin(f, c4 + 6, 96);
  const o3 = data.demo.o3 as number, pick = data.demo.pick as number;
  return (
    <SceneFrame>
      <div style={{ opacity: 1 - off }}>
        <Title kicker="Frozen test set · measured">33 unseen programs, 11 families</Title>
        <div style={{ position: "absolute", left: 110, top: 235, width: 1140, height: 560 }}>
          <svg width="1240" height="560" style={{ position: "absolute", left: 0, top: 0 }}>
            <line x1={sx(1)} x2={sx(1)} y1="0" y2="540" stroke={C.o3} strokeWidth="2" strokeDasharray="6 6" />
            <text x={sx(1)} y="556" fill={C.mute} fontSize="20" textAnchor="middle" fontFamily={MONO}>-O3</text>
            {data.bars.map((b, i) => {
              const y = 10 + i * 66, p = prog(f, 8 + i * 5, 24);
              const main = i === 0;
              const col = main ? C.rl : i === 1 ? C.lib : b.v >= 1 ? C.acc : C.bad;
              const x1 = sx(1), x2 = sx(1 + (b.v - 1) * p);
              return (
                <g key={b.name}>
                  <text x="0" y={y + 32} fill={main ? C.text : C.mute} fontSize="26" fontWeight={main ? 700 : 500} fontFamily={SANS}>{b.name}</text>
                  <rect x={Math.min(x1, x2)} y={y + 6} width={Math.abs(x2 - x1)} height="38" rx="5" fill={col} opacity={main ? 1 : 0.65} />
                  <line x1={sx(b.lo)} x2={sx(b.hi)} y1={y + 25} y2={y + 25} stroke={C.text} strokeWidth="2.5" opacity={p * 0.75} />
                  <text x={sx(Math.max(b.hi, 1)) + 14} y={y + 34} fill={C.text} fontSize="26" fontWeight="600" fontFamily={MONO} opacity={p}>{pc(b.v)}</text>
                </g>
              );
            })}
          </svg>
        </div>
        <div style={{ position: "absolute", left: 1400, top: 240, width: 440, fontFamily: SANS, color: C.text }}>
          <Rise at={c1}><div style={{ fontSize: 100, fontWeight: 700, color: C.rl, lineHeight: 1 }}>{pc(h.geomean)}</div><div style={{ fontSize: 25, color: C.mute }}>geomean vs -O3</div><div style={{ fontSize: 23, color: C.mute, fontFamily: MONO, whiteSpace: "nowrap" }}>95% CI {pc(h.ci[0])}…{pc(h.ci[1])}</div></Rise>
          <Rise at={c2} style={{ marginTop: 30 }}><div style={{ fontSize: 66, fontWeight: 700, lineHeight: 1 }}>{pc(h.excl_largest)}</div><div style={{ fontSize: 25, color: C.mute }}>excluding the largest win</div></Rise>
          <Rise at={c3} style={{ marginTop: 30 }}><div style={{ fontSize: 66, fontWeight: 700, color: C.ok, lineHeight: 1 }}>{h.slower} of {h.n}</div><div style={{ fontSize: 25, color: C.mute }}>measurably slower · {h.ge5} are ≥ 5% faster</div></Rise>
        </div>
      </div>
      <div style={{ opacity: off }}>
        <Title kicker="Demo run · interpreter loop" at={c4 - 4}>Same code, new pipeline</Title>
        {[["-O3", o3, C.o3], ["RL pick", pick, C.ok]].map(([n, ms, col], i) => {
          const m = ms as number; const t = Math.min(1, race * (o3 / m > 1 && i ? o3 / m : 1));
          return (
            <div key={i} style={{ position: "absolute", left: 110, top: 300 + i * 170, width: 1700 }}>
              <div style={{ fontFamily: MONO, fontSize: 30, color: C.text, marginBottom: 10 }}>{n as string}</div>
              <div style={{ height: 84, background: C.panel, borderRadius: 12, border: `1.5px solid ${C.line}`, width: 1500 * (m / o3) + 2 }}>
                <div style={{ height: "100%", width: `${t * 100}%`, background: col as string, borderRadius: 11 }} />
              </div>
              <div style={{ position: "absolute", left: 1500 * (m / o3) + 22, top: 56, fontFamily: MONO, fontSize: 38, fontWeight: 500, color: C.text }}>{(m * t).toFixed(0)} ms</div>
            </div>
          );
        })}
        <Rise at={c4 + 70} style={{ position: "absolute", left: 110, top: 660, fontFamily: SANS, display: "flex", alignItems: "baseline", gap: 24 }}>
          <span style={{ fontSize: 96, fontWeight: 700, color: C.ok }}>{data.demo.speedup.toFixed(2)}×</span>
          <span style={{ fontSize: 30, color: C.mute }}>demo on a validation program, not part of the 33-program test set</span>
        </Rise>
      </div>
    </SceneFrame>
  );
};

/* ---------- 7. Stack and the honest lesson ---------- */
const STACK = ["LLVM 18.1.8", "clang · opt · llc", "LightGBM", "PPO in NumPy", "SQLite", "FastAPI", "valgrind cachegrind"];
export const Stack: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames: d } = useVideoConfig();
  const c1 = cue("stack", 1), c2 = cue("stack", 2), c3 = cue("stack", 3);
  const off = prog(f, c2 - 6, 14);
  const z = interpolate(f, [0, c2], [1.1, 1.28]);
  return (
    <SceneFrame>
      <div style={{ opacity: 1 - off }}>
        <Title kicker="Implementation">Real tools, real interface</Title>
        <div style={{ position: "absolute", left: 110, top: 225, display: "flex", gap: 14, flexWrap: "wrap", width: 1700 }}>
          {STACK.map((s, i) => <span key={s} style={{ opacity: prog(f, 6 + i * 6, 12) }}><Chip color={[C.acc, C.lib, C.acc2, C.rl][i % 4]} mono={false}>{s}</Chip></span>)}
        </div>
        <div style={{ position: "absolute", left: 110, top: 300, width: 1700, height: 560, borderRadius: 18, overflow: "hidden", border: `1.5px solid ${C.line}`, opacity: prog(f, c1 - 10, 16) }}>
          <Img src={staticFile("shots/tune_diff.jpg")} style={{ width: "100%", transform: `scale(${z}) translateY(${-f * 0.5}px)`, transformOrigin: "30% 25%" }} />
        </div>
        <Rise at={c1 + 10} style={{ position: "absolute", left: 140, top: 790 }}><Chip color={C.ok} mono={false} style={{ background: `${C.bg}ee` }}>selected sequence vs -O3, pass by pass</Chip></Rise>
      </div>
      <div style={{ opacity: off }}>
        <Title kicker="The honest lesson" at={c2}>What actually made it work</Title>
        {[["LightGBM alone", "Spearman ≈ 0.11", "weak on unseen families", C.lib, 0], ["RL on top", "+0.2%, not significant", "shipped on 1 of 33 programs", C.rl, 40], ["Measure + confirm", "+8.09%, 0 slower", "reliable, with -O3 as fallback", C.ok, 0]].map(([a, b, cc, col, dl], i) => (
          <Rise key={i} at={i === 2 ? c3 : c2 + 12 + i * 34} style={{ position: "absolute", left: 110 + i * 580, top: 280, width: 540 }}>
            <div style={{ background: C.panel, border: `2px solid ${col}`, borderRadius: 20, padding: "38px 30px", fontFamily: SANS, height: 400 }}>
              <div style={{ fontSize: 36, color: col as string, fontWeight: 700 }}>{a}</div>
              <div style={{ fontSize: 50, color: C.text, fontWeight: 700, marginTop: 40, lineHeight: 1.15 }}>{b}</div>
              <div style={{ fontSize: 30, color: C.mute, marginTop: 24 }}>{cc}</div>
            </div>
          </Rise>
        ))}
      </div>
    </SceneFrame>
  );
};

/* ---------- 8. Close ---------- */
export const Close: React.FC = () => {
  const f = useCurrentFrame();
  const h = data.headline;
  return (
    <SceneFrame>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingBottom: 70 }}>
        <div style={{ transform: `scale(${0.85 + prog(f, 0, 24) * 0.15})` }}><Logo size={140} /></div>
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 120, color: C.text, marginTop: 26, letterSpacing: -3, opacity: prog(f, 4, 16) }}>NeuroCompiler</div>
        <div style={{ fontFamily: SANS, fontWeight: 500, fontSize: 46, color: C.acc2, marginTop: 8, opacity: prog(f, 26, 16) }}>Faster code. Measured, not guessed.</div>
        <div style={{ display: "flex", gap: 18, marginTop: 40, opacity: prog(f, 46, 16) }}>
          <Chip color={C.rl}>+8.09% vs -O3</Chip><Chip color={C.lib}>{h.n} unseen programs</Chip><Chip color={C.ok}>{h.slower} measurably slower</Chip>
        </div>
        <div style={{ fontFamily: SANS, fontSize: 25, color: C.mute, marginTop: 42, opacity: prog(f, 62, 16) }}>Chirag S · Dhanush Singh · Gagan S Shamnur · Nithin Choudhary A · JSSATE, CSE</div>
      </div>
    </SceneFrame>
  );
};
