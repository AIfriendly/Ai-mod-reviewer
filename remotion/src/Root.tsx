import React from "react";
import { Composition } from "remotion";
import { TitleCard } from "./TitleCard";

// The Python pipeline passes props via --props (defaultProps below are fallbacks).
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="TitleCard"
      component={TitleCard}
      durationInFrames={120} // 4s at 30fps
      fps={30}
      width={1920}
      height={1080}
      defaultProps={{
        title: "Best Skyrim Mods",
        subtitle: "@YourChannel",
        accent: "#d4af37",
      }}
    />
  );
};
