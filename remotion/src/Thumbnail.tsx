import React from "react";
import { AbsoluteFill, Img, staticFile, useVideoConfig } from "remotion";

export interface ThumbnailProps {
  headline: string;     // e.g. "BEST WEAPON MODS"
  keyword: string;      // word(s) to colour in the accent, e.g. "BEST"
  banner: string;       // top tag, e.g. "2026" or "REMASTERED"
  images: string[];     // staticFile names (1-3); split into panels
  accent: string;
  badge: boolean;       // draw an ESRB-style "E" badge
  brand?: string;       // channel brand name shown as a corner tag
}

// Per-panel colour wash, like the split character panels on Heavy Burns / Syn Gaming.
const WASHES = [
  "linear-gradient(180deg, rgba(20,60,120,0.15), rgba(0,0,0,0.65))",
  "linear-gradient(180deg, rgba(150,30,30,0.18), rgba(0,0,0,0.65))",
  "linear-gradient(180deg, rgba(30,120,60,0.18), rgba(0,0,0,0.65))",
];

export const Thumbnail: React.FC<ThumbnailProps> = ({
  headline, keyword, banner, images, accent, badge, brand,
}) => {
  const { width, height } = useVideoConfig();
  const panels = (images.length ? images : ["thumb_0.jpg"]).slice(0, 3);
  const kw = new Set(keyword.toUpperCase().split(/\s+/).filter(Boolean));
  const words = headline.toUpperCase().split(/\s+/);

  return (
    <AbsoluteFill style={{ backgroundColor: "#05080c" }}>
      {/* Split image panels */}
      <AbsoluteFill style={{ flexDirection: "row" }}>
        {panels.map((img, i) => (
          <div key={i} style={{ flex: 1, position: "relative", overflow: "hidden",
              borderRight: i < panels.length - 1 ? `4px solid ${accent}` : "none" }}>
            <Img src={staticFile(img)}
              style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            <AbsoluteFill style={{ background: WASHES[i % WASHES.length] }} />
          </div>
        ))}
      </AbsoluteFill>

      {/* Cinematic darkening: top + bottom gradients for text legibility */}
      <AbsoluteFill style={{ background:
        "linear-gradient(180deg, rgba(0,0,0,0.55) 0%, rgba(0,0,0,0) 28%, rgba(0,0,0,0) 50%, rgba(0,0,0,0.88) 100%)" }} />

      {/* Top banner pill */}
      {banner ? (
        <div style={{ position: "absolute", top: 34, left: 40, display: "flex",
            alignItems: "center", gap: 14 }}>
          <div style={{ width: 12, height: 46, background: accent, borderRadius: 2 }} />
          <span style={{ fontFamily: "Arial Black, Arial, sans-serif", fontWeight: 900,
            fontSize: 46, color: accent, letterSpacing: 2,
            textShadow: "0 3px 10px rgba(0,0,0,0.8)", textTransform: "uppercase" }}>
            {banner}
          </span>
        </div>
      ) : null}

      {/* Headline — auto-fit so long headlines never chop. Size from the longest
          word (must fit the width) and total length (keeps it to ~2-3 lines). */}
      <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "flex-start",
          padding: "0 56px 70px" }}>
        <h1 style={{ margin: 0, fontFamily: "Arial Black, Arial, sans-serif",
            fontWeight: 900,
            fontSize: Math.max(64, Math.min(
              140,
              (width * 0.9) / (Math.max(...words.map((w) => w.length)) * 0.62),
              (width * 1.7) / headline.length)),
            lineHeight: 0.95, letterSpacing: 1,
            textTransform: "uppercase", maxWidth: width * 0.92,
            WebkitTextStroke: "10px #000",
            textShadow: "0 8px 26px rgba(0,0,0,0.9)" }}>
          {words.map((w, i) => (
            <span key={i} style={{
              color: kw.has(w.replace(/[^A-Z0-9]/g, "")) ? accent : "#ffffff",
              marginRight: 24, display: "inline-block",
              // paint the stroke behind, fill on top
              WebkitTextStroke: "10px #000",
              paintOrder: "stroke fill" as any,
            }}>{w}</span>
          ))}
        </h1>
      </AbsoluteFill>

      {/* ESRB-style badge, bottom-left */}
      {badge ? (
        <div style={{ position: "absolute", bottom: 24, left: 40, width: 70, height: 88,
            background: "#fff", borderRadius: 6, display: "flex", flexDirection: "column",
            justifyContent: "space-between", alignItems: "center", padding: "8px 0",
            boxShadow: "0 4px 12px rgba(0,0,0,0.6)" }}>
          <span style={{ fontFamily: "Arial Black, sans-serif", fontWeight: 900,
            fontSize: 46, color: "#111", lineHeight: 1 }}>E</span>
          <span style={{ fontFamily: "Arial, sans-serif", fontWeight: 700,
            fontSize: 11, color: "#111", letterSpacing: 0.5 }}>EVERYONE</span>
        </div>
      ) : null}

      {/* Channel brand tag, top-right */}
      {brand ? (
        <div style={{ position: "absolute", top: 30, right: 30, display: "flex",
            alignItems: "center", gap: 10, background: "rgba(8,11,16,0.82)",
            border: `3px solid ${accent}`, borderRadius: 10, padding: "8px 18px",
            boxShadow: "0 3px 10px rgba(0,0,0,0.6)" }}>
          <div style={{ width: 16, height: 16, background: accent,
            transform: "rotate(45deg)" }} />
          <span style={{ fontFamily: "Arial Black, Arial, sans-serif", fontWeight: 900,
            fontSize: 40, color: "#fff", letterSpacing: 1, textTransform: "uppercase" }}>
            {brand}
          </span>
        </div>
      ) : null}

      {/* Accent border frame */}
      <AbsoluteFill style={{ border: `8px solid ${accent}`, pointerEvents: "none",
        boxShadow: "inset 0 0 120px rgba(0,0,0,0.6)" }} />
    </AbsoluteFill>
  );
};
