import { useEffect, useRef } from "react";
import type { LocalMap, RuntimeState } from "./types";

const TILE_COLORS = [
  0x55735a, 0x9b927d, 0xc6c2b5, 0x48504c, 0x376d86,
  0x676861, 0x755f48, 0x846a4b, 0xb7a47f, 0xc19a72,
  0xc5ad72, 0x355f43, 0x6f746d, 0x7f8c52, 0x8c7350,
  0xaeb5aa, 0x526f61,
];

type Props = {
  map: LocalMap;
  runtime: RuntimeState;
};

export default function LocalMiniMap({ map, runtime }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    canvas.width = map.width;
    canvas.height = map.height;
    context.imageSmoothingEnabled = false;
    const image = context.createImageData(map.width, map.height);
    map.tiles.forEach((tile, index) => {
      const color = TILE_COLORS[tile] ?? TILE_COLORS[0];
      const offset = index * 4;
      image.data[offset] = (color >> 16) & 0xff;
      image.data[offset + 1] = (color >> 8) & 0xff;
      image.data[offset + 2] = color & 0xff;
      image.data[offset + 3] = 0xff;
    });
    context.putImageData(image, 0, 0);

    context.strokeStyle = "rgba(246, 239, 214, .55)";
    context.lineWidth = 1;
    map.buildings.forEach((building) => {
      const [left, top, right, bottom] = building.bounds;
      context.strokeRect(left, top, right - left + 1, bottom - top + 1);
    });

    const visible = new Set(
      runtime.visible_tiles.map((tile) => `${tile.x},${tile.y}`),
    );
    const explored = new Set(
      runtime.explored_tiles.map((tile) => `${tile.x},${tile.y}`),
    );
    for (let y = 0; y < map.height; y += 1) {
      for (let x = 0; x < map.width; x += 1) {
        const key = `${x},${y}`;
        if (visible.has(key)) {
          const darkness = (1 - runtime.environment.light_level) * 0.34;
          if (darkness > 0) {
            context.fillStyle = `rgba(13, 23, 29, ${darkness})`;
            context.fillRect(x, y, 1, 1);
          }
        } else {
          context.fillStyle = explored.has(key)
            ? "rgba(12, 18, 15, .58)"
            : "rgba(7, 11, 9, .96)";
          context.fillRect(x, y, 1, 1);
        }
      }
    }

    const npcPositions = new Map(
      runtime.npcs.map((npc) => [npc.id, { x: npc.x, y: npc.y }]),
    );
    map.entities.forEach((entity) => {
      const position = npcPositions.get(entity.id) ?? entity;
      if (!visible.has(`${position.x},${position.y}`)) return;
      context.fillStyle = entity.kind === "container"
        ? ["excavation", "debris_search"].includes(entity.placement_kind ?? "")
          ? "#a68b64" : "#e0b66e"
        : entity.kind === "evidence"
          ? entity.placement_kind === "structural" ? "#d3d0c4" : "#f1d998"
          : entity.kind === "informant" ? "#d9a84f" : "#c8ddd0";
      context.fillRect(position.x - 1, position.y - 1, 3, 3);
    });
    context.fillStyle = "#d94f45";
    context.fillRect(runtime.player.x - 1, runtime.player.y - 1, 3, 3);
    context.strokeStyle = "#fff7df";
    context.strokeRect(runtime.player.x - 2, runtime.player.y - 2, 5, 5);
  }, [map, runtime]);

  return (
    <figure className="local-minimap" aria-label="当地地图缩略图">
      <figcaption>{map.profile.landscape_name} · {map.profile.layout_name}</figcaption>
      <canvas
        ref={canvasRef}
        style={{ aspectRatio: `${map.width} / ${map.height}` }}
      />
    </figure>
  );
}
