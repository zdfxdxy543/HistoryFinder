export type MapEntity = {
  id: string;
  kind: "evidence" | "container" | "informant" | "resident";
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
  accessibility?: string;
  condition?: string;
  searched?: boolean;
  discovered_count?: number;
  container_id?: string;
  storage_position?: string;
  placement_kind?: string;
  storage_site_id?: string;
  blocks_movement?: boolean;
  can_read?: boolean;
  quick_read?: boolean;
};

export type LocalBuilding = {
  id: string;
  name: string;
  building_type: string;
  bounds: number[];
  door: { x: number; y: number };
};

export type LocalMap = {
  site_type: "settlement" | "ruin";
  width: number;
  height: number;
  profile: {
    layout_type: string;
    layout_name: string;
    water_axis: string;
    water_side: string;
    hub: { x: number; y: number };
    entrances: string[];
    landscape_type: string;
    landscape_name: string;
  };
  tiles: number[];
  blocking_tiles: number[];
  player_start: { x: number; y: number };
  entities: MapEntity[];
  discovered_evidence: MapEntity[];
  buildings: LocalBuilding[];
  zones: Array<{ id: string; name: string; bounds: number[]; show_label?: boolean }>;
};

export type WorldLocation = {
  id: string;
  name: string;
  x: number;
  y: number;
  site_type: "settlement" | "ruin";
  size: string;
  biome: string;
  polity_code: number | null;
};

export type WorldPolity = {
  code: number;
  name: string;
};

export type WorldMapState = {
  width: number;
  height: number;
  terrain: number[][];
  biome_codes: Record<string, number>;
  territory: {
    unclaimed_code: number;
    owners: number[][];
    polities: WorldPolity[];
  };
  locations: WorldLocation[];
  current_location_id: string;
};

export type NpcRuntime = {
  id: string;
  kind: "informant" | "resident";
  x: number;
  y: number;
  activity: string;
  activity_name: string;
};

export type RuntimeState = {
  day: number;
  minute_of_day: number;
  time_label: string;
  period_name: string;
  turn: number;
  player: { x: number; y: number };
  environment: {
    daylight: "dawn" | "day" | "dusk" | "night" | "late_night";
    daylight_name: string;
    light_level: number;
    weather: "clear" | "cloudy" | "rain" | "storm" | "fog" | "snow" | "dust";
    weather_name: string;
    visibility_radius: number;
  };
  visible_tiles: Array<{ x: number; y: number }>;
  explored_tiles: Array<{ x: number; y: number }>;
  npcs: NpcRuntime[];
};

export type Informant = {
  id: string;
  name: string;
  role: string;
  role_name: string;
  base_role_name: string;
  public_status: "resident" | "visitor" | "survivor" | "captive";
  public_role_name: string;
  claimed_origin_name: string;
  origin_knowledge_status: "unknown" | "self_reported" | "documented" | "corroborated";
  presence_label: string;
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
  runtime: RuntimeState;
  world_map: WorldMapState;
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
  runtime?: RuntimeState;
  moved?: boolean;
  minutes?: number;
  elapsed_minutes?: number;
  location?: Pick<PlayerState, "settlement" | "local_map" | "runtime" | "informants">;
  world_map?: WorldMapState;
  origin?: { id: string; name: string };
  destination?: { id: string; name: string; site_type: "settlement" | "ruin" };
  container?: Record<string, unknown>;
  discovered_evidence?: MapEntity[];
  local_map?: LocalMap;
  newly_discovered_count?: number;
};
