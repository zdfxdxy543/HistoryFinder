import { useEffect, useRef } from "react";
import Phaser from "phaser";
import type { LocalMap, MapEntity } from "./types";

const TILE_SIZE = 32;

type Props = {
  map: LocalMap;
  selectedId: string | null;
  onSelect: (entity: MapEntity) => void;
  onNearby: (entityIds: string[]) => void;
  onInteract: (entity: MapEntity | null) => void;
};

type SceneCallbacks = Pick<Props, "onSelect" | "onNearby" | "onInteract">;

class SettlementScene extends Phaser.Scene {
  private mapData: LocalMap;
  private callbacks: SceneCallbacks;
  private player!: Phaser.GameObjects.Container;
  private playerGrid: { x: number; y: number };
  private moving = false;
  private markers = new Map<string, Phaser.GameObjects.Container>();
  private selectedId: string | null = null;
  private cursors?: Phaser.Types.Input.Keyboard.CursorKeys;
  private keys?: Record<string, Phaser.Input.Keyboard.Key>;

  constructor(map: LocalMap, callbacks: SceneCallbacks) {
    super("settlement");
    this.mapData = map;
    this.callbacks = callbacks;
    this.playerGrid = { ...map.player_start };
  }

  create() {
    this.drawMap();
    this.drawBuildings();
    this.drawEntities();
    this.player = this.createPlayer(
      this.playerGrid.x * TILE_SIZE + TILE_SIZE / 2,
      this.playerGrid.y * TILE_SIZE + TILE_SIZE / 2,
    );
    this.cameras.main.setBounds(
      0,
      0,
      this.mapData.width * TILE_SIZE,
      this.mapData.height * TILE_SIZE,
    );
    this.cameras.main.startFollow(this.player, true, 0.12, 0.12);
    this.cameras.main.setZoom(1.05);
    this.cursors = this.input.keyboard?.createCursorKeys();
    this.keys = this.input.keyboard?.addKeys("W,A,S,D,E,SPACE") as Record<
      string,
      Phaser.Input.Keyboard.Key
    >;
    window.addEventListener("hf-move", this.handleMoveEvent as EventListener);
    window.addEventListener("hf-interact", this.handleInteractEvent);
    window.addEventListener("hf-select", this.handleSelectEvent as EventListener);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener("hf-move", this.handleMoveEvent as EventListener);
      window.removeEventListener("hf-interact", this.handleInteractEvent);
      window.removeEventListener("hf-select", this.handleSelectEvent as EventListener);
    });
    this.emitNearby();
  }

  update() {
    if (this.moving || !this.cursors || !this.keys) return;
    const just = Phaser.Input.Keyboard.JustDown;
    if (just(this.cursors.left) || just(this.keys.A)) this.tryMove(-1, 0);
    else if (just(this.cursors.right) || just(this.keys.D)) this.tryMove(1, 0);
    else if (just(this.cursors.up) || just(this.keys.W)) this.tryMove(0, -1);
    else if (just(this.cursors.down) || just(this.keys.S)) this.tryMove(0, 1);
    else if (just(this.keys.E) || just(this.keys.SPACE)) this.interact();
  }

  private drawMap() {
    const graphics = this.add.graphics();
    const colors = [
      0x55735a,
      0x9b927d,
      0xc6c2b5,
      0x48504c,
      0x376d86,
      0x676861,
      0x755f48,
      0x846a4b,
      0xb7a47f,
      0xc19a72,
    ];
    for (let y = 0; y < this.mapData.height; y += 1) {
      for (let x = 0; x < this.mapData.width; x += 1) {
        const tile = this.mapData.tiles[y * this.mapData.width + x];
        const px = x * TILE_SIZE;
        const py = y * TILE_SIZE;
        graphics.fillStyle(colors[tile] ?? 0x4d6653, 1);
        graphics.fillRect(px, py, TILE_SIZE, TILE_SIZE);
        graphics.lineStyle(1, 0x17211c, tile === 2 ? 0.08 : 0.12);
        graphics.strokeRect(px, py, TILE_SIZE, TILE_SIZE);
        if (tile === 0 && (x * 17 + y * 31) % 7 === 0) {
          graphics.fillStyle(0x78916e, 0.8);
          graphics.fillCircle(px + 8, py + 9, 2);
          graphics.fillCircle(px + 12, py + 6, 1.5);
        } else if (tile === 1 && (x + y) % 3 === 0) {
          graphics.fillStyle(0xb5aa91, 0.5);
          graphics.fillCircle(px + 9, py + 20, 1.3);
          graphics.fillCircle(px + 23, py + 10, 1.1);
        } else if (tile === 4) {
          graphics.lineStyle(1, 0x70a4b7, 0.5);
          graphics.lineBetween(px + 4, py + 10, px + 24, py + 10);
          graphics.lineBetween(px + 10, py + 22, px + 29, py + 22);
        } else if (tile === 6) {
          graphics.fillStyle(0x9d7b51, 0.8);
          graphics.fillRect(px + 5, py + 5, 22, 4);
          graphics.fillRect(px + 5, py + 14, 22, 4);
          graphics.fillRect(px + 5, py + 23, 22, 4);
        }
      }
    }
    this.mapData.zones.forEach((zone) => {
      if (zone.id === "services") return;
      const [left, top] = zone.bounds;
      this.add
        .text(left * TILE_SIZE + 8, top * TILE_SIZE + 7, zone.name, {
          fontFamily: '"Microsoft YaHei", sans-serif',
          fontSize: "11px",
          color: "#eef2ed",
          backgroundColor: "rgba(23,30,26,0.70)",
          padding: { x: 5, y: 3 },
        })
        .setDepth(3);
    });
  }

  private drawBuildings() {
    this.mapData.buildings.forEach((building) => {
      const [left, top, right, bottom] = building.bounds;
      if (building.building_type === "well") {
        const well = this.add.graphics().setDepth(5);
        const centerX = left * TILE_SIZE + TILE_SIZE / 2;
        const centerY = top * TILE_SIZE + TILE_SIZE / 2;
        well.fillStyle(0x4f7480, 1);
        well.fillCircle(centerX, centerY, 10);
        well.lineStyle(4, 0x8b8170, 1);
        well.strokeCircle(centerX, centerY, 12);
        return;
      }
      const doorX = building.door.x * TILE_SIZE;
      const doorY = building.door.y * TILE_SIZE;
      const detail = this.add.graphics().setDepth(4);
      detail.fillStyle(0x5f3f2d, 1);
      detail.fillRect(doorX + 10, doorY + 10, 12, 18);

      if (building.building_type === "home") {
        detail.fillStyle(0x725747, 0.85);
        detail.fillRect((left + 1) * TILE_SIZE + 7, (top + 1) * TILE_SIZE + 7, 11, 11);
        detail.lineStyle(2, 0xe0c48c, 0.55);
        detail.strokeRect((right - 1) * TILE_SIZE + 7, (bottom - 1) * TILE_SIZE + 7, 14, 10);
      } else if (["inn", "bakery", "granary"].includes(building.building_type)) {
        this.add
          .text((left + 1) * TILE_SIZE, (top + 1) * TILE_SIZE, building.name, {
            fontFamily: '"Microsoft YaHei", sans-serif',
            fontSize: "10px",
            color: "#fff7e8",
            backgroundColor: "rgba(72,45,31,0.78)",
            padding: { x: 4, y: 2 },
          })
          .setDepth(5);
      }
    });
  }

  private drawEntities() {
    this.mapData.entities.forEach((entity) => {
      const x = entity.x * TILE_SIZE + TILE_SIZE / 2;
      const y = entity.y * TILE_SIZE + TILE_SIZE / 2;
      const marker = this.add.container(x, y).setDepth(8);
      const shadow = this.add.ellipse(0, 11, 22, 8, 0x18201c, 0.28);
      const shape = this.add.graphics();
      if (entity.kind === "informant") {
        shape.fillStyle(0xd0b26e, 1);
        shape.fillCircle(0, -7, 6);
        shape.fillStyle(0x324f47, 1);
        shape.fillRoundedRect(-8, -1, 16, 18, 3);
        shape.lineStyle(2, 0xe6d59f, 0.9);
        shape.strokeRoundedRect(-8, -1, 16, 18, 3);
      } else if (entity.kind === "resident") {
        const residentColors: Record<string, number> = {
          farmer: 0x718653,
          weaver: 0x6f6688,
          porter: 0x7b6a55,
          baker: 0xa27852,
          vendor: 0x4f7b72,
          water_carrier: 0x557b8b,
          carpenter: 0x87634b,
          inn_worker: 0x8a5960,
          laborer: 0x6d736b,
        };
        shape.fillStyle(0xd6b98a, 1);
        shape.fillCircle(0, -6, 5);
        shape.fillStyle(residentColors[entity.role] ?? 0x6d736b, 1);
        shape.fillRoundedRect(-7, 0, 14, 15, 2);
        shape.lineStyle(1.5, 0x26312b, 0.85);
        shape.strokeRoundedRect(-7, 0, 14, 15, 2);
      } else if (entity.subtype === "document") {
        shape.fillStyle(0xe1d5b4, 1);
        shape.fillRoundedRect(-10, -10, 20, 20, 2);
        shape.lineStyle(2, 0x745b3b, 1);
        shape.strokeRoundedRect(-10, -10, 20, 20, 2);
        shape.lineBetween(-6, -4, 6, -4);
        shape.lineBetween(-6, 1, 4, 1);
        shape.lineBetween(-6, 6, 7, 6);
      } else {
        shape.fillStyle(entity.material === "metal" ? 0x8fa1a3 : 0xb08b62, 1);
        shape.fillTriangle(0, -12, 11, 8, -11, 8);
        shape.lineStyle(2, 0x27322d, 1);
        shape.strokeTriangle(0, -12, 11, 8, -11, 8);
      }
      const ring = this.add.circle(0, 0, 15).setStrokeStyle(2, 0xe5b85c, 0);
      marker.add([shadow, ring, shape]);
      marker.setSize(30, 34).setInteractive({ useHandCursor: true });
      marker.on("pointerdown", () => {
        this.setSelected(entity.id);
        this.callbacks.onSelect(entity);
      });
      marker.setData("ring", ring);
      this.markers.set(entity.id, marker);
      if (entity.kind === "resident") {
        this.tweens.add({
          targets: marker,
          y: y - 2,
          duration: 900 + (entity.id.length % 5) * 120,
          yoyo: true,
          repeat: -1,
          ease: "Sine.easeInOut",
        });
      }
    });
  }

  private createPlayer(x: number, y: number) {
    const container = this.add.container(x, y).setDepth(12);
    const shadow = this.add.ellipse(0, 11, 22, 8, 0x111814, 0.35);
    const body = this.add.graphics();
    body.fillStyle(0xb6493f, 1);
    body.fillTriangle(0, -9, 10, 12, -10, 12);
    body.fillStyle(0xead3ad, 1);
    body.fillCircle(0, -12, 6);
    body.lineStyle(2, 0x28332d, 1);
    body.strokeCircle(0, -12, 6);
    body.strokeTriangle(0, -9, 10, 12, -10, 12);
    const marker = this.add.triangle(0, -25, 0, 0, 7, 0, 3.5, 7, 0xe5b85c, 1);
    container.add([shadow, body, marker]);
    return container;
  }

  private tryMove(dx: number, dy: number) {
    const x = this.playerGrid.x + dx;
    const y = this.playerGrid.y + dy;
    if (!this.isWalkable(x, y)) return;
    this.moving = true;
    this.playerGrid = { x, y };
    this.tweens.add({
      targets: this.player,
      x: x * TILE_SIZE + TILE_SIZE / 2,
      y: y * TILE_SIZE + TILE_SIZE / 2,
      duration: 105,
      ease: "Sine.easeOut",
      onComplete: () => {
        this.moving = false;
        this.emitNearby();
      },
    });
  }

  private isWalkable(x: number, y: number) {
    if (x < 0 || y < 0 || x >= this.mapData.width || y >= this.mapData.height) {
      return false;
    }
    const tile = this.mapData.tiles[y * this.mapData.width + x];
    if (this.mapData.blocking_tiles.includes(tile)) return false;
    return !this.mapData.entities.some((entity) => entity.x === x && entity.y === y);
  }

  private nearbyEntities() {
    return this.mapData.entities.filter(
      (entity) =>
        Math.abs(entity.x - this.playerGrid.x) +
          Math.abs(entity.y - this.playerGrid.y) <=
        1,
    );
  }

  private emitNearby() {
    this.callbacks.onNearby(this.nearbyEntities().map((item) => item.id));
  }

  private interact() {
    const nearby = this.nearbyEntities();
    const entity = nearby.find((item) => item.id === this.selectedId) ?? nearby[0] ?? null;
    if (entity) {
      this.setSelected(entity.id);
      this.callbacks.onSelect(entity);
    }
    this.callbacks.onInteract(entity);
  }

  private setSelected(id: string | null) {
    this.selectedId = id;
    this.markers.forEach((marker, markerId) => {
      const ring = marker.getData("ring") as Phaser.GameObjects.Arc;
      ring.setStrokeStyle(2, 0xe5b85c, markerId === id ? 1 : 0);
    });
  }

  private handleMoveEvent = (event: CustomEvent<{ dx: number; dy: number }>) => {
    if (!this.moving) this.tryMove(event.detail.dx, event.detail.dy);
  };

  private handleInteractEvent = () => this.interact();

  private handleSelectEvent = (event: CustomEvent<{ id: string | null }>) => {
    this.setSelected(event.detail.id);
  };
}

export default function GameCanvas({ map, selectedId, onSelect, onNearby, onInteract }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const callbacksRef = useRef({ onSelect, onNearby, onInteract });
  callbacksRef.current = { onSelect, onNearby, onInteract };

  useEffect(() => {
    if (!hostRef.current) return;
    const scene = new SettlementScene(map, {
      onSelect: (entity) => callbacksRef.current.onSelect(entity),
      onNearby: (ids) => callbacksRef.current.onNearby(ids),
      onInteract: (entity) => callbacksRef.current.onInteract(entity),
    });
    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: hostRef.current,
      backgroundColor: "#26322b",
      pixelArt: true,
      render: { antialias: false, roundPixels: true },
      scale: { mode: Phaser.Scale.RESIZE, width: "100%", height: "100%" },
      scene,
    });
    return () => game.destroy(true);
  }, [map]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("hf-select", { detail: { id: selectedId } }));
  }, [selectedId]);

  return <div ref={hostRef} className="game-canvas" aria-label="聚落格子地图" />;
}
