import React from "react";
import { Composition } from "remotion";
import { Explainer } from "./Explainer";
import timeline from "./timeline.json";

export const Root: React.FC = () => (
  <Composition id="Explainer" component={Explainer} durationInFrames={Math.round(timeline.total * timeline.fps)}
    fps={timeline.fps} width={1920} height={1080} />
);
