import { useEffect, useMemo, useRef, useState } from "react";
import { Building2, Landmark, MapPin, Navigation } from "lucide-react";
import type { WorldLocation, WorldMapState } from "./types";

type Props = {
  map: WorldMapState;
  busy: boolean;
  onTravel: (destinationId: string) => void;
};

const TERRAIN_COLORS = [
  "#777b73", "#7e897a", "#7b9a71", "#416b4e",
  "#b99a62", "#78a061", "#9da8a2", "#87916b",
  "#91a76d", "#315f73", "#477b91", "#4f8ca0",
];

const SIZE_NAMES: Record<string, string> = {
  village: "村庄",
  town: "城镇",
  city: "城市",
};

const BIOME_NAMES: Record<string, string> = {
  plains: "平原",
  grassland: "草原",
  forest: "森林",
  river_valley: "河谷",
  mountain: "山地",
  highland: "高地",
  desert: "荒漠",
  scrubland: "灌木地",
  tundra: "苔原",
};

export default function WorldMapView({ map, busy, onTravel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [selectedId, setSelectedId] = useState(map.current_location_id);
  const selected = map.locations.find((item) => item.id === selectedId) ?? null;
  const current = map.locations.find((item) => item.id === map.current_location_id) ?? null;

  useEffect(() => setSelectedId(map.current_location_id), [map.current_location_id]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const scale = 8;
    canvas.width = map.width * scale;
    canvas.height = map.height * scale;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.imageSmoothingEnabled = false;
    map.terrain.forEach((row, y) => {
      row.forEach((tile, x) => {
        context.fillStyle = TERRAIN_COLORS[tile] ?? "#84906f";
        context.fillRect(x * scale, y * scale, scale, scale);
      });
    });
    context.strokeStyle = "rgba(79, 65, 47, 0.48)";
    context.lineWidth = 1.5;
    const linked = new Set<string>();
    map.locations.forEach((location) => {
      const nearest = map.locations
        .filter((item) => item.id !== location.id)
        .sort((a, b) => distance(location, a) - distance(location, b))[0];
      if (!nearest) return;
      const key = [location.id, nearest.id].sort().join("|");
      if (linked.has(key)) return;
      linked.add(key);
      context.beginPath();
      context.moveTo((location.x + 0.5) * scale, (location.y + 0.5) * scale);
      context.lineTo((nearest.x + 0.5) * scale, (nearest.y + 0.5) * scale);
      context.stroke();
    });
  }, [map]);

  const travelMinutes = useMemo(() => {
    if (!current || !selected) return 0;
    return Math.max(60, Math.ceil(distance(current, selected) * 45 / 5) * 5);
  }, [current, selected]);

  return (
    <section className="world-workspace">
      <div className="world-map-pane">
        <div className="world-map-surface" style={{ aspectRatio: `${map.width} / ${map.height}` }}>
          <canvas ref={canvasRef} />
          {map.locations.map((location) => {
            const isCurrent = location.id === map.current_location_id;
            const active = location.id === selectedId;
            return (
              <button
                className={`world-marker ${location.site_type} ${active ? "active" : ""} ${isCurrent ? "current" : ""}`}
                key={location.id}
                style={{ left: `${((location.x + 0.5) / map.width) * 100}%`, top: `${((location.y + 0.5) / map.height) * 100}%` }}
                title={location.name}
                onClick={() => setSelectedId(location.id)}
              >
                {location.site_type === "ruin" ? <Landmark size={16} /> : <Building2 size={16} />}
                <span>{location.name}</span>
              </button>
            );
          })}
        </div>
        <div className="world-map-legend">
          <span><i className="location-swatch settlement" />现存聚落</span>
          <span><i className="location-swatch ruin" />废墟</span>
          <span><MapPin size={13} />当前位置</span>
        </div>
      </div>

      <aside className="world-location-panel">
        <header>
          <p>世界地点</p>
          <h2>{selected?.name ?? "选择目的地"}</h2>
          {selected && (
            <span>
              {selected.site_type === "ruin" ? "废墟" : SIZE_NAMES[selected.size] ?? selected.size}
              {` · ${BIOME_NAMES[selected.biome] ?? selected.biome}`}
            </span>
          )}
        </header>
        {selected && selected.id !== map.current_location_id && (
          <div className="travel-command">
            <div><small>预计行程</small><strong>{formatDuration(travelMinutes)}</strong></div>
            <button className="command-button primary" disabled={busy} onClick={() => onTravel(selected.id)}>
              <Navigation size={16} /> 前往
            </button>
          </div>
        )}
        {selected?.id === map.current_location_id && (
          <p className="current-location-note"><MapPin size={15} />你目前位于这里</p>
        )}
        <div className="world-location-list">
          {map.locations.map((location) => (
            <button
              className={location.id === selectedId ? "active" : ""}
              key={location.id}
              onClick={() => setSelectedId(location.id)}
            >
              {location.site_type === "ruin" ? <Landmark size={15} /> : <Building2 size={15} />}
              <span><strong>{location.name}</strong><small>{location.site_type === "ruin" ? "废墟" : SIZE_NAMES[location.size] ?? location.size}</small></span>
            </button>
          ))}
        </div>
      </aside>
    </section>
  );
}

function distance(first: WorldLocation, second: WorldLocation) {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

function formatDuration(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} 分钟`;
  return rest ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`;
}
