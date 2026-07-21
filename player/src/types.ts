export type MapEntity = {
  id: string;
  kind: "evidence" | "informant" | "resident";
  x: number;
  y: number;
  name: string;
  subtype: string;
  role: string;
  role_name: string;
  state: string;
  material: string;
  zone: string;
  description_cn: string;
  dialogue_cn: string;
};

export type LocalBuilding = {
  id: string;
  name: string;
  building_type: string;
  bounds: number[];
  door: { x: number; y: number };
};

export type LocalMap = {
  width: number;
  height: number;
  tiles: number[];
  blocking_tiles: number[];
  player_start: { x: number; y: number };
  entities: MapEntity[];
  buildings: LocalBuilding[];
  zones: Array<{ id: string; name: string; bounds: number[] }>;
};

export type Informant = {
  id: string;
  name: string;
  role: string;
  role_name: string;
};

export type Journal = {
  counts: Record<string, number>;
  evidence_names: Record<string, string>;
  observations: Array<Record<string, unknown>>;
  readings: Array<Record<string, unknown>>;
  statements: Array<Record<string, unknown>>;
  claims: Array<Record<string, unknown>>;
  conflicts: Array<Record<string, unknown>>;
  comparisons: Array<Record<string, unknown>>;
};

export type PlayerState = {
  mode: "player_safe";
  world: { seed: number; name: string; current_year: number };
  settlement: {
    id: string;
    name: string;
    size: string;
    biome: string;
    population: number;
    alive: boolean;
  };
  local_map: LocalMap;
  informants: Informant[];
  journal: Journal;
};

export type ActionResult = {
  action: string;
  journal?: Journal;
  evidence?: Record<string, unknown> | Array<Record<string, unknown>>;
  description_cn?: string;
  text_cn?: string;
  observations?: Array<Record<string, unknown>>;
  reading?: Record<string, unknown>;
  consultation?: Record<string, unknown>;
  consultant?: Informant;
  resident?: Record<string, unknown>;
  dialogue_cn?: string;
  comparison?: Record<string, unknown>;
  learned_claims?: Array<Record<string, unknown>>;
};
