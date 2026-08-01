import { useEffect, useRef } from "react";
import Phaser from "phaser";
import type { LocalMap, MapEntity, RuntimeState } from "./types";

const TILE_SIZE = 32;
const TILE_COLORS = [
  "#55735a", "#9b927d", "#c6c2b5", "#48504c", "#376d86",
  "#676861", "#755f48", "#846a4b", "#b7a47f", "#c19a72",
  "#c5ad72", "#355f43", "#6f746d", "#7f8c52", "#8c7350",
  "#aeb5aa", "#526f61",
  "#55735a",
];

type Props = {
  map: LocalMap;
  runtime: RuntimeState;
  selectedId: string | null;
  onSelect: (entity: MapEntity) => void;
  onNearby: (entityIds: string[]) => void;
  onInteract: (entity: MapEntity | null) => void;
  onMove: (dx: number, dy: number) => Promise<RuntimeState | null>;
};

type SceneCallbacks = Pick<Props, "onSelect" | "onNearby" | "onInteract" | "onMove">;

type WeatherParticle = {
  x: number;
  y: number;
  speed: number;
  drift: number;
  size: number;
};

class SettlementScene extends Phaser.Scene {
  private mapData: LocalMap;
  private callbacks: SceneCallbacks;
  private player!: Phaser.GameObjects.Container;
  private playerGrid: { x: number; y: number };
  private moving = false;
  private markers = new Map<string, Phaser.GameObjects.Container>();
  private entityPositions = new Map<string, { x: number; y: number }>();
  private initialRuntime: RuntimeState;
  private runtimeTurn: number;
  private visibilityLayer?: Phaser.GameObjects.Graphics;
  private weatherLayer?: Phaser.GameObjects.Graphics;
  private weatherParticles: WeatherParticle[] = [];
  private weather: RuntimeState["environment"]["weather"] = "clear";
  private selectedId: string | null = null;
  private cursors?: Phaser.Types.Input.Keyboard.CursorKeys;
  private keys?: Record<string, Phaser.Input.Keyboard.Key>;

  constructor(map: LocalMap, runtime: RuntimeState, callbacks: SceneCallbacks) {
    super("settlement");
    this.mapData = map;
    this.callbacks = callbacks;
    this.initialRuntime = runtime;
    this.playerGrid = { ...runtime.player };
    this.runtimeTurn = runtime.turn;
    map.entities.forEach((entity) => {
      this.entityPositions.set(entity.id, { x: entity.x, y: entity.y });
    });
    runtime.npcs.forEach((npc) => {
      this.entityPositions.set(npc.id, { x: npc.x, y: npc.y });
    });
  }

  create() {
    this.drawMap();
    this.drawDecorations();
    this.drawBuildings();
    this.drawEntities();
    this.player = this.createPlayer(
      this.playerGrid.x * TILE_SIZE + TILE_SIZE / 2,
      this.playerGrid.y * TILE_SIZE + TILE_SIZE / 2,
    );
    this.visibilityLayer = this.add.graphics().setDepth(20);
    this.weatherLayer = this.add.graphics().setDepth(21);
    this.renderEnvironment(this.initialRuntime);
    this.cameras.main.setBounds(
      0,
      0,
      this.mapData.width * TILE_SIZE,
      this.mapData.height * TILE_SIZE,
    );
    this.cameras.main.startFollow(this.player, true, 0.28, 0.28);
    this.cameras.main.setZoom(1.05);
    this.cursors = this.input.keyboard?.createCursorKeys();
    this.keys = this.input.keyboard?.addKeys("W,A,S,D,E,SPACE") as Record<
      string,
      Phaser.Input.Keyboard.Key
    >;
    window.addEventListener("hf-move", this.handleMoveEvent as EventListener);
    window.addEventListener("hf-interact", this.handleInteractEvent);
    window.addEventListener("hf-select", this.handleSelectEvent as EventListener);
    window.addEventListener("hf-runtime", this.handleRuntimeEvent as EventListener);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener("hf-move", this.handleMoveEvent as EventListener);
      window.removeEventListener("hf-interact", this.handleInteractEvent);
      window.removeEventListener("hf-select", this.handleSelectEvent as EventListener);
      window.removeEventListener("hf-runtime", this.handleRuntimeEvent as EventListener);
    });
    this.emitNearby();
  }

  update(_time: number, delta: number) {
    this.updateWeather(delta);
    if (this.moving || !this.cursors || !this.keys) return;
    const just = Phaser.Input.Keyboard.JustDown;
    if (just(this.cursors.left) || just(this.keys.A)) this.tryMove(-1, 0);
    else if (just(this.cursors.right) || just(this.keys.D)) this.tryMove(1, 0);
    else if (just(this.cursors.up) || just(this.keys.W)) this.tryMove(0, -1);
    else if (just(this.cursors.down) || just(this.keys.S)) this.tryMove(0, 1);
    else if (just(this.keys.E) || just(this.keys.SPACE)) this.interact();
  }

  private drawMap() {
    const texture = this.textures.createCanvas(
      "terrain-atlas",
      TILE_COLORS.length * TILE_SIZE,
      TILE_SIZE,
    );
    if (texture) {
      const context = texture.context;
      context.imageSmoothingEnabled = false;
      TILE_COLORS.forEach((_, tile) => {
        this.drawTerrainTile(
          context, tile, tile * 7, tile * 11,
          tile * TILE_SIZE, 0,
        );
      });
      texture.refresh();
      const data = Array.from(
        { length: this.mapData.height },
        (_, y) => this.mapData.tiles.slice(
          y * this.mapData.width,
          (y + 1) * this.mapData.width,
        ),
      );
      const tilemap = this.make.tilemap({
        data,
        tileWidth: TILE_SIZE,
        tileHeight: TILE_SIZE,
      });
      const tileset = tilemap.addTilesetImage(
        "terrain", texture.key, TILE_SIZE, TILE_SIZE, 0, 0, 0,
      );
      if (tileset) {
        tilemap.createLayer(0, tileset, 0, 0)?.setDepth(0).setCullPadding(2, 2);
      }
    }
    this.mapData.zones.forEach((zone) => {
      if (zone.show_label === false) return;
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

  private drawTerrainTile(
    context: CanvasRenderingContext2D,
    tile: number,
    mapX: number,
    mapY: number,
    px: number,
    py: number,
  ) {
    context.fillStyle = TILE_COLORS[tile] ?? "#4d6653";
    context.fillRect(px, py, TILE_SIZE, TILE_SIZE);
    context.strokeStyle = tile === 2
      ? "rgba(23, 33, 28, .08)"
      : "rgba(23, 33, 28, .12)";
    context.lineWidth = 1;
    context.strokeRect(px + 0.5, py + 0.5, TILE_SIZE - 1, TILE_SIZE - 1);

    if (tile === 0 && (mapX * 17 + mapY * 31) % 7 === 0) {
      this.fillCircle(context, px + 8, py + 9, 2, "rgba(120, 145, 110, .8)");
      this.fillCircle(context, px + 12, py + 6, 1.5, "rgba(120, 145, 110, .8)");
    } else if (tile === 1 && (mapX + mapY) % 3 === 0) {
      this.fillCircle(context, px + 9, py + 20, 1.3, "rgba(181, 170, 145, .5)");
      this.fillCircle(context, px + 23, py + 10, 1.1, "rgba(181, 170, 145, .5)");
    } else if (tile === 4) {
      context.strokeStyle = "rgba(112, 164, 183, .5)";
      context.beginPath();
      context.moveTo(px + 4, py + 10);
      context.lineTo(px + 24, py + 10);
      context.moveTo(px + 10, py + 22);
      context.lineTo(px + 29, py + 22);
      context.stroke();
    } else if (tile === 6) {
      context.fillStyle = "rgba(157, 123, 81, .8)";
      for (const row of [5, 14, 23]) context.fillRect(px + 5, py + row, 22, 4);
    } else if (tile === 10) {
      this.fillCircle(context, px + 8, py + 8, 1.2, "rgba(216, 200, 148, .55)");
      this.fillCircle(context, px + 23, py + 20, 1.5, "rgba(216, 200, 148, .55)");
    } else if (tile === 11) {
      this.fillTriangle(
        context,
        [px + 16, py + 4], [px + 6, py + 24], [px + 26, py + 24],
        "rgba(36, 76, 53, .95)",
      );
      context.fillStyle = "rgba(107, 76, 50, .9)";
      context.fillRect(px + 14, py + 23, 4, 7);
    } else if (tile === 12) {
      this.fillTriangle(
        context,
        [px + 5, py + 24], [px + 13, py + 7], [px + 22, py + 25],
        "rgba(146, 151, 142, .9)",
      );
      this.fillTriangle(
        context,
        [px + 15, py + 25], [px + 23, py + 12], [px + 29, py + 26],
        "rgba(146, 151, 142, .9)",
      );
    } else if (tile === 13 || tile === 14) {
      context.strokeStyle = tile === 13
        ? "rgba(169, 166, 95, .75)"
        : "rgba(82, 54, 33, .95)";
      context.lineWidth = 2;
      context.beginPath();
      const start = tile === 13 ? 6 : 4;
      const step = tile === 13 ? 7 : 6;
      for (let row = start; row < TILE_SIZE; row += step) {
        context.moveTo(px + 3, py + row);
        context.lineTo(px + 29, py + row);
      }
      context.stroke();
      if (tile === 14) {
        context.fillStyle = "rgba(49, 35, 24, .95)";
        context.fillRect(px + 2, py + 2, 3, TILE_SIZE - 4);
        context.fillRect(px + TILE_SIZE - 5, py + 2, 3, TILE_SIZE - 4);
        this.fillCircle(context, px + 8, py + 7, 1.5, "#d6b16f");
        this.fillCircle(context, px + 24, py + 25, 1.5, "#d6b16f");
      }
    } else if (tile === 15) {
      context.fillStyle = "rgba(226, 232, 224, .55)";
      context.fillRect(px + 6, py + 7, 3, 2);
      context.fillRect(px + 20, py + 21, 5, 2);
    } else if (tile === 16) {
      context.strokeStyle = "rgba(132, 166, 151, .7)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(px + 3, py + 24);
      context.lineTo(px + 28, py + 24);
      context.moveTo(px + 10, py + 25);
      context.lineTo(px + 8, py + 13);
      context.moveTo(px + 19, py + 25);
      context.lineTo(px + 22, py + 11);
      context.stroke();
    } else if (tile === 17) {
      context.strokeStyle = "rgba(116, 91, 57, .95)";
      context.lineWidth = 3;
      context.beginPath();
      context.moveTo(px + 3, py + 10);
      context.lineTo(px + 29, py + 10);
      context.moveTo(px + 3, py + 23);
      context.lineTo(px + 29, py + 23);
      for (const post of [6, 16, 26]) {
        context.moveTo(px + post, py + 3);
        context.lineTo(px + post, py + 29);
      }
      context.stroke();
    }
  }

  private drawDecorations() {
    this.mapData.decorations.forEach((decoration) => {
      const detail = this.add.graphics()
        .setPosition(
          decoration.x * TILE_SIZE + TILE_SIZE / 2,
          decoration.y * TILE_SIZE + TILE_SIZE / 2,
        )
        .setScale(decoration.scale)
        .setDepth(1);
      const subtype = decoration.subtype;
      if (["grass_tuft", "dry_grass", "pale_grass", "water_grass", "reeds"].includes(subtype)) {
        const color = subtype === "reeds" || subtype === "water_grass"
          ? 0x6f8c63 : subtype === "pale_grass" ? 0xaab29d
            : subtype === "dry_grass" ? 0xa79463 : 0x78935d;
        detail.lineStyle(subtype === "reeds" ? 2 : 1.4, color, 0.9);
        for (const offset of [-6, -2, 3, 7]) {
          const height = 6 + ((decoration.variant + offset + 8) % 5);
          detail.lineBetween(offset, 8, offset - 2, 8 - height);
        }
      } else if (["wildflowers", "heather", "mushroom", "leaf_patch", "lichen"].includes(subtype)) {
        const colors = subtype === "wildflowers"
          ? [0xd6b85e, 0xc87572, 0xe3ddd0]
          : subtype === "heather" ? [0x9c7895, 0xb18a9f]
            : subtype === "mushroom" ? [0xc8b28a, 0xa56f52]
              : [0x829668, 0xa1aa7b];
        for (let index = 0; index < 5; index += 1) {
          detail.fillStyle(colors[(index + decoration.variant) % colors.length], 0.9);
          detail.fillCircle(-7 + index * 3.5, 3 - (index % 2) * 4, subtype === "mushroom" ? 2 : 1.5);
        }
      } else if (["stone_cluster", "river_stone", "small_stone"].includes(subtype)) {
        const color = subtype === "river_stone" ? 0x809398 : 0x898d84;
        detail.fillStyle(color, 0.85);
        detail.fillEllipse(-4, 4, 11, 7);
        detail.fillEllipse(5, 5, 9, 6);
        if (subtype === "stone_cluster") detail.fillEllipse(1, -1, 8, 8);
      } else if (["fallen_branch", "driftwood", "dead_branch", "bleached_branch"].includes(subtype)) {
        const color = subtype === "bleached_branch" ? 0xb4aa8f : 0x70543b;
        detail.lineStyle(2.5, color, 0.9);
        detail.lineBetween(-10, 6, 10, -4);
        detail.lineBetween(-2, 2, -7, -5);
        detail.lineBetween(4, -1, 9, 3);
      } else {
        const color = ["dry_shrub", "thorn_bush", "desert_grass"].includes(subtype)
          ? 0x8d8053 : subtype === "willow_shoot" ? 0x668b61 : 0x587b50;
        detail.fillStyle(color, 0.72);
        detail.fillCircle(-5, 3, 6);
        detail.fillCircle(2, 0, 8);
        detail.fillCircle(8, 4, 5);
        detail.lineStyle(1.2, 0x405b3d, 0.8);
        detail.lineBetween(0, 7, 0, -7);
      }
    });
  }

  private fillCircle(
    context: CanvasRenderingContext2D,
    x: number,
    y: number,
    radius: number,
    color: string,
  ) {
    context.fillStyle = color;
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
  }

  private fillTriangle(
    context: CanvasRenderingContext2D,
    first: [number, number],
    second: [number, number],
    third: [number, number],
    color: string,
  ) {
    context.fillStyle = color;
    context.beginPath();
    context.moveTo(first[0], first[1]);
    context.lineTo(second[0], second[1]);
    context.lineTo(third[0], third[1]);
    context.closePath();
    context.fill();
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
      if (building.building_type === "cemetery") {
        const cemetery = this.add.graphics().setDepth(3);
        cemetery.lineStyle(
          3, building.condition === "ruined" ? 0x625f57 : 0x929087, 0.95,
        );
        cemetery.strokeRect(
          left * TILE_SIZE + 4,
          top * TILE_SIZE + 4,
          (right - left + 1) * TILE_SIZE - 8,
          (bottom - top + 1) * TILE_SIZE - 8,
        );
        this.add.text(
          (left + 1) * TILE_SIZE,
          (top + 1) * TILE_SIZE,
          building.name,
          {
            fontFamily: '"Microsoft YaHei", sans-serif',
            fontSize: "10px",
            color: "#f0eee6",
            backgroundColor: "rgba(54,58,54,0.78)",
            padding: { x: 4, y: 2 },
          },
        ).setDepth(5);
        return;
      }
      const doorX = building.door.x * TILE_SIZE;
      const doorY = building.door.y * TILE_SIZE;
      const detail = this.add.graphics().setDepth(4);
      const damaged = building.condition === "damaged";
      const ruined = building.condition === "ruined";
      detail.fillStyle(ruined ? 0x514b42 : damaged ? 0x76583f : 0x5f3f2d, 1);
      detail.fillRect(doorX + 10, doorY + 10, 12, 18);

      if (building.building_type === "home") {
        detail.fillStyle(0x725747, 0.85);
        detail.fillRect((left + 1) * TILE_SIZE + 7, (top + 1) * TILE_SIZE + 7, 11, 11);
        detail.lineStyle(2, 0xe0c48c, 0.55);
        detail.strokeRect((right - 1) * TILE_SIZE + 7, (bottom - 1) * TILE_SIZE + 7, 14, 10);
      } else if ([
        "inn", "bakery", "granary", "library", "great_market",
        "fortification", "aqueduct", "palace", "temple",
        "roadside_inn", "tollhouse", "farmstead", "mine",
        "logging_camp", "watchtower", "battlefield_ruins",
        "burned_waystation", "disaster_ruins", "abandoned_hamlet",
        "ruined_outpost",
      ].includes(building.building_type)) {
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

      if (building.infrastructure_type && (damaged || ruined)) {
        detail.lineStyle(3, ruined ? 0x342f2a : 0x806a52, 0.95);
        const startX = (left + 1) * TILE_SIZE;
        const startY = (top + 1) * TILE_SIZE;
        detail.lineBetween(startX, startY, startX + 18, startY + 13);
        detail.lineBetween(startX + 18, startY + 2, startX + 5, startY + 20);
      }
    });
  }

  private drawEntities() {
    this.mapData.entities.forEach((entity) => {
      const position = this.entityPositions.get(entity.id) ?? entity;
      const x = position.x * TILE_SIZE + TILE_SIZE / 2;
      const y = position.y * TILE_SIZE + TILE_SIZE / 2;
      const marker = this.add.container(x, y).setDepth(8);
      const shadow = this.add.ellipse(0, 11, 22, 8, 0x18201c, 0.28);
      const shape = this.add.graphics();
      if (entity.kind === "landmark") {
        if (entity.subtype === "sacred_shrine") {
          shape.fillStyle(0x77766d, 1);
          shape.fillRect(-12, 2, 24, 10);
          shape.fillStyle(0xa6a28f, 1);
          shape.fillRect(-8, -10, 16, 14);
          shape.lineStyle(2, 0xd1b86f, 0.9);
          shape.strokeCircle(0, -3, 5);
          shape.fillStyle(0x65809a, 0.9);
          shape.fillCircle(-6, 8, 3);
        } else if (entity.subtype === "temple_altar") {
          shape.fillStyle(0x8d887d, 1);
          shape.fillRect(-14, -6, 28, 16);
          shape.fillStyle(0xc4b77f, 1);
          shape.fillRect(-10, -10, 20, 5);
          shape.lineStyle(2, 0x5f645d, 1);
          shape.strokeCircle(0, 1, 5);
        } else if (entity.subtype === "offering_table") {
          shape.fillStyle(0x79583d, 1);
          shape.fillRect(-14, -5, 28, 8);
          shape.fillRect(-10, 3, 4, 11);
          shape.fillRect(6, 3, 4, 11);
          shape.fillStyle(0xd4bc72, 1);
          shape.fillCircle(-5, -7, 3);
          shape.fillStyle(0x7493a2, 1);
          shape.fillCircle(5, -7, 3);
        } else if (entity.subtype === "votive_wall") {
          shape.fillStyle(0x89877e, 1);
          shape.fillRect(-15, -14, 30, 27);
          shape.lineStyle(1.5, 0xc7b77d, 0.85);
          shape.lineBetween(-9, -8, 8, -8);
          shape.lineBetween(-7, -2, 10, -2);
          shape.lineBetween(-10, 5, 5, 5);
        } else {
          const signColor = entity.wear_level === "heavy"
          ? 0x8f7650
          : entity.wear_level === "moderate" ? 0xad9161 : 0xc8ad73;
        shape.lineStyle(4, 0x5f432d, 1);
        shape.lineBetween(0, -16, 0, 15);
        shape.fillStyle(signColor, 1);
        shape.fillTriangle(-13, -13, 13, -13, 8, -4);
        shape.lineStyle(1.5, 0x4b3928, 1);
        shape.strokeTriangle(-13, -13, 13, -13, 8, -4);
        if (entity.wear_level !== "light") {
          shape.lineStyle(1.2, 0x66513a, 0.85);
          shape.lineBetween(-8, -11, -2, -6);
          if (entity.wear_level === "heavy") {
            shape.lineBetween(4, -12, 8, -7);
          }
        }
        if (entity.repair_type === "iron_strap") {
          shape.fillStyle(0x777b74, 0.95);
          shape.fillRect(-2, -16, 4, 10);
        } else if (entity.repair_type === "replacement_board") {
          shape.fillStyle(0xd8be83, 0.95);
          shape.fillRect(2, -12, 7, 4);
          shape.fillStyle(0x4b3928, 1);
          shape.fillCircle(4, -10, 1);
        } else if (entity.repair_type === "rope_binding") {
          shape.lineStyle(1.5, 0xc1a16d, 1);
          for (const repairY of [-5, -2, 1]) {
            shape.lineBetween(-4, repairY, 4, repairY + 1);
          }
        } else if (entity.repair_type === "fresh_paint") {
          shape.lineStyle(2, 0xb76532, 1);
          shape.lineBetween(-7, -9, 6, -9);
          shape.lineBetween(6, -9, 2, -12);
          shape.lineBetween(6, -9, 2, -6);
        }
        }
      } else if (entity.kind === "camp") {
        const component = entity.component_type ?? entity.subtype;
        if (component.includes("tent")) {
          const collapsed = component.includes("collapsed");
          shape.fillStyle(collapsed ? 0x71695b : component.includes("large") ? 0xb8874d : 0x9f7650, 1);
          shape.fillTriangle(0, collapsed ? -5 : -15, 14, 12, -14, 12);
          shape.lineStyle(2, 0x463628, 1);
          shape.strokeTriangle(0, collapsed ? -5 : -15, 14, 12, -14, 12);
          shape.lineBetween(0, collapsed ? -5 : -15, 0, 12);
          if (!collapsed) {
            shape.lineStyle(1.5, 0xd8c69f, 0.9);
            shape.lineBetween(-14, 12, -18, 15);
            shape.lineBetween(14, 12, 18, 15);
          }
        } else if (component.includes("campfire")) {
          const burning = component === "campfire_burning";
          const embers = component === "campfire_embers";
          shape.fillStyle(0x71685a, 1);
          for (const [stoneX, stoneY] of [[-7, 0], [-4, -5], [2, -6], [7, -1], [5, 5], [-3, 6]]) {
            shape.fillCircle(stoneX, stoneY, 3);
          }
          shape.lineStyle(3, 0x493426, 1);
          shape.lineBetween(-6, 5, 6, -4);
          shape.lineBetween(-6, -4, 6, 5);
          shape.fillStyle(burning ? 0xe56532 : embers ? 0xa4422c : 0x343331, burning ? 0.95 : 0.65);
          shape.fillCircle(0, 0, burning ? 5 : 3);
          if (burning) {
            shape.fillStyle(0xf4b447, 0.95);
            shape.fillTriangle(-3, 2, 1, -10, 5, 2);
          }
        } else if (component === "camp_wagon") {
          shape.fillStyle(0x8b6848, 1);
          shape.fillRoundedRect(-14, -6, 25, 15, 2);
          shape.fillStyle(0xd0bb83, 1);
          shape.fillTriangle(-12, -6, 9, -6, -2, -17);
          shape.fillStyle(0x363a35, 1);
          shape.fillCircle(-8, 11, 4);
          shape.fillCircle(7, 11, 4);
        } else if (["camp_supplies", "camp_crate_broken"].includes(component)) {
          shape.fillStyle(component.includes("broken") ? 0x72553d : 0x9a7048, 1);
          shape.fillRect(-11, -8, 22, 17);
          shape.lineStyle(2, 0x4b3728, 1);
          shape.strokeRect(-11, -8, 22, 17);
          shape.lineBetween(-10, -7, 10, 8);
          if (component.includes("broken")) shape.lineBetween(-11, 3, 2, -8);
        } else if (component === "camp_tether") {
          shape.lineStyle(4, 0x654a32, 1);
          shape.lineBetween(-8, -10, -8, 10);
          shape.lineBetween(8, -10, 8, 10);
          shape.lineStyle(2, 0xb89460, 1);
          shape.lineBetween(-8, -5, 8, 1);
        } else if (component === "camp_bedroll") {
          shape.fillStyle(0x837158, 1);
          shape.fillRoundedRect(-13, -6, 26, 12, 5);
          shape.lineStyle(2, 0x4d4336, 1);
          shape.lineBetween(-5, -6, -5, 6);
        } else {
          const ruts = component === "camp_ruts" || component === "camp_tracks";
          shape.lineStyle(2, ruts ? 0x725d43 : 0x555049, 0.75);
          shape.lineBetween(-13, -6, 13, ruts ? -2 : 6);
          shape.lineBetween(-13, 3, 13, ruts ? 7 : -3);
          if (!ruts) shape.strokeCircle(0, 0, 8);
        }
      } else if (entity.kind === "caravan") {
        shape.fillStyle(0x8b6848, 1);
        shape.fillRoundedRect(-15, -7, 26, 17, 3);
        shape.fillStyle(0xd0bb83, 1);
        shape.fillTriangle(-13, -7, 8, -7, -2, -19);
        shape.fillStyle(0x363a35, 1);
        shape.fillCircle(-9, 12, 4);
        shape.fillCircle(7, 12, 4);
        shape.lineStyle(2, 0x49392b, 1);
        shape.lineBetween(11, 0, 18, -6);
      } else if (entity.kind === "traveler") {
        const clothing = entity.subtype === "pilgrim" ? 0x7f6f95
          : entity.subtype === "courier" ? 0x557b8b
            : entity.subtype === "peddler" ? 0x8a6847 : 0x7c765f;
        shape.fillStyle(0xd6b98a, 1);
        shape.fillCircle(0, -7, 5);
        shape.fillStyle(clothing, 1);
        shape.fillRoundedRect(-7, -1, 14, 16, 2);
        shape.lineStyle(2, 0x4b3928, 0.9);
        shape.lineBetween(-3, 14, -5, 20);
        shape.lineBetween(3, 14, 6, 20);
        if (entity.subtype === "pilgrim") {
          shape.lineStyle(2, 0xc8ad73, 1);
          shape.lineBetween(9, -10, 9, 20);
          shape.fillCircle(9, -12, 2);
        } else if (entity.subtype === "peddler") {
          shape.fillStyle(0x9b794f, 1);
          shape.fillRoundedRect(6, 0, 9, 11, 2);
        }
      } else if (entity.kind === "trace") {
        shape.fillStyle(0x7d6248, 0.82);
        if (entity.subtype === "broken_wheel") {
          shape.lineStyle(3, 0x75583e, 1);
          shape.strokeCircle(0, 0, 11);
          shape.lineBetween(-8, -8, 8, 8);
          shape.lineBetween(-8, 8, 8, -8);
        } else if (entity.subtype === "old_fire_ring" || entity.subtype === "charcoal_patch") {
          shape.fillStyle(0x4f4940, 0.8);
          shape.fillEllipse(0, 5, 25, 14);
          shape.lineStyle(2, 0x8c806d, 0.9);
          shape.strokeEllipse(0, 5, 26, 15);
        } else if (entity.subtype === "stone_cairn") {
          shape.fillStyle(0x85877f, 1);
          shape.fillEllipse(0, 8, 22, 8);
          shape.fillEllipse(0, 2, 16, 8);
          shape.fillEllipse(0, -4, 10, 7);
        } else {
          shape.lineStyle(3, 0x75583e, 0.9);
          shape.lineBetween(-13, 7, 13, 1);
          shape.lineBetween(-12, 12, 14, 6);
          shape.fillCircle(-8, 5, 2);
          shape.fillCircle(9, 4, 2);
        }
      } else if (entity.kind === "wildlife") {
        const wildlifeColor = ["deer", "mountain_goat", "fox"].includes(entity.subtype)
          ? 0x9a7650 : ["heron", "waterfowl", "ptarmigan"].includes(entity.subtype)
            ? 0xc6c8b8 : entity.subtype === "lizard" ? 0x70865c : 0xa98d68;
        shape.fillStyle(wildlifeColor, 1);
        shape.fillEllipse(0, 2, entity.subtype === "lizard" ? 18 : 16, entity.subtype === "lizard" ? 6 : 10);
        shape.fillCircle(8, -2, 4);
        shape.lineStyle(2, 0x493d31, 0.9);
        if (entity.subtype === "deer" || entity.subtype === "mountain_goat") {
          shape.lineBetween(7, -5, 5, -11);
          shape.lineBetween(9, -5, 12, -11);
        } else if (entity.subtype === "heron") {
          shape.lineBetween(5, 1, 9, -12);
        } else if (entity.subtype === "lizard") {
          shape.lineBetween(-8, 2, -15, 6);
        }
      } else if (entity.kind === "informant") {
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
      } else if (entity.kind === "container") {
        const muted = entity.searched ? 0x718276 : 0x8c6745;
        if (["bookshelf", "ledger_shelf"].includes(entity.placement_kind ?? "")) {
          shape.fillStyle(muted, 1);
          shape.fillRect(-11, -14, 22, 28);
          shape.lineStyle(2, 0x34291f, 1);
          shape.strokeRect(-11, -14, 22, 28);
          shape.lineBetween(-10, -5, 10, -5);
          shape.lineBetween(-10, 5, 10, 5);
          [0xb84f45, 0x617b8b, 0xd0ae62, 0x5f7c62].forEach((color, index) => {
            shape.fillStyle(color, 1);
            shape.fillRect(-8 + index * 5, -12, 3, 6 + (index % 2) * 2);
          });
        } else if (entity.placement_kind === "archive_cabinet") {
          shape.fillStyle(muted, 1);
          shape.fillRoundedRect(-10, -14, 20, 28, 2);
          shape.lineStyle(2, 0x34291f, 1);
          shape.strokeRoundedRect(-10, -14, 20, 28, 2);
          shape.lineBetween(-9, -5, 9, -5);
          shape.lineBetween(-9, 5, 9, 5);
          shape.fillStyle(0xd2bd8b, 1);
          shape.fillCircle(0, -9, 1.5);
          shape.fillCircle(0, 0, 1.5);
          shape.fillCircle(0, 9, 1.5);
        } else if (entity.placement_kind === "tool_rack") {
          shape.lineStyle(3, muted, 1);
          shape.strokeRect(-11, -13, 22, 26);
          shape.lineStyle(2, 0xa5afb0, 1);
          shape.lineBetween(-6, -9, -6, 8);
          shape.lineBetween(1, -9, 5, 8);
          shape.lineBetween(7, -9, 4, -1);
        } else if (["excavation", "debris_search"].includes(entity.placement_kind ?? "")) {
          shape.fillStyle(0x80694c, 0.7);
          shape.fillRect(-13, -10, 26, 20);
          shape.lineStyle(2, 0xe0c991, 1);
          shape.strokeRect(-13, -10, 26, 20);
          shape.lineBetween(-13, 0, 13, 0);
          shape.lineBetween(0, -10, 0, 10);
        } else {
          shape.fillStyle(muted, 1);
          shape.fillRoundedRect(-11, -8, 22, 17, 2);
          shape.lineStyle(2, 0x3f3428, 1);
          shape.strokeRoundedRect(-11, -8, 22, 17, 2);
          shape.lineBetween(-11, -2, 11, -2);
          if (entity.placement_kind === "scroll_chest") {
            shape.fillStyle(0xe1d5b4, 1);
            shape.fillCircle(-4, 2, 3);
            shape.fillCircle(4, 2, 3);
          } else {
            shape.fillStyle(0xd7c091, 1);
            shape.fillRect(-2, -4, 4, 6);
          }
        }
      } else if (["grave_marker", "ruler_tomb"].includes(entity.subtype)) {
        const ruined = entity.state === "ruined" || entity.state === "buried";
        shape.fillStyle(ruined ? 0x6f706a : 0x9a9b92, 1);
        shape.fillRoundedRect(-9, -15, 18, 28, 3);
        shape.fillStyle(0x77786f, 1);
        shape.fillRect(-13, 10, 26, 6);
        shape.lineStyle(1.5, 0x4b504d, 0.95);
        shape.lineBetween(-5, -7, 5, -7);
        shape.lineBetween(-5, -2, 4, -2);
        shape.lineBetween(-5, 3, 6, 3);
        if (ruined) {
          shape.lineStyle(2, 0x50534f, 1);
          shape.lineBetween(-8, -4, 5, 8);
        }
      } else if (entity.placement_kind === "structural") {
        shape.fillStyle(0x85877f, 1);
        shape.fillRect(-13, -4, 11, 16);
        shape.fillRect(-1, -12, 13, 24);
        shape.lineStyle(2, 0x454a46, 1);
        shape.strokeRect(-13, -4, 11, 16);
        shape.strokeRect(-1, -12, 13, 24);
      } else if (entity.placement_kind === "stratigraphic") {
        shape.fillStyle(0x8d7253, 0.85);
        shape.fillEllipse(0, 3, 28, 18);
        shape.lineStyle(2, 0x3f3428, 1);
        shape.strokeEllipse(0, 3, 28, 18);
        shape.lineStyle(2, 0x4d3b2c, 1);
        shape.lineBetween(-10, 1, 10, 1);
        shape.lineStyle(2, 0xb6a071, 1);
        shape.lineBetween(-8, 6, 8, 6);
      } else if (entity.placement_kind === "stone_display") {
        shape.fillStyle(0x8d9088, 1);
        shape.fillRoundedRect(-10, -14, 20, 28, 2);
        shape.lineStyle(2, 0x474c48, 1);
        shape.strokeRoundedRect(-10, -14, 20, 28, 2);
        shape.lineBetween(-6, -7, 6, -7);
        shape.lineBetween(-6, -1, 5, -1);
        shape.lineBetween(-6, 5, 7, 5);
      } else if (["ground_object", "ground_scatter"].includes(entity.placement_kind ?? "")) {
        shape.fillStyle(entity.material === "metal" ? 0x8fa1a3 : 0x8a6747, 1);
        shape.fillTriangle(-12, 7, -3, -7, 2, 8);
        shape.fillTriangle(1, 8, 7, -4, 12, 7);
        shape.lineStyle(1.5, 0x303733, 1);
        shape.lineBetween(-12, 8, 12, 8);
      } else if (entity.placement_kind === "floor_object") {
        shape.fillStyle(0x8b6d4e, 1);
        shape.fillEllipse(0, -9, 13, 6);
        shape.fillRoundedRect(-9, -8, 18, 22, 6);
        shape.lineStyle(2, 0x403329, 1);
        shape.strokeRoundedRect(-9, -8, 18, 22, 6);
      } else if (entity.placement_kind === "workbench_display") {
        shape.fillStyle(0x76543b, 1);
        shape.fillRect(-13, 3, 26, 7);
        shape.fillRect(-10, 9, 4, 8);
        shape.fillRect(6, 9, 4, 8);
        shape.fillStyle(0xa5afb0, 1);
        shape.fillTriangle(0, -11, 9, 3, -9, 3);
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
    });
  }

  private createPlayer(x: number, y: number) {
    const container = this.add.container(x, y).setDepth(22);
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

  private async tryMove(dx: number, dy: number) {
    const x = this.playerGrid.x + dx;
    const y = this.playerGrid.y + dy;
    if (!this.isWalkable(x, y)) return;
    this.moving = true;
    const runtime = await this.callbacks.onMove(dx, dy);
    if (!runtime || runtime.turn <= this.runtimeTurn) {
      this.moving = false;
      return;
    }
    this.applyRuntime(runtime);
  }

  private isWalkable(x: number, y: number) {
    if (x < 0 || y < 0 || x >= this.mapData.width || y >= this.mapData.height) {
      return true;
    }
    const tile = this.mapData.tiles[y * this.mapData.width + x];
    if (this.mapData.blocking_tiles.includes(tile)) return false;
    return !this.mapData.entities.some((entity) => {
      const position = this.entityPositions.get(entity.id) ?? entity;
      const blocks = ["informant", "resident"].includes(entity.kind)
        || entity.blocks_movement !== false;
      return blocks && position.x === x && position.y === y;
    });
  }

  private nearbyEntities() {
    return this.mapData.entities.filter((entity) => {
      const position = this.entityPositions.get(entity.id) ?? entity;
      return Math.abs(position.x - this.playerGrid.x) +
        Math.abs(position.y - this.playerGrid.y) <= 1;
    });
  }

  private applyRuntime(runtime: RuntimeState) {
    if (runtime.turn <= this.runtimeTurn) {
      return;
    }
    this.runtimeTurn = runtime.turn;
    this.playerGrid = { ...runtime.player };
    this.tweens.add({
      targets: this.player,
      x: runtime.player.x * TILE_SIZE + TILE_SIZE / 2,
      y: runtime.player.y * TILE_SIZE + TILE_SIZE / 2,
      duration: 125,
      ease: "Sine.easeOut",
      onComplete: () => {
        this.moving = false;
        this.emitNearby();
      },
    });
    runtime.npcs.forEach((npc) => {
      const previous = this.entityPositions.get(npc.id);
      this.entityPositions.set(npc.id, { x: npc.x, y: npc.y });
      const marker = this.markers.get(npc.id);
      if (!marker || (previous?.x === npc.x && previous?.y === npc.y)) return;
      this.tweens.killTweensOf(marker);
      this.tweens.add({
        targets: marker,
        x: npc.x * TILE_SIZE + TILE_SIZE / 2,
        y: npc.y * TILE_SIZE + TILE_SIZE / 2,
        duration: 170,
        ease: "Sine.easeInOut",
      });
    });
    this.renderEnvironment(runtime);
  }

  private renderEnvironment(runtime: RuntimeState) {
    if (!this.visibilityLayer) return;
    const visible = new Set(
      runtime.visible_tiles.map((tile) => `${tile.x},${tile.y}`),
    );
    const explored = new Set(
      runtime.explored_tiles.map((tile) => `${tile.x},${tile.y}`),
    );
    const visibleDarkness = (1 - runtime.environment.light_level) * 0.42;
    this.visibilityLayer.clear();
    for (let y = 0; y < this.mapData.height; y += 1) {
      for (let x = 0; x < this.mapData.width; x += 1) {
        const key = `${x},${y}`;
        if (visible.has(key)) {
          if (visibleDarkness > 0) {
            this.visibilityLayer.fillStyle(0x111c24, visibleDarkness);
            this.visibilityLayer.fillRect(
              x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE,
            );
          }
          continue;
        }
        this.visibilityLayer.fillStyle(
          explored.has(key) ? 0x111815 : 0x080c0a,
          explored.has(key) ? 0.62 : 0.97,
        );
        this.visibilityLayer.fillRect(
          x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE,
        );
      }
    }
    this.markers.forEach((marker, id) => {
      const position = this.entityPositions.get(id);
      marker.setVisible(Boolean(
        position && visible.has(`${position.x},${position.y}`),
      ));
    });
    if (this.weather !== runtime.environment.weather) {
      this.weather = runtime.environment.weather;
      this.resetWeatherParticles();
    }
  }

  private resetWeatherParticles() {
    const width = this.mapData.width * TILE_SIZE;
    const height = this.mapData.height * TILE_SIZE;
    if (["clear", "cloudy"].includes(this.weather)) {
      this.weatherParticles = [];
      this.weatherLayer?.clear();
      return;
    }
    const density = this.weather === "fog" ? 15000 : 7000;
    const count = Phaser.Math.Clamp(Math.round(width * height / density), 90, 480);
    this.weatherParticles = Array.from({ length: count }, () => ({
      x: Phaser.Math.Between(0, width),
      y: Phaser.Math.Between(0, height),
      speed: Phaser.Math.Between(35, this.weather === "storm" ? 280 : 150),
      drift: Phaser.Math.Between(-18, 34),
      size: Phaser.Math.FloatBetween(1, 3.2),
    }));
  }

  private updateWeather(delta: number) {
    if (!this.weatherLayer || this.weatherParticles.length === 0) return;
    const width = this.mapData.width * TILE_SIZE;
    const height = this.mapData.height * TILE_SIZE;
    const elapsed = Math.min(delta, 50) / 1000;
    this.weatherLayer.clear();
    if (this.weather === "rain" || this.weather === "storm") {
      this.weatherLayer.lineStyle(
        this.weather === "storm" ? 1.5 : 1,
        0xb8cad0,
        this.weather === "storm" ? 0.52 : 0.34,
      );
    }
    for (const particle of this.weatherParticles) {
      if (this.weather === "fog") {
        particle.x += particle.drift * elapsed;
        if (particle.x > width + 100) particle.x = -100;
        if (particle.x < -100) particle.x = width + 100;
        this.weatherLayer.fillStyle(0xd8dfdc, 0.035);
        this.weatherLayer.fillRect(
          particle.x, particle.y, particle.size * 28, particle.size * 2.5,
        );
      } else if (this.weather === "snow") {
        particle.y += particle.speed * 0.35 * elapsed;
        particle.x += Math.sin(particle.y * 0.02) * 8 * elapsed;
        if (particle.y > height) particle.y = 0;
        this.weatherLayer.fillStyle(0xf0f3ee, 0.68);
        this.weatherLayer.fillCircle(particle.x, particle.y, particle.size);
      } else if (this.weather === "dust") {
        particle.x += (particle.speed + 45) * elapsed;
        particle.y += particle.drift * 0.18 * elapsed;
        if (particle.x > width) particle.x = 0;
        if (particle.y > height) particle.y = 0;
        if (particle.y < 0) particle.y = height;
        this.weatherLayer.lineStyle(1.2, 0xc2a56e, 0.28);
        this.weatherLayer.lineBetween(
          particle.x, particle.y, particle.x + particle.size * 6, particle.y + 1,
        );
      } else {
        const storm = this.weather === "storm";
        particle.y += particle.speed * elapsed;
        particle.x += (storm ? 60 : 22) * elapsed;
        if (particle.y > height) particle.y = 0;
        if (particle.x > width) particle.x = 0;
        this.weatherLayer.lineBetween(
          particle.x,
          particle.y,
          particle.x + (storm ? 8 : 4),
          particle.y + particle.size * (storm ? 9 : 6),
        );
      }
    }
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
    if (!this.moving) void this.tryMove(event.detail.dx, event.detail.dy);
  };

  private handleInteractEvent = () => this.interact();

  private handleSelectEvent = (event: CustomEvent<{ id: string | null }>) => {
    this.setSelected(event.detail.id);
  };

  private handleRuntimeEvent = (event: CustomEvent<RuntimeState>) => {
    this.applyRuntime(event.detail);
  };
}

export default function GameCanvas({ map, runtime, selectedId, onSelect, onNearby, onInteract, onMove }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const callbacksRef = useRef({ onSelect, onNearby, onInteract, onMove });
  callbacksRef.current = { onSelect, onNearby, onInteract, onMove };

  useEffect(() => {
    if (!hostRef.current) return;
    const scene = new SettlementScene(map, runtime, {
      onSelect: (entity) => callbacksRef.current.onSelect(entity),
      onNearby: (ids) => callbacksRef.current.onNearby(ids),
      onInteract: (entity) => callbacksRef.current.onInteract(entity),
      onMove: (dx, dy) => callbacksRef.current.onMove(dx, dy),
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

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("hf-runtime", { detail: runtime }));
  }, [runtime]);

  return <div ref={hostRef} className="game-canvas" aria-label="本地格子地图" />;
}
