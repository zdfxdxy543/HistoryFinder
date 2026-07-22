import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import {
  Building2,
  Flag,
  Landmark,
  MapPin,
  Maximize2,
  Navigation,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
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

const POLITY_COLORS = [
  "#c84f45", "#3f78b5", "#4f8a5b", "#c49336",
  "#7b61a8", "#2f8f91", "#b05a83", "#70823f",
  "#d27735", "#5b6f91", "#8a6248", "#4882a0",
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

const MIN_ZOOM = 1;
const MAX_ZOOM = 6;
const ZOOM_STEP = 0.25;

type MapView = {
  zoom: number;
  x: number;
  y: number;
};

export default function WorldMapView({ map, busy, onTravel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const draggedRef = useRef(false);
  const [selectedId, setSelectedId] = useState(map.current_location_id);
  const [showTerritories, setShowTerritories] = useState(false);
  const [fitSize, setFitSize] = useState({ width: 1, height: 1 });
  const [view, setView] = useState<MapView>({ zoom: 1, x: 0, y: 0 });
  const selected = map.locations.find((item) => item.id === selectedId) ?? null;
  const current = map.locations.find((item) => item.id === map.current_location_id) ?? null;
  const polityByCode = useMemo(
    () => new Map(map.territory.polities.map((item) => [item.code, item])),
    [map.territory.polities],
  );

  useEffect(() => setSelectedId(map.current_location_id), [map.current_location_id]);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const fitMap = () => {
      const availableWidth = viewport.clientWidth;
      const availableHeight = viewport.clientHeight;
      const ratio = map.width / map.height;
      let width = Math.min(availableWidth, 1100);
      let height = width / ratio;
      if (height > availableHeight) {
        height = availableHeight;
        width = height * ratio;
      }
      setFitSize({
        width: Math.max(1, Math.floor(width)),
        height: Math.max(1, Math.floor(height)),
      });
    };
    fitMap();
    const observer = new ResizeObserver(fitMap);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [map.width, map.height]);

  useEffect(() => {
    setView((current) => constrainView(current, fitSize, viewportRef.current));
  }, [fitSize]);

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
    if (showTerritories) {
      map.territory.owners.forEach((row, y) => {
        row.forEach((code, x) => {
          if (code === map.territory.unclaimed_code) return;
          const color = polityColor(code);
          context.fillStyle = `${color}78`;
          context.fillRect(x * scale, y * scale, scale, scale);
          context.fillStyle = color;
          if (x === 0 || row[x - 1] !== code) context.fillRect(x * scale, y * scale, 1, scale);
          if (x === map.width - 1 || row[x + 1] !== code) context.fillRect((x + 1) * scale - 1, y * scale, 1, scale);
          if (y === 0 || map.territory.owners[y - 1][x] !== code) context.fillRect(x * scale, y * scale, scale, 1);
          if (y === map.height - 1 || map.territory.owners[y + 1][x] !== code) context.fillRect(x * scale, (y + 1) * scale - 1, scale, 1);
        });
      });
    }
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
  }, [map, showTerritories]);

  const travelMinutes = useMemo(() => {
    if (!current || !selected) return 0;
    return Math.max(60, Math.ceil(distance(current, selected) * 45 / 5) * 5);
  }, [current, selected]);

  const changeZoom = (nextZoom: number, anchor?: { x: number; y: number }) => {
    setView((current) => {
      const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
      if (zoom === current.zoom) return current;
      let x = current.x;
      let y = current.y;
      const viewport = viewportRef.current;
      if (anchor && viewport) {
        const centerX = viewport.clientWidth / 2;
        const centerY = viewport.clientHeight / 2;
        const factor = zoom / current.zoom;
        x = anchor.x - centerX - (anchor.x - centerX - current.x) * factor;
        y = anchor.y - centerY - (anchor.y - centerY - current.y) * factor;
      }
      return constrainView({ zoom, x, y }, fitSize, viewport);
    });
  };

  const resetView = () => setView({ zoom: 1, x: 0, y: 0 });

  const onWheel = (event: WheelEvent) => {
    event.preventDefault();
    const viewport = viewportRef.current;
    if (!viewport) return;
    const bounds = viewport.getBoundingClientRect();
    const factor = Math.exp(-event.deltaY * 0.0015);
    changeZoom(view.zoom * factor, {
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    });
  };

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    viewport.addEventListener("wheel", onWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", onWheel);
  }, [view.zoom, fitSize]);

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (view.zoom <= MIN_ZOOM || (event.target as HTMLElement).closest("button")) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: view.x,
      originY: view.y,
    };
    draggedRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const x = drag.originX + event.clientX - drag.startX;
    const y = drag.originY + event.clientY - drag.startY;
    if (Math.abs(event.clientX - drag.startX) + Math.abs(event.clientY - drag.startY) > 3) {
      draggedRef.current = true;
    }
    setView((current) => constrainView(
      { zoom: current.zoom, x, y }, fitSize, viewportRef.current,
    ));
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    event.currentTarget.releasePointerCapture(event.pointerId);
  };

  return (
    <section className="world-workspace">
      <div className="world-map-pane">
        <div className="world-map-toolbar">
          <button
            className={`world-territory-toggle ${showTerritories ? "active" : ""}`}
            aria-pressed={showTerritories}
            onClick={() => setShowTerritories((visible) => !visible)}
          >
            <Flag size={14} />国家疆域
          </button>
          <div className="world-zoom-controls" aria-label="地图缩放">
            <button title="缩小地图" aria-label="缩小地图" disabled={view.zoom <= MIN_ZOOM} onClick={() => changeZoom(view.zoom - ZOOM_STEP)}>
              <ZoomOut size={15} />
            </button>
            <span>{Math.round(view.zoom * 100)}%</span>
            <button title="放大地图" aria-label="放大地图" disabled={view.zoom >= MAX_ZOOM} onClick={() => changeZoom(view.zoom + ZOOM_STEP)}>
              <ZoomIn size={15} />
            </button>
            <button title="恢复完整地图" aria-label="恢复完整地图" disabled={view.zoom === 1 && view.x === 0 && view.y === 0} onClick={resetView}>
              <Maximize2 size={14} />
            </button>
          </div>
        </div>
        <div
          ref={viewportRef}
          className={`world-map-viewport ${view.zoom > 1 ? "zoomed" : ""}`}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onClickCapture={(event) => {
            if (!draggedRef.current) return;
            event.preventDefault();
            event.stopPropagation();
            draggedRef.current = false;
          }}
        >
          <div
            className="world-map-surface"
            style={{
              width: fitSize.width,
              height: fitSize.height,
              transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`,
            }}
          >
            <canvas ref={canvasRef} />
            {map.locations.map((location) => {
              const isCurrent = location.id === map.current_location_id;
              const active = location.id === selectedId;
              return (
                <button
                  className={`world-marker ${location.site_type} ${active ? "active" : ""} ${isCurrent ? "current" : ""}`}
                  key={location.id}
                  style={{
                    left: `${((location.x + 0.5) / map.width) * 100}%`,
                    top: `${((location.y + 0.5) / map.height) * 100}%`,
                    transform: `translate(-50%, -50%) scale(${1 / view.zoom})`,
                  }}
                  title={`${location.name} · ${polityName(location.polity_code, polityByCode)}`}
                  onClick={() => setSelectedId(location.id)}
                >
                  {location.site_type === "ruin" ? <Landmark size={16} /> : <Building2 size={16} />}
                  <span>{location.name}</span>
                </button>
              );
            })}
          </div>
        </div>
        <div className={`world-map-legend ${showTerritories ? "polity" : ""}`}>
          {!showTerritories ? (
            <>
              <span><i className="location-swatch settlement" />现存聚落</span>
              <span><i className="location-swatch ruin" />废墟</span>
              <span><MapPin size={13} />当前位置</span>
            </>
          ) : (
            <>
              {map.territory.polities.map((polity) => (
                <span key={polity.code}><i className="polity-swatch" style={{ background: polityColor(polity.code) }} />{polity.name}</span>
              ))}
              <span><i className="polity-swatch unclaimed" />无主地</span>
            </>
          )}
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
              {` · ${polityName(selected.polity_code, polityByCode)}`}
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
              <span>
                <strong>{location.name}</strong>
                <small>{location.site_type === "ruin" ? "废墟" : SIZE_NAMES[location.size] ?? location.size} · {polityName(location.polity_code, polityByCode)}</small>
              </span>
            </button>
          ))}
        </div>
      </aside>
    </section>
  );
}

function polityColor(code: number) {
  return POLITY_COLORS[code % POLITY_COLORS.length];
}

function polityName(code: number | null, polities: Map<number, { name: string }>) {
  return code == null ? "无主地" : polities.get(code)?.name ?? "无主地";
}

function constrainView(
  view: MapView,
  fitSize: { width: number; height: number },
  viewport: HTMLDivElement | null,
): MapView {
  if (!viewport || view.zoom <= MIN_ZOOM) return { zoom: view.zoom, x: 0, y: 0 };
  const maxX = Math.max(0, (fitSize.width * view.zoom - viewport.clientWidth) / 2);
  const maxY = Math.max(0, (fitSize.height * view.zoom - viewport.clientHeight) / 2);
  return {
    zoom: view.zoom,
    x: Math.min(maxX, Math.max(-maxX, view.x)),
    y: Math.min(maxY, Math.max(-maxY, view.y)),
  };
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
