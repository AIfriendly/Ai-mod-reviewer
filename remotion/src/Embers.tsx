import React from "react";
import { AbsoluteFill, interpolate, random, useCurrentFrame, useVideoConfig } from "remotion";

// Deterministic drifting ember particles — gives the title card a living,
// dragon-fire feel without any external assets.
export const Embers: React.FC<{ count?: number; accent?: string }> = ({
  count = 60,
  accent = "#d4af37",
}) => {
  const frame = useCurrentFrame();
  const { width, height, durationInFrames } = useVideoConfig();

  return (
    <AbsoluteFill>
      {new Array(count).fill(0).map((_, i) => {
        const seedX = random(`x-${i}`);
        const seedSize = random(`s-${i}`);
        const seedSpeed = random(`v-${i}`);
        const seedPhase = random(`p-${i}`);

        const speed = 0.3 + seedSpeed * 0.9;
        const progress = ((frame * speed) / durationInFrames + seedPhase) % 1;
        const y = height - progress * (height + 80);
        const sway = Math.sin((frame / 18) + seedPhase * 6) * 24;
        const x = seedX * width + sway;
        const size = 2 + seedSize * 5;
        const opacity = interpolate(progress, [0, 0.1, 0.8, 1], [0, 1, 1, 0]);

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: size,
              height: size,
              borderRadius: "50%",
              background: accent,
              opacity: opacity * (0.4 + seedSize * 0.6),
              filter: `blur(${size > 4 ? 1.5 : 0.5}px)`,
              boxShadow: `0 0 ${size * 2}px ${accent}`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};
