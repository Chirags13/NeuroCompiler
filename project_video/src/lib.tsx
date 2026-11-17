import React from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import timeline from "./timeline.json";

export const C = {
  bg: "#070a14", panel: "#0f1424", panel2: "#161c30", line: "#2a3350", text: "#eef1f8", mute: "#8e98b3",
  acc: "#8b5cf6", acc2: "#22d3ee", rl: "#ec4899", lib: "#3b82f6", ok: "#34d399", bad: "#f87171", warn: "#fbbf24", o3: "#94a3b8",
};
export const SANS = "Inter, sans-serif";
export const MONO = "JBMono, monospace";

export const FPS = timeline.fps;
export const sceneOf = (id: string) => timeline.scenes.find((s) => s.id === id)!;

/** Frame, relative to the scene, at which phrase i of the voiceover starts. */
export const cue = (id: string, i: number) => {
  const s = sceneOf(id);
  return Math.round((s.phrases[i].start - s.start) * FPS);
};

const out = Easing.bezier(0.16, 1, 0.3, 1);
export const prog = (f: number, start: number, dur = 18) =>
  interpolate(f, [start, start + dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: out });
export const lin = (f: number, start: number, dur: number) =>
  interpolate(f, [start, start + dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

/** Fade + rise in at `at`, optional fade out at `until`. */
export const Rise: React.FC<{ at: number; until?: number; y?: number; style?: React.CSSProperties; children: React.ReactNode }> = ({ at, until, y = 24, style, children }) => {
  const f = useCurrentFrame();
  const p = prog(f, at);
  const q = until === undefined ? 0 : prog(f, until, 12);
  return <div style={{ ...style, opacity: p * (1 - q), transform: `${style?.transform ?? ""} translateY(${(1 - p) * y - q * 12}px)` }}>{children}</div>;
};

/** Wraps a scene: fades and slides between scenes. */
export const SceneFrame: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const f = useCurrentFrame();
  const { durationInFrames: d } = useVideoConfig();
  const a = prog(f, 0, 14);
  const b = lin(f, d - 10, 10);
  return <div style={{ position: "absolute", inset: 0, opacity: a * (1 - b), transform: `scale(${1.02 - a * 0.02 + b * 0.015})` }}>{children}</div>;
};

export const Title: React.FC<{ kicker: string; children: React.ReactNode; at?: number; until?: number; x?: number; y?: number }> = ({ kicker, children, at = 4, until, x = 110, y = 74 }) => (
  <Rise at={at} until={until} style={{ position: "absolute", left: x, top: y }}>
    <div style={{ fontFamily: MONO, fontSize: 23, letterSpacing: 3, color: C.acc2, textTransform: "uppercase" }}>{kicker}</div>
    <div style={{ fontFamily: SANS, fontWeight: 700, fontSize: 52, color: C.text, marginTop: 8, letterSpacing: -1 }}>{children}</div>
  </Rise>
);

export const Chip: React.FC<{ color?: string; mono?: boolean; style?: React.CSSProperties; children: React.ReactNode }> = ({ color = C.line, mono = true, style, children }) => (
  <span style={{ fontFamily: mono ? MONO : SANS, fontSize: 22, color: C.text, border: `1.5px solid ${color}`, background: `${color}22`, borderRadius: 10, padding: "8px 16px", whiteSpace: "nowrap", ...style }}>{children}</span>
);

export const Panel: React.FC<{ style?: React.CSSProperties; children: React.ReactNode }> = ({ style, children }) => (
  <div style={{ position: "absolute", background: `${C.panel}e6`, border: `1.5px solid ${C.line}`, borderRadius: 22, boxShadow: "0 24px 70px #0009", ...style }}>{children}</div>
);

export const Stopwatch: React.FC<{ size?: number; color?: string; speed?: number }> = ({ size = 90, color = C.acc2, speed = 8 }) => {
  const f = useCurrentFrame();
  return (
    <svg width={size} height={size} viewBox="0 0 100 100">
      <rect x="43" y="4" width="14" height="9" rx="2" fill={color} />
      <circle cx="50" cy="56" r="37" fill="none" stroke={color} strokeWidth="7" />
      <line x1="50" y1="56" x2="50" y2="30" stroke={C.text} strokeWidth="5" strokeLinecap="round" transform={`rotate(${f * speed} 50 56)`} />
      <circle cx="50" cy="56" r="5" fill={C.text} />
    </svg>
  );
};

export const Logo: React.FC<{ size?: number }> = ({ size = 120 }) => (
  <div style={{ width: size, height: size, borderRadius: size * 0.26, background: `linear-gradient(135deg, ${C.acc}, ${C.lib})`, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: SANS, fontWeight: 700, fontSize: size * 0.56, color: "#fff", boxShadow: `0 0 ${size * 0.8}px ${C.acc}66` }}>N</div>
);

export const count = (f: number, start: number, dur: number, to: number) => Math.round(prog(f, start, dur) * to);
