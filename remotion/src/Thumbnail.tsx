import React from "react";
import { AbsoluteFill, Img, staticFile, useVideoConfig } from "remotion";

export interface ThumbnailProps {
  headline: string;     // e.g. "GOD-TIER MAGIC MODS"
  keyword: string;      // word(s) to colour in the accent, e.g. "GOD-TIER"
  banner: string;       // small top tag, e.g. "SKYRIM • 2026"
  images: string[];     // staticFile names; first is the hero
  accent: string;
  count?: number;       // big "TOP N" number block
  brand?: string;       // channel brand name shown as a corner tag
}

// Bold single-hero layout (modeled on Heavy Burns / Mxadder): one epic screenshot,
// a heavy gradient for legibility, a giant TOP-N number block, and a punchy two-tone
// headline. Far less busy than a 3-panel split, which read as generic.
export const Thumbnail: React.FC<ThumbnailProps> = ({
  headline, keyword, banner, images, accent, count, brand,
}) => {
  const { width } = useVideoConfig();
  const hero = (images && images.length ? images[0] : "thumb_0.jpg");
  const kw = new Set(keyword.toUpperCase().split(/\s+/).filter(Boolean));
  const words = headline.toUpperCase().split(/\s+/);
  const longest = Math.max(1, ...words.map((w) => w.length));
  const fontSize = Math.max(
    78,
    Math.min(168, (width * 0.66) / (longest * 0.6), (width * 1.25) / headline.length),
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#05080c" }}>
      {/* Full-bleed hero */}
      <Img src={staticFile(hero)}
        style={{ position: "absolute", width: "100%", height: "100%",
          objectFit: "cover", transform: "scale(1.04)" }} />

      {/* Cinematic darkening: strong from the left + bottom so text pops */}
      <AbsoluteFill style={{ background:
        "linear-gradient(90deg, rgba(0,0,0,0.86) 0%, rgba(0,0,0,0.45) 42%, rgba(0,0,0,0) 70%)" }} />
      <AbsoluteFill style={{ background:
        "linear-gradient(0deg, rgba(0,0,0,0.92) 4%, rgba(0,0,0,0) 46%)" }} />

      {/* Top-left context pill */}
      {banner ? (
        <div style={{ position: "absolute", top: 30, left: 38, display: "flex",
            alignItems: "center", gap: 12 }}>
          <div style={{ width: 10, height: 38, background: accent, borderRadius: 2 }} />
          <span style={{ fontFamily: "Arial Black, Arial, sans-serif", fontWeight: 900,
            fontSize: 34, color: "#fff", letterSpacing: 3,
            textShadow: "0 3px 10px rgba(0,0,0,0.9)", textTransform: "uppercase" }}>
            {banner}
          </span>
        </div>
      ) : null}

      {/* Giant TOP-N number block, right side */}
      {count ? (
        <div style={{ position: "absolute", top: 0, bottom: 0, right: 44,
            display: "flex", flexDirection: "column", justifyContent: "center",
            alignItems: "center", transform: "rotate(-6deg)" }}>
          <span style={{ fontFamily: "Arial Black, Arial, sans-serif", fontWeight: 900,
            fontSize: 70, color: "#fff", letterSpacing: 6, lineHeight: 1,
            WebkitTextStroke: "6px #000", paintOrder: "stroke fill" as any,
            textShadow: "0 6px 18px rgba(0,0,0,0.9)" }}>TOP</span>
          <span style={{ fontFamily: "Arial Black, Arial, sans-serif", fontWeight: 900,
            fontSize: 280, color: accent, lineHeight: 0.8,
            WebkitTextStroke: "12px #000", paintOrder: "stroke fill" as any,
            textShadow: "0 12px 34px rgba(0,0,0,0.95)" }}>{count}</span>
        </div>
      ) : null}

      {/* Headline — big, two-tone, bottom-left */}
      <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "flex-start",
          padding: "0 56px 60px" }}>
        <h1 style={{ margin: 0, fontFamily: "Arial Black, Arial, sans-serif",
            fontWeight: 900, fontSize, lineHeight: 0.92, letterSpacing: 1,
            textTransform: "uppercase", maxWidth: width * 0.72 }}>
          {words.map((w, i) => (
            <span key={i} style={{
              color: kw.has(w.replace(/[^A-Z0-9-]/g, "")) ? accent : "#ffffff",
              marginRight: 22, display: "inline-block",
              WebkitTextStroke: "11px #000",
              paintOrder: "stroke fill" as any,
              textShadow: "0 8px 26px rgba(0,0,0,0.95)",
            }}>{w}</span>
          ))}
        </h1>
      </AbsoluteFill>

      {/* Channel brand tag, top-right */}
      {brand ? (
        <div style={{ position: "absolute", top: 28, right: 30, display: "flex",
            alignItems: "center", gap: 10, background: "rgba(8,11,16,0.85)",
            border: `3px solid ${accent}`, borderRadius: 10, padding: "7px 16px",
            boxShadow: "0 3px 10px rgba(0,0,0,0.7)" }}>
          <div style={{ width: 15, height: 15, background: accent,
            transform: "rotate(45deg)" }} />
          <span style={{ fontFamily: "Arial Black, Arial, sans-serif", fontWeight: 900,
            fontSize: 34, color: "#fff", letterSpacing: 1, textTransform: "uppercase" }}>
            {brand}
          </span>
        </div>
      ) : null}

      {/* Accent border frame */}
      <AbsoluteFill style={{ border: `8px solid ${accent}`, pointerEvents: "none",
        boxShadow: "inset 0 0 130px rgba(0,0,0,0.7)" }} />
    </AbsoluteFill>
  );
};
