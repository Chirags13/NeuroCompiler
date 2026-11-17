import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { C, Chip, Logo, MONO, Panel, Rise, SANS, SceneFrame, Stopwatch, Title, count, cue, lin, prog } from "../lib";
import data from "../data.json";

/* ---------- 1. Hook: one fixed pipeline for every program ---------- */
const belt = data.passes.slice(0, 60);
export const Hook: React.FC = () => {
  const f = useCurrentFrame();
  const c1 = cue("hook", 1), c3 = cue("hook", 3), c4 = cue("hook", 4);
  const cmd = "clang -O3 program.c";
  const typed = cmd.slice(0, Math.floor(lin(f, 4, 24) * cmd.length));
  const beltOn = prog(f, c1 - 4, 20);
  const beltOff = prog(f, c3 - 6, 16);
  const shift = f * 7;
  const progs = ["matmul.c", "interpreter.c", "fibonacci.c"];
  return (
    <SceneFrame>
      <div style={{ opacity: 1 - beltOff }}>
        <Panel style={{ left: interpolate(prog(f, c1 - 6, 16), [0, 1], [430, 110]), top: interpolate(prog(f, c1 - 6, 16), [0, 1], [440, 130]), width: interpolate(prog(f, c1 - 6, 16), [0, 1], [1060, 760]), padding: "26px 34px", fontFamily: MONO, fontSize: interpolate(prog(f, c1 - 6, 16), [0, 1], [56, 36]), color: C.text }}>
          <span style={{ color: C.ok }}>$ </span>{typed}<span style={{ opacity: f % 20 < 10 ? 1 : 0, color: C.acc2 }}>▌</span>
        </Panel>
        <div style={{ position: "absolute", right: 110, top: 118, textAlign: "right", opacity: beltOn }}>
          <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 96, color: C.text, lineHeight: 1 }}>{count(f, c1, 30, 109)}</div>
          <div style={{ fontFamily: MONO, fontSize: 24, color: C.mute }}>passes in LLVM 18 -O3</div>
        </div>
        {/* conveyor of real pass names */}
        <div style={{ position: "absolute", left: 0, right: 0, top: 480, height: 150, opacity: beltOn, overflow: "hidden", background: `${C.panel}cc`, borderTop: `1.5px solid ${C.line}`, borderBottom: `1.5px solid ${C.line}` }}>
          <div style={{ display: "flex", gap: 14, alignItems: "center", height: "100%", transform: `translateX(${-(shift % 2600)}px)` }}>
            {[...belt, ...belt].map((p, i) => <Chip key={i} color={i % 5 === 0 ? C.acc : C.lib}>{p}</Chip>)}
          </div>
        </div>
        {progs.map((p, i) => {
          const start = c1 + 6 + i * 16;
          const y = interpolate(f, [start, start + 16], [300, 410], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const x = 240 + i * 520 + Math.max(0, f - start - 16) * 2;
          return <div key={p} style={{ position: "absolute", left: x, top: y, opacity: prog(f, start, 10) * (1 - prog(f, c3 - 16, 10)) }}><Chip color={C.warn} style={{ fontSize: 26, background: C.panel2 }}>{p}</Chip></div>;
        })}
        <Rise at={cue("hook", 2)} until={c3 - 6} style={{ position: "absolute", left: 0, right: 0, top: 690, textAlign: "center", fontFamily: SANS, fontWeight: 600, fontSize: 44, color: C.text }}>
          same passes · same order · every program
        </Rise>
      </div>
      {/* title reveal */}
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", paddingBottom: 130, opacity: prog(f, c3 - 2, 16), transform: `scale(${0.92 + prog(f, c3 - 2, 26) * 0.08})` }}>
        <Logo size={150} />
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 124, color: C.text, marginTop: 30, letterSpacing: -3 }}>NeuroCompiler</div>
        <div style={{ fontFamily: SANS, fontSize: 36, color: C.mute, marginTop: 8 }}>ML + RL guided LLVM pass selection</div>
        <div style={{ marginTop: 26, opacity: prog(f, c4, 12), display: "flex", alignItems: "center", gap: 18 }}>
          <Stopwatch size={72} /><span style={{ fontFamily: MONO, fontSize: 28, color: C.acc2 }}>judged only by measured runtime</span>
        </div>
      </div>
    </SceneFrame>
  );
};

/* ---------- 2. Problem: compromise, and IR count is not runtime ---------- */
const DOTS = (() => { // 31 programs of the knowledge base; colours are the real counts, positions arbitrary
  const a = Array.from({ length: data.kb.programs }, (_, i) => "n");
  const idx = [2, 7, 12, 20, 25, 29, 4, 15, 9, 23];
  idx.slice(0, data.kb.faster).forEach((i) => (a[i] = "f"));
  idx.slice(data.kb.faster, data.kb.faster + data.kb.slower).forEach((i) => (a[i] = "s"));
  return a;
})();
export const Problem: React.FC = () => {
  const f = useCurrentFrame();
  const c1 = cue("problem", 1), c2 = cue("problem", 2), c3 = cue("problem", 3), c4 = cue("problem", 4);
  const W = 1000, H = 560, x0 = 90, y0 = 20;
  const sx = (v: number) => x0 + ((Math.log(v) + 0.7) / 1.4) * (W - x0 - 20);
  const sy = (v: number) => y0 + (1 - (Math.log(v) + 0.7) / 1.4) * (H - y0 - 60);
  const shown = Math.floor(lin(f, c3, 70) * data.ir.pts.length);
  return (
    <SceneFrame>
      <div style={{ opacity: 1 - prog(f, c2 - 4, 12) }}>
        <Title kicker="The problem">A fixed recipe is a compromise</Title>
        <Rise at={12} style={{ position: "absolute", left: 110, top: 240 }}><Chip color={C.acc} style={{ fontSize: 34 }}>{data.kb.label}</Chip>
          <span style={{ fontFamily: SANS, fontSize: 30, color: C.mute, marginLeft: 22 }}>one edit, tried on {data.kb.programs} programs</span></Rise>
        <div style={{ position: "absolute", left: 110, top: 350, width: 1240, display: "grid", gridTemplateColumns: "repeat(11, 96px)", gap: 16 }}>
          {DOTS.map((d, i) => {
            const p = prog(f, c1 + i * 1.3, 12);
            const col = d === "f" ? C.ok : d === "s" ? C.bad : C.panel2;
            return <div key={i} style={{ width: 96, height: 96, borderRadius: 18, background: col, border: `1.5px solid ${d === "n" ? C.line : col}`, opacity: p, transform: `scale(${0.6 + p * 0.4})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 40, color: "#061018", fontWeight: 700, fontFamily: SANS }}>{d === "f" ? "↑" : d === "s" ? "↓" : ""}</div>;
          })}
        </div>
        <Rise at={c1 + 50} style={{ position: "absolute", right: 110, top: 400, width: 340, fontFamily: SANS }}>
          <div style={{ fontSize: 76, fontWeight: 700, color: C.ok }}>{data.kb.faster} <span style={{ fontSize: 30, fontWeight: 500 }}>faster</span></div>
          <div style={{ fontSize: 76, fontWeight: 700, color: C.bad, marginTop: 6 }}>{data.kb.slower} <span style={{ fontSize: 30, fontWeight: 500 }}>slower</span></div>
          <div style={{ fontSize: 22, color: C.mute, marginTop: 14 }}>confirmed by timing; grey = no confirmed change</div>
        </Rise>
      </div>
      <div style={{ opacity: prog(f, c2, 14) }}>
        <Title kicker="The trap" at={c2}>Fewer instructions ≠ faster code</Title>
        <Panel style={{ left: 110, top: 215, width: W + 40, height: H + 40, padding: 20 }}>
          <svg width={W} height={H}>
            <line x1={x0} x2={W - 20} y1={sy(1)} y2={sy(1)} stroke={C.line} strokeWidth="2" />
            <line x1={sx(1)} x2={sx(1)} y1={y0} y2={H - 40} stroke={C.line} strokeWidth="2" />
            {data.ir.pts.slice(0, shown).map((p, i) => <circle key={i} cx={sx(p[0])} cy={sy(p[1])} r="4" fill={C.acc2} opacity="0.55" />)}
            <text x={(x0 + W) / 2} y={H - 8} fill={C.mute} fontSize="24" textAnchor="middle" fontFamily={SANS}>IR instruction count relative to -O3</text>
            <text transform={`translate(30 ${H / 2}) rotate(-90)`} fill={C.mute} fontSize="24" textAnchor="middle" fontFamily={SANS}>measured speedup</text>
          </svg>
        </Panel>
        <Rise at={c4} style={{ position: "absolute", left: 1220, top: 310, width: 620, fontFamily: SANS }}>
          <div style={{ fontFamily: MONO, fontSize: 28, color: C.mute }}>rank correlation</div>
          <div style={{ fontSize: 108, fontWeight: 700, color: C.warn, lineHeight: 1.15, whiteSpace: "nowrap" }}>ρ = −{Math.abs(data.ir.rho).toFixed(2)}</div>
          <div style={{ fontSize: 30, color: C.text, marginTop: 14 }}>{data.ir.n.toLocaleString("en-US")} timed candidates</div>
          <div style={{ fontSize: 26, color: C.mute, marginTop: 6 }}>IR count barely predicts runtime</div>
        </Rise>
      </div>
    </SceneFrame>
  );
};

/* ---------- 3. Measurement ---------- */
const ROUNDS = [["B", "1", "A", "2"], ["2", "B", "1", "A"], ["A", "2", "B", "1"], ["1", "A", "2", "B"], ["B", "2", "A", "1"]];
const LANE: Record<string, [string, string]> = { B: [C.o3, "-O3"], A: [C.acc2, "A/A copy"], "1": [C.acc, "cand 1"], "2": [C.rl, "cand 2"] };
export const Measure: React.FC = () => {
  const f = useCurrentFrame();
  const c0 = cue("measure", 0), c1 = cue("measure", 1), c2 = cue("measure", 2), c3 = cue("measure", 3);
  const hold = prog(f, c3 - 4, 14);
  return (
    <SceneFrame>
      <Title kicker="Rule one">Only measured runtime counts</Title>
      <div style={{ opacity: 1 - hold * 0.93 }}>
        <Rise at={c1 - 6} style={{ position: "absolute", left: 110, top: 225, display: "flex", gap: 16 }}>
          <Chip color={C.ok}>pinned vCPU</Chip><Chip color={C.lib}>ASLR off</Chip><Chip color={C.acc}>shuffled rounds</Chip><Chip color={C.warn}>paired bootstrap 95% CI</Chip>
        </Rise>
        {ROUNDS.map((r, ri) => r.map((k, i) => {
          const start = c1 + (ri * 4 + i) * 5;
          const p = lin(f, start, 12);
          const [col, label] = LANE[k];
          const isAA = k === "A";
          const glow = isAA ? prog(f, c2, 12) : 0;
          return (
            <div key={`${ri}${i}`} style={{ position: "absolute", left: 110 + i * 300, top: 320 + ri * 100, width: 284, height: 86, borderRadius: 12, background: C.panel, border: `1.5px solid ${isAA && glow ? C.acc2 : C.line}`, overflow: "hidden", boxShadow: glow ? `0 0 ${glow * 22}px ${C.acc2}aa` : "none", opacity: p > 0 ? 1 : 0.35 }}>
              <div style={{ position: "absolute", inset: 0, width: `${p * 100}%`, background: `${col}55` }} />
              <div style={{ position: "relative", fontFamily: MONO, fontSize: 26, color: C.text, lineHeight: "86px", textAlign: "center" }}>{label}</div>
            </div>
          );
        }))}
        <Rise at={c2} style={{ position: "absolute", left: 1370, top: 320, width: 450, fontFamily: SANS }}>
          <div style={{ fontSize: 42, fontWeight: 700, color: C.acc2 }}>A/A control</div>
          <div style={{ fontSize: 32, color: C.text, marginTop: 12, lineHeight: 1.35 }}>byte-identical copy of -O3. It must measure 1.00×, or the run is noise.</div>
        </Rise>
      </div>
      <div style={{ position: "absolute", left: 240, top: 340, width: 1440, opacity: hold }}>
        <Panel style={{ left: 0, top: 0, width: 1440, padding: "48px 56px", fontFamily: MONO, fontSize: 42 }}>
          <div style={{ color: C.mute, fontSize: 26, marginBottom: 20 }}>program output vs the -O0 build</div>
          <div style={{ display: "flex", justifyContent: "space-between", color: C.text, opacity: prog(f, c3 + 10, 10) }}><span>candidate A  output identical</span><span style={{ color: C.ok }}>✓ keep</span></div>
          <div style={{ display: "flex", justifyContent: "space-between", color: C.bad, marginTop: 34, opacity: prog(f, c3 + 34, 10) }}><span style={{ textDecoration: prog(f, c3 + 44, 8) > 0.5 ? "line-through" : "none" }}>candidate B  output differs</span><span>✗ rejected</span></div>
        </Panel>
      </div>
    </SceneFrame>
  );
};

/* ---------- 4. Data and models ---------- */
const Tree: React.FC<{ x: number; col: string; on: number }> = ({ x, col, on }) => (
  <g transform={`translate(${x} 0)`} opacity={on}>
    {[[50, 16, 22, 62], [50, 16, 78, 62], [22, 62, 8, 108], [22, 62, 36, 108], [78, 62, 64, 108], [78, 62, 92, 108]].map((l, i) => <line key={i} x1={l[0]} y1={l[1]} x2={l[2]} y2={l[3]} stroke={col} strokeWidth="3" />)}
    {[[50, 16], [22, 62], [78, 62], [8, 108], [36, 108], [64, 108], [92, 108]].map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="9" fill={col} />)}
  </g>
);
const editLabels = ["-tail-dup-size=6", "-unroll-max-count=4", "delete all simplifycfg", "delete all instcombine"];
export const Learn: React.FC = () => {
  const f = useCurrentFrame();
  const { durationInFrames: d } = useVideoConfig();
  const c1 = cue("learn", 1), c2 = cue("learn", 2), c3 = cue("learn", 3), c4 = cue("learn", 4);
  return (
    <SceneFrame>
      <Title kicker="Learning from measurements">Search first, then train</Title>
      <Panel style={{ left: 110, top: 240, width: 520, height: 500, padding: 38, fontFamily: SANS }}>
        <div style={{ fontFamily: MONO, fontSize: 24, color: C.mute }}>real programs</div>
        <div style={{ fontSize: 96, fontWeight: 700, color: C.text, lineHeight: 1.15 }}>{count(f, 6, 30, 146)}</div>
        <div style={{ fontFamily: MONO, fontSize: 24, color: C.mute, marginTop: 20, opacity: prog(f, c1 - 4, 10) }}>candidate pipelines</div>
        <div style={{ fontSize: 96, fontWeight: 700, color: C.acc2, lineHeight: 1.15, opacity: prog(f, c1 - 4, 10) }}>{count(f, c1, 40, 70409).toLocaleString("en-US")}</div>
        <div style={{ fontFamily: MONO, fontSize: 22, color: C.mute, marginTop: 18, opacity: prog(f, c1 + 30, 10) }}>dataset.sqlite · PolyBench + LLVM test-suite</div>
      </Panel>
      {/* flow to the models */}
      <svg style={{ position: "absolute", left: 630, top: 240 }} width="200" height="500">
        {[[250, 110], [250, 380]].map(([a, b], i) => <path key={i} d={`M0 ${a} C100 ${a} 100 ${b} 200 ${b}`} fill="none" stroke={i ? C.rl : C.lib} strokeWidth="4" strokeDasharray="10 10" strokeDashoffset={-f * 2} opacity={prog(f, c2, 14)} />)}
      </svg>
      <Panel style={{ left: 830, top: 240, width: 980, height: 240, padding: 28, opacity: prog(f, c2, 14) }}>
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 38, color: C.lib }}>LightGBM <span style={{ fontWeight: 400, fontSize: 26, color: C.mute }}>supervised · predicts speedup</span></div>
        <svg width="560" height="130" style={{ marginTop: 14 }}>
          {[0, 1, 2, 3, 4].map((i) => <Tree key={i} x={i * 112} col={i % 2 ? C.lib : C.acc2} on={prog(f, c3 + i * 7, 10)} />)}
        </svg>
        <div style={{ position: "absolute", right: 34, top: 112, fontFamily: MONO, fontSize: 26, color: C.text, lineHeight: 1.5, opacity: prog(f, c3 + 34, 12) }}>program features<br />+ pipeline edits<br /><span style={{ color: C.acc2 }}>→ predicted speedup</span></div>
      </Panel>
      <Panel style={{ left: 830, top: 500, width: 980, height: 240, padding: 28, opacity: prog(f, c3 + 10, 14) }}>
        <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 38, color: C.rl }}>PPO <span style={{ fontWeight: 400, fontSize: 26, color: C.mute }}>reinforcement learning · builds pipelines</span></div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14, marginTop: 24 }}>
          <Chip color={C.o3}>-O3</Chip>
          {editLabels.map((e, i) => { const s = c4 + 14 + i * Math.max(12, (d - c4 - 50) / 4); return <span key={e} style={{ opacity: prog(f, s, 10), transform: `translateY(${(1 - prog(f, s, 10)) * 18}px)` }}><Chip color={C.rl}>+ {e}</Chip></span>; })}
        </div>
      </Panel>
    </SceneFrame>
  );
};
