import { useEffect, useRef } from "react";
import type { ItemVisualProfile } from "./types";

type Palette = { base: string; light: string; shade: string; dark: string; accent: string };

const PALETTES: Record<string, Palette> = {
  parchment: { base: "#c9aa6c", light: "#ead49a", shade: "#8e6c3e", dark: "#493824", accent: "#704536" },
  stone: { base: "#89908a", light: "#b8beb5", shade: "#5f6863", dark: "#343b38", accent: "#707d73" },
  metal: { base: "#82929a", light: "#bac7c8", shade: "#4d6268", dark: "#28373b", accent: "#a05b37" },
  wood: { base: "#9a7045", light: "#c49a64", shade: "#68472f", dark: "#392b22", accent: "#78513b" },
  cloth: { base: "#8b8a69", light: "#b9b68d", shade: "#5f604d", dark: "#34372e", accent: "#76594b" },
};

function seededRandom(seed: number) {
  let value = seed || 1;
  return () => {
    value ^= value << 13;
    value ^= value >>> 17;
    value ^= value << 5;
    return (value >>> 0) / 4294967296;
  };
}

function polygon(ctx: CanvasRenderingContext2D, color: string, points: number[][]) {
  ctx.fillStyle = color;
  ctx.beginPath();
  points.forEach(([x, y], index) => index ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
  ctx.closePath();
  ctx.fill();
}

function drawDocument(ctx: CanvasRenderingContext2D, profile: ItemVisualProfile, palette: Palette) {
  const kind = profile.kind;
  if (kind === "codex") {
    ctx.fillStyle = "#151c18"; ctx.fillRect(26, 24, 78, 54);
    ctx.fillStyle = palette.light; ctx.fillRect(31, 22, 70, 50);
    ctx.fillStyle = palette.shade; ctx.fillRect(29, 18, 68, 50);
    ctx.fillStyle = palette.base; ctx.fillRect(33, 17, 66, 48);
    ctx.fillStyle = palette.dark; ctx.fillRect(33, 17, 7, 48);
    ctx.fillStyle = palette.accent; ctx.fillRect(48, 27, 37, 3); ctx.fillRect(52, 50, 29, 2);
    ctx.fillStyle = palette.light; ctx.fillRect(43, 21, 51, 2); ctx.fillRect(94, 24, 3, 35);
    return;
  }
  if (kind === "scroll") {
    ctx.fillStyle = palette.dark; ctx.fillRect(21, 22, 86, 5); ctx.fillRect(21, 70, 86, 5);
    ctx.fillStyle = palette.shade; ctx.fillRect(26, 18, 8, 61); ctx.fillRect(94, 18, 8, 61);
    ctx.fillStyle = palette.light; ctx.fillRect(31, 23, 66, 50);
    ctx.fillStyle = palette.base; ctx.fillRect(35, 25, 58, 46);
    for (let y = 34; y < 64; y += 7) { ctx.fillStyle = palette.accent; ctx.fillRect(43, y, 42 - (y % 3) * 4, 2); }
    return;
  }
  const points = kind === "tablet"
    ? [[31, 17], [96, 20], [102, 68], [91, 79], [29, 74], [24, 29]]
    : [[27, 18], [99, 21], [96, 76], [69, 73], [62, 79], [27, 74]];
  ctx.fillStyle = "#151c18"; ctx.fillRect(28, 24, 74, 56);
  polygon(ctx, palette.shade, points.map(([x, y]) => [x + 2, y + 3]));
  polygon(ctx, palette.base, points);
  ctx.fillStyle = palette.light; ctx.fillRect(34, 24, 54, 3);
  for (let y = 34; y < 67; y += 7) {
    ctx.fillStyle = palette.accent;
    ctx.fillRect(38 + (y % 4), y, 45 - (y % 5) * 3, kind === "tablet" ? 2 : 1);
  }
}

function drawArtifact(ctx: CanvasRenderingContext2D, profile: ItemVisualProfile, palette: Palette) {
  const { kind, variant } = profile;
  if (kind === "coin" || kind === "seal") {
    if (kind === "seal") { ctx.fillStyle = palette.dark; ctx.fillRect(58, 18, 13, 31); ctx.fillRect(53, 17, 23, 9); }
    polygon(ctx, palette.dark, [[45, 42], [54, 33], [76, 33], [86, 43], [86, 65], [76, 75], [53, 75], [43, 64]]);
    polygon(ctx, palette.base, [[48, 43], [56, 36], [74, 36], [82, 44], [82, 63], [74, 71], [55, 71], [47, 62]]);
    ctx.fillStyle = palette.light; ctx.fillRect(55, 42, 20, 3); ctx.fillRect(52, 47, 3, 13);
    ctx.fillStyle = palette.accent;
    if (kind === "seal") {
      polygon(ctx, palette.accent, [[65, 45], [75, 54], [65, 64], [55, 54]]);
      ctx.fillStyle = palette.dark; ctx.fillRect(62, 51, 6, 6);
    } else if (variant % 2) {
      polygon(ctx, palette.accent, [[65, 45], [75, 54], [65, 64], [55, 54]]);
      ctx.fillStyle = palette.dark; ctx.fillRect(62, 51, 6, 6);
    } else {
      ctx.fillRect(57, 48, 16, 3); ctx.fillRect(60, 54, 10, 3); ctx.fillRect(63, 60, 4, 3);
    }
    return;
  }
  if (kind === "weapon") {
    polygon(ctx, palette.light, [[29, 69], [35, 70], [95, 24], [100, 15], [91, 20]]);
    polygon(ctx, palette.base, [[35, 66], [91, 24], [97, 18], [88, 27]]);
    ctx.fillStyle = palette.dark; ctx.fillRect(26, 63, 26, 5); ctx.fillRect(31, 68, 7, 16);
    return;
  }
  if (kind === "tool") {
    ctx.fillStyle = palette.dark; ctx.fillRect(58, 35, 8, 48);
    ctx.fillStyle = palette.shade; ctx.fillRect(61, 39, 6, 42);
    polygon(ctx, palette.base, [[31, 25], [85, 20], [99, 32], [84, 41], [32, 37]]);
    ctx.fillStyle = palette.light; ctx.fillRect(36, 26, 46, 3);
    return;
  }
  if (kind === "vessel") {
    polygon(ctx, palette.dark, [[42, 23], [86, 23], [91, 37], [85, 75], [75, 82], [51, 82], [41, 72], [36, 37]]);
    polygon(ctx, palette.base, [[45, 27], [83, 27], [87, 39], [81, 72], [73, 78], [53, 78], [45, 70], [40, 39]]);
    ctx.fillStyle = palette.light; ctx.fillRect(48, 31, 28, 4); ctx.fillRect(46, 39, 5, 26);
    ctx.fillStyle = palette.accent; ctx.fillRect(43, 48, 42, 4); ctx.fillRect(46, 62, 36, 3);
    return;
  }
  const points = kind === "icon"
    ? [[41, 18], [87, 18], [94, 75], [78, 81], [35, 72]]
    : kind === "model"
    ? [[29, 65], [43, 35], [61, 49], [76, 22], [100, 67], [84, 78], [47, 75]]
    : [[27, 33], [56, 17], [101, 29], [91, 70], [61, 81], [24, 64]];
  polygon(ctx, palette.dark, points.map(([x, y]) => [x + 2, y + 3]));
  polygon(ctx, palette.base, points);
  ctx.fillStyle = palette.light; ctx.fillRect(42, 30, 34, 4);
  ctx.fillStyle = palette.accent; ctx.fillRect(48, 42, 5, 20); ctx.fillRect(62, 38, 4, 27); ctx.fillRect(76, 45, 4, 15);
}

function drawSite(ctx: CanvasRenderingContext2D, profile: ItemVisualProfile, palette: Palette) {
  if (profile.kind === "layer") {
    const colors = [palette.dark, palette.shade, palette.base, palette.accent, palette.light];
    colors.forEach((color, index) => { ctx.fillStyle = color; ctx.fillRect(17, 26 + index * 10, 94, 10); });
    ctx.fillStyle = "#222d27"; ctx.fillRect(30, 39, 7, 3); ctx.fillRect(72, 57, 10, 3); ctx.fillRect(91, 68, 6, 3);
    return;
  }
  ctx.fillStyle = "#171f1a"; ctx.fillRect(15, 76, 99, 8);
  if (profile.kind === "monument") {
    polygon(ctx, palette.dark, [[41, 74], [45, 17], [84, 17], [91, 74]]);
    polygon(ctx, palette.base, [[46, 72], [49, 21], [80, 21], [86, 72]]);
    ctx.fillStyle = palette.light; ctx.fillRect(52, 25, 23, 3);
    ctx.fillStyle = palette.accent; ctx.fillRect(55, 37, 19, 3); ctx.fillRect(53, 46, 23, 3); ctx.fillRect(57, 55, 16, 3);
  } else {
    polygon(ctx, palette.dark, [[19, 75], [27, 39], [46, 28], [58, 51], [72, 25], [103, 40], [111, 76]]);
    polygon(ctx, palette.base, [[24, 73], [31, 43], [44, 34], [57, 58], [74, 31], [98, 43], [105, 73]]);
    ctx.fillStyle = palette.shade; ctx.fillRect(34, 50, 15, 23); ctx.fillRect(78, 46, 16, 27);
  }
}

function applyDamage(ctx: CanvasRenderingContext2D, profile: ItemVisualProfile, palette: Palette, random: () => number) {
  for (const damage of profile.damage) {
    if (damage === "water") {
      ctx.fillStyle = "rgba(64, 105, 111, .48)";
      ctx.fillRect(45, 34, 31, 7); ctx.fillRect(55, 41, 29, 5); ctx.fillRect(65, 46, 15, 4);
    } else if (damage === "holes") {
      ctx.fillStyle = "#273029";
      for (let i = 0; i < 8; i++) ctx.fillRect(34 + Math.floor(random() * 57), 25 + Math.floor(random() * 45), 2 + Math.floor(random() * 3), 2 + Math.floor(random() * 2));
    } else if (damage === "charred") {
      ctx.fillStyle = "#302820"; ctx.fillRect(26, 66, 15, 7); ctx.fillRect(34, 72, 47, 6); ctx.fillRect(82, 67, 14, 7);
    } else if (damage === "cracked") {
      ctx.strokeStyle = palette.dark; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(69, 21); ctx.lineTo(63, 37); ctx.lineTo(72, 48); ctx.lineTo(64, 67); ctx.stroke();
    } else if (damage === "rust") {
      ctx.fillStyle = "#9a5331";
      for (let i = 0; i < 11; i++) ctx.fillRect(35 + Math.floor(random() * 58), 25 + Math.floor(random() * 45), 3, 2);
    } else if (damage === "torn") {
      ctx.fillStyle = "#263129"; ctx.fillRect(25, 52, 10, 12); ctx.fillRect(92, 28, 9, 10);
    } else if (damage === "soil") {
      ctx.fillStyle = "rgba(91, 68, 43, .72)";
      for (let i = 0; i < 14; i++) ctx.fillRect(23 + Math.floor(random() * 82), 57 + Math.floor(random() * 20), 3 + Math.floor(random() * 5), 2);
    } else if (damage === "faded") {
      ctx.fillStyle = "rgba(225, 218, 183, .25)"; ctx.fillRect(36, 29, 52, 32);
    }
  }
}

export default function ItemPixelArt({ profile, label }: { profile: ItemVisualProfile; label: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#263129"; ctx.fillRect(0, 0, 128, 96);
    ctx.fillStyle = "#2d3931";
    for (let x = 0; x < 128; x += 8) ctx.fillRect(x, 0, 1, 96);
    for (let y = 0; y < 96; y += 8) ctx.fillRect(0, y, 128, 1);
    ctx.fillStyle = "#1a221d"; ctx.fillRect(12, 82, 104, 4);
    const palette = PALETTES[profile.material] ?? PALETTES.stone;
    if (["codex", "scroll", "sheet", "tablet"].includes(profile.kind)) drawDocument(ctx, profile, palette);
    else if (["monument", "ruins", "layer"].includes(profile.kind)) drawSite(ctx, profile, palette);
    else drawArtifact(ctx, profile, palette);
    applyDamage(ctx, profile, palette, seededRandom(profile.seed));
  }, [profile]);
  return (
    <figure className="item-pixel-figure">
      <canvas ref={canvasRef} width={128} height={96} role="img" aria-label={`${label}的像素外观`} />
      <figcaption><span>现场外观记录</span><strong>{label}</strong></figcaption>
    </figure>
  );
}
