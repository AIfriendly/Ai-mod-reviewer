import React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Embers } from "./Embers";

export interface TitleCardProps {
  title: string;
  subtitle: string;
  accent: string;
}

// A cinematic, kinetic intro: a slow push-in over an ember field, a glowing
// accent bar that wipes open, the title rising word-by-word, then a vignette.
export const TitleCard: React.FC<TitleCardProps> = ({ title, subtitle, accent }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames, width, height } = useVideoConfig();

  // Slow continuous push-in (parallax depth).
  const push = interpolate(frame, [0, durationInFrames], [1.04, 1.14]);

  // Accent bar wipes open.
  const barEnter = spring({ frame: frame - 6, fps, config: { damping: 200 } });
  const barWidth = interpolate(barEnter, [0, 1], [0, 520]);
  const barGlow = interpolate(
    Math.sin(frame / 8),
    [-1, 1],
    [10, 28]
  );

  // Title rises word by word.
  const words = title.split(" ");

  // Subtitle fades in late.
  const subOpacity = interpolate(frame, [30, 48], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Whole card fades out at the end so it cuts cleanly into the video.
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp" }
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#070b11", opacity: fadeOut }}>
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at 50% 38%, #1d2c3c 0%, #0a0f16 70%, #05080c 100%)",
          transform: `scale(${push})`,
        }}
      />
      <Embers count={70} accent={accent} />

      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
        <div style={{ textAlign: "center", transform: `scale(${push})` }}>
          <div
            style={{
              height: 6,
              width: barWidth,
              background: accent,
              margin: "0 auto 34px",
              borderRadius: 3,
              boxShadow: `0 0 ${barGlow}px ${accent}`,
            }}
          />
          <h1
            style={{
              fontFamily: "Georgia, 'Times New Roman', serif",
              fontSize: 104,
              color: "white",
              margin: 0,
              letterSpacing: 2,
              lineHeight: 1.05,
              maxWidth: width * 0.8,
              textShadow: "0 6px 30px rgba(0,0,0,0.7)",
            }}
          >
            {words.map((w, i) => {
              const wordSpring = spring({
                frame: frame - 10 - i * 4,
                fps,
                config: { damping: 200, stiffness: 90 },
              });
              const dy = interpolate(wordSpring, [0, 1], [40, 0]);
              const o = interpolate(wordSpring, [0, 1], [0, 1]);
              return (
                <span
                  key={i}
                  style={{
                    display: "inline-block",
                    transform: `translateY(${dy}px)`,
                    opacity: o,
                    marginRight: 18,
                  }}
                >
                  {w}
                </span>
              );
            })}
          </h1>
          <p
            style={{
              fontFamily: "Georgia, serif",
              fontSize: 38,
              color: accent,
              marginTop: 22,
              letterSpacing: 6,
              textTransform: "uppercase",
              opacity: subOpacity,
            }}
          >
            {subtitle}
          </p>
        </div>
      </AbsoluteFill>

      {/* Vignette */}
      <AbsoluteFill
        style={{
          boxShadow: `inset 0 0 ${Math.min(width, height) * 0.5}px rgba(0,0,0,0.85)`,
          pointerEvents: "none",
        }}
      />
    </AbsoluteFill>
  );
};
