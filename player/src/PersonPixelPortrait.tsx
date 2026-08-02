import { useEffect, useRef } from "react";
import type { PersonVisualProfile } from "./types";

const SKIN = ["#f0c49a", "#dca77d", "#bd825f", "#976047", "#744635", "#503126"];
const SKIN_LIGHT = ["#ffdab1", "#efbd91", "#d69b75", "#b97959", "#925b45", "#694331"];
const SKIN_SHADE = ["#c58c68", "#b67755", "#985f45", "#764735", "#593326", "#38231c"];
const HAIR = ["#28231f", "#4a3024", "#6b4931", "#9a7047", "#b7aaa0", "#e0d7c8"];
const ACCENTS = ["#708b72", "#9b6a4a", "#5d7890", "#8b7952", "#775f82", "#6f7c53"];
const OUTFITS: Record<string, [string, string, string]> = {
  scholar: ["#526b78", "#354a55", "#b49a61"], merchant: ["#667e61", "#42563f", "#b7834f"],
  artisan: ["#8b6350", "#594235", "#6f8791"], guard: ["#667078", "#3e484e", "#9a7344"],
  laborer: ["#807153", "#544a38", "#9b6545"], official: ["#745f65", "#493d42", "#b49a61"],
  cleric: ["#5e665c", "#3b433c", "#9a895b"], traveler: ["#6f6559", "#463f38", "#7f8a6a"],
  common: ["#74745a", "#494b3a", "#8a654f"],
};

function rect(ctx: CanvasRenderingContext2D, color: string, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, h);
}

function poly(ctx: CanvasRenderingContext2D, color: string, points: Array<[number, number]>) {
  ctx.fillStyle = color;
  ctx.beginPath();
  points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
  ctx.closePath();
  ctx.fill();
}

function drawHair(ctx: CanvasRenderingContext2D, profile: PersonVisualProfile, color: string) {
  const style = profile.hair_style;
  if (style === "balding") {
    rect(ctx, color, 31, 27, 7, 18); rect(ctx, color, 58, 27, 7, 18); rect(ctx, color, 37, 24, 7, 5); rect(ctx, color, 52, 24, 7, 5);
  } else {
    poly(ctx, color, [[29, 43], [29, 28], [36, 20], [59, 20], [67, 28], [67, 46], [61, 39], [59, 30], [51, 27], [39, 30], [35, 42]]);
    if (style === "cropped") rect(ctx, color, 34, 24, 28, 7);
    if (style === "long" || style === "wavy") { rect(ctx, color, 27, 38, 8, 29); rect(ctx, color, 61, 38, 8, 29); }
    if (style === "braided") { rect(ctx, color, 61, 38, 7, 31); rect(ctx, color, 63, 67, 5, 13); }
  }
}

function drawHeadwear(ctx: CanvasRenderingContext2D, profile: PersonVisualProfile, base: string, shade: string) {
  if (profile.headwear === "none") return;
  if (profile.headwear === "cap") {
    rect(ctx, shade, 29, 21, 39, 8); rect(ctx, base, 34, 17, 28, 9); rect(ctx, base, 62, 25, 10, 4);
  } else if (profile.headwear === "wrap") {
    rect(ctx, shade, 29, 24, 39, 9); rect(ctx, base, 33, 19, 31, 10); rect(ctx, shade, 38, 22, 4, 9); rect(ctx, shade, 52, 20, 4, 10);
  } else if (profile.headwear === "hood") {
    poly(ctx, shade, [[25, 48], [27, 27], [36, 16], [59, 16], [69, 28], [71, 54], [63, 45], [61, 30], [53, 24], [40, 24], [33, 31], [33, 46]]);
  } else if (profile.headwear === "hat") {
    rect(ctx, shade, 20, 27, 57, 6); poly(ctx, base, [[31, 27], [36, 15], [61, 15], [67, 27]]); rect(ctx, shade, 35, 23, 29, 4);
  } else if (profile.headwear === "helmet") {
    poly(ctx, shade, [[27, 43], [29, 25], [37, 16], [59, 16], [67, 25], [69, 43], [61, 34], [35, 34]]);
    rect(ctx, base, 35, 20, 27, 12); rect(ctx, ACCENTS[profile.accent], 46, 14, 4, 8);
  }
}

export default function PersonPixelPortrait({ profile, name }: { profile: PersonVisualProfile; name: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.imageSmoothingEnabled = false;
    const skin = SKIN[profile.skin_tone] ?? SKIN[2];
    const skinLight = SKIN_LIGHT[profile.skin_tone] ?? SKIN_LIGHT[2];
    const skinShade = SKIN_SHADE[profile.skin_tone] ?? SKIN_SHADE[2];
    let hair = HAIR[profile.hair_color] ?? HAIR[1];
    if (profile.age_group === "elder" && profile.hair_color < 4) hair = HAIR[4 + (profile.seed % 2)];
    const [cloth, clothShade, trim] = OUTFITS[profile.outfit] ?? OUTFITS.common;

    rect(ctx, "#24302a", 0, 0, 96, 112);
    rect(ctx, "#2d3b33", 5, 5, 86, 102);
    for (let y = 7; y < 106; y += 8) for (let x = 7; x < 90; x += 8) if ((x + y + profile.seed) % 3 === 0) rect(ctx, "#324238", x, y, 1, 1);
    rect(ctx, "#17201b", 7, 101, 82, 5);

    poly(ctx, clothShade, [[9, 108], [14, 85], [31, 74], [65, 74], [82, 85], [87, 108]]);
    poly(ctx, cloth, [[14, 108], [18, 88], [34, 78], [62, 78], [78, 88], [82, 108]]);
    rect(ctx, trim, 46, 81, 4, 27);
    if (profile.outfit === "guard") { rect(ctx, "#8e999c", 18, 87, 18, 5); rect(ctx, "#8e999c", 60, 87, 18, 5); }
    if (profile.outfit === "laborer") { rect(ctx, "#5b4232", 27, 79, 7, 29); rect(ctx, "#5b4232", 62, 79, 7, 29); }

    rect(ctx, skinShade, 39, 68, 18, 15);
    rect(ctx, skin, 41, 66, 14, 17);
    rect(ctx, skinShade, 25, 43, 8, 17); rect(ctx, skinShade, 63, 43, 8, 17);
    const face = profile.face_shape === "round"
      ? [[32, 34], [38, 27], [58, 27], [65, 34], [64, 58], [56, 70], [40, 70], [32, 58]]
      : profile.face_shape === "angular"
        ? [[31, 33], [38, 26], [59, 26], [66, 34], [62, 61], [54, 71], [42, 71], [34, 61]]
        : [[32, 32], [39, 25], [57, 25], [64, 32], [64, 58], [56, 70], [40, 70], [32, 58]];
    poly(ctx, skinShade, face.map(([x, y]) => [x + 2, y + 2] as [number, number]));
    poly(ctx, skin, face as Array<[number, number]>);
    rect(ctx, skinLight, 37, 32, 4, 22);
    drawHair(ctx, profile, hair);
    drawHeadwear(ctx, profile, cloth, clothShade);

    const browY = profile.expression === "stern" || profile.expression === "focused" ? 42 : 41;
    rect(ctx, hair, 37, browY, 7, 2); rect(ctx, hair, 53, browY, 7, 2);
    const eyeY = profile.expression === "weary" ? 47 : 46;
    rect(ctx, "#202720", 39, eyeY, 3, 2); rect(ctx, "#202720", 55, eyeY, 3, 2);
    rect(ctx, skinShade, 47, 48, 3, 9); rect(ctx, skinLight, 46, 49, 2, 6);
    if (profile.expression === "warm") { rect(ctx, "#7b3f38", 43, 61, 11, 2); rect(ctx, skinLight, 46, 63, 5, 1); }
    else if (profile.expression === "weary") { rect(ctx, "#75463c", 43, 63, 11, 2); rect(ctx, skinShade, 38, 50, 5, 1); rect(ctx, skinShade, 54, 50, 5, 1); }
    else rect(ctx, "#75463c", 44, 62, 9, 2);

    if (profile.age_group === "mature" || profile.age_group === "elder") { rect(ctx, skinShade, 35, 55, 5, 1); rect(ctx, skinShade, 57, 55, 5, 1); }
    if (profile.age_group === "elder") { rect(ctx, skinShade, 38, 67, 4, 1); rect(ctx, skinShade, 55, 67, 4, 1); }
    if (profile.detail === "freckles") { rect(ctx, "#9b6049", 38, 54, 2, 1); rect(ctx, "#9b6049", 57, 54, 2, 1); rect(ctx, "#9b6049", 42, 56, 1, 1); }
    if (profile.detail === "scar") { rect(ctx, skinShade, 58, 47, 2, 12); rect(ctx, skinLight, 60, 49, 1, 8); }
    if (profile.detail === "earring") { rect(ctx, ACCENTS[profile.accent], 66, 57, 3, 4); }
  }, [profile]);
  return <canvas ref={canvasRef} width={96} height={112} role="img" aria-label={`${name}的像素肖像`} />;
}
