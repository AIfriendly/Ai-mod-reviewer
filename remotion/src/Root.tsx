import React from "react";
import { Composition } from "remotion";
import { TitleCard } from "./TitleCard";
import { Thumbnail } from "./Thumbnail";

// The Python pipeline passes props via --props (defaultProps below are fallbacks).
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="TitleCard"
        component={TitleCard}
        durationInFrames={150} // 5s at 30fps — room for the kinetic title to breathe
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          title: "Best Skyrim Mods",
          subtitle: "@YourChannel",
          accent: "#d4af37",
        }}
      />
      <Composition
        id="Thumbnail"
        component={Thumbnail}
        durationInFrames={1}
        fps={1}
        width={1280}
        height={720}
        defaultProps={{
          headline: "BEST WEAPON MODS",
          keyword: "BEST",
          banner: "2026",
          images: ["thumb_0.jpg"],
          accent: "#d4af37",
          badge: true,
        }}
      />
    </>
  );
};
