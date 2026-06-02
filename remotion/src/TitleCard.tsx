import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

export interface TitleCardProps {
  title: string;
  subtitle: string;
  accent: string;
}

export const TitleCard: React.FC<TitleCardProps> = ({ title, subtitle, accent }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const enter = spring({ frame, fps, config: { damping: 200 } });
  const scale = interpolate(enter, [0, 1], [0.85, 1]);
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 15, durationInFrames],
    [1, 0],
    { extrapolateLeft: "clamp" }
  );
  const barWidth = interpolate(enter, [0, 1], [0, 480]);

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(circle at 50% 40%, #1b2a3a 0%, #0a0f16 100%)",
        justifyContent: "center",
        alignItems: "center",
        opacity: fadeOut,
      }}
    >
      <div style={{ transform: `scale(${scale})`, opacity, textAlign: "center" }}>
        <div
          style={{
            height: 6,
            width: barWidth,
            background: accent,
            margin: "0 auto 36px",
            borderRadius: 3,
          }}
        />
        <h1
          style={{
            fontFamily: "Georgia, 'Times New Roman', serif",
            fontSize: 96,
            color: "white",
            margin: 0,
            letterSpacing: 2,
            textShadow: "0 4px 24px rgba(0,0,0,0.6)",
          }}
        >
          {title}
        </h1>
        <p
          style={{
            fontFamily: "Georgia, serif",
            fontSize: 38,
            color: accent,
            marginTop: 18,
            letterSpacing: 4,
          }}
        >
          {subtitle}
        </p>
      </div>
    </AbsoluteFill>
  );
};
