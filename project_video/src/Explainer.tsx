import React from "react";
import "./fonts.css";
import { AbsoluteFill, Audio, Sequence, cancelRender, continueRender, delayRender, getRemotionEnvironment, staticFile, useCurrentFrame } from "remotion";
import { C, FPS, MONO, SANS } from "./lib";
import timeline from "./timeline.json";
import { Hook, Learn, Measure, Problem } from "./scenes/one";
import { Close, Results, Stack, Tune } from "./scenes/two";

// fonts are embedded as data URIs (src/fonts.css) so every render process has them at once
const handle = delayRender("fonts", { timeoutInMilliseconds: 120000 });
Promise.all(["400 20px Inter", "500 20px Inter", "600 20px Inter", "700 20px Inter", "400 20px JBMono", "500 20px JBMono"].map((x) => document.fonts.load(x)))
  .then(() => continueRender(handle)).catch(cancelRender);

const SCENES: Record<string, React.FC> = { hook: Hook, problem: Problem, measure: Measure, learn: Learn, tune: Tune, results: Results, stack: Stack, close: Close };

const Backdrop: React.FC = () => {
  const f = useCurrentFrame();
  const a = f * 0.25, b = Math.sin(f / 90) * 120;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <AbsoluteFill style={{ backgroundImage: `linear-gradient(${C.line}33 1px, transparent 1px), linear-gradient(90deg, ${C.line}33 1px, transparent 1px)`, backgroundSize: "70px 70px", backgroundPosition: `${a}px ${a}px` }} />
      <AbsoluteFill style={{ background: `radial-gradient(900px 620px at ${300 + b}px 180px, ${C.acc}2e, transparent 70%), radial-gradient(800px 600px at ${1640 - b}px 900px, ${C.lib}26, transparent 70%)` }} />
    </AbsoluteFill>
  );
};

const Captions: React.FC = () => {
  const t = useCurrentFrame() / FPS;
  const p = timeline.scenes.filter((s) => s.id !== "close").flatMap((s) => s.phrases).find((x) => t >= x.start - 0.05 && t < x.end + 0.15);
  if (!p) return null;
  const a = Math.min(1, (t - p.start + 0.05) / 0.12);
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: 56, textAlign: "center" }}>
      <span style={{ opacity: a, fontFamily: SANS, fontWeight: 500, fontSize: 36, color: "#fff", background: "#05070ee0", padding: "10px 24px", borderRadius: 12, border: `1px solid ${C.line}` }}>{p.text}</span>
    </div>
  );
};

const Progress: React.FC = () => {
  const f = useCurrentFrame();
  return <div style={{ position: "absolute", left: 0, bottom: 0, height: 4, width: `${(f / (timeline.total * FPS)) * 100}%`, background: `linear-gradient(90deg, ${C.acc}, ${C.acc2})` }} />;
};

export const Explainer: React.FC = () => (
  <AbsoluteFill style={{ fontFamily: SANS }}>
    <Backdrop />
    {timeline.scenes.map((s) => {
      const Sc = SCENES[s.id];
      return <Sequence key={s.id} from={Math.round(s.start * FPS)} durationInFrames={Math.round(s.dur * FPS)}><Sc /></Sequence>;
    })}
    <Captions />
    <Progress />
    {!getRemotionEnvironment().isRendering && <Audio src={staticFile("mix.wav")} />}{/* the render is muxed with mix.wav by build.sh */}
  </AbsoluteFill>
);
