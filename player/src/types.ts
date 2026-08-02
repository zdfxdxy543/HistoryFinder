export type MapEntity = {
  id: string;
  kind: "evidence" | "container" | "bookshelf" | "informant" | "resident" | "landmark" | "camp" | "caravan" | "traveler" | "trace" | "wildlife";
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
  shelf_id?: string;
  book_count?: number;
  library_total?: number;
  blocks_movement?: boolean;
  can_read?: boolean;
  quick_read?: boolean;
  dynamic?: boolean;
  travel_group_id?: string;
  route_id?: string;
  cargo?: string[];
  destination_name?: string;
  religion_name?: string;
  guard_count?: number;
  historical_site_id?: string;
  portrait_visual?: PersonVisualProfile;
  camp_id?: string;
  camp_state?: "occupied" | "embers" | "abandoned" | "weathered";
  owner_group_id?: string;
  component_type?: string;
  site_state?: "active" | "damaged" | "abandoned" | "ruined" | "restored";
  source_event_ids?: string[];
  wear_level?: "light" | "moderate" | "heavy";
  wear_name?: string;
  repair_type?: "iron_strap" | "replacement_board" | "rope_binding" | "fresh_paint";
  repair_name?: string;
  repair_error_type?: "none" | "misspelling" | "distance_error" | "missing_character" | "illegible_text" | "illegible_distance";
  repair_error_name?: string;
};

export type MapDecoration = {
  id: string;
  kind: "natural";
  subtype: string;
  x: number;
  y: number;
  variant: number;
  scale: number;
};

export type LocalBuilding = {
  id: string;
  name: string;
  building_type: string;
  bounds: number[];
  door: { x: number; y: number };
  condition: "intact" | "damaged" | "ruined";
  infrastructure_type: string;
  infrastructure_level: number;
  historical_site_id?: string;
};

export type LocalMap = {
  site_type: "settlement" | "ruin" | "wilderness";
  cell: { x: number; y: number };
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
    feature_names: string[];
    watercourse?: Array<{ x: number; y: number }>;
  };
  tiles: number[];
  blocking_tiles: number[];
  player_start: { x: number; y: number };
  entities: MapEntity[];
  decorations: MapDecoration[];
  discovered_evidence: MapEntity[];
  buildings: LocalBuilding[];
  zones: Array<{
    id: string;
    name: string;
    bounds: number[];
    show_label?: boolean;
    zone_type?: string;
    historical_site_id?: string;
  }>;
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

export type GeographicFeature = {
  id: string;
  feature_type: "river" | "lake" | "mountain" | "plains" | "forest" | "desert" | "tundra";
  feature_type_name: string;
  name: string;
  x: number;
  y: number;
  size: number;
  importance: number;
  min_zoom: number;
  bounds: number[];
  meaning_tags: string[];
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
  geographic_features: GeographicFeature[];
  current_location_id: string | null;
  current_cell: { x: number; y: number };
  routes: Array<{
    id: string;
    status: "active" | "declining" | "abandoned" | "destroyed";
    path: Array<{ x: number; y: number }>;
  }>;
};

export type NpcRuntime = {
  id: string;
  kind: "informant" | "resident" | "caravan" | "traveler" | "wildlife";
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
  full_map_vision: boolean;
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

export type CheatState = {
  full_map_vision: {
    unlocked: boolean;
    enabled: boolean;
  };
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
  portrait_visual: PersonVisualProfile;
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

export type LibraryBook = {
  id: string;
  shelf_id: string;
  catalog_number: number;
  title: string;
  genre: string;
  genre_name: string;
  author_name: string;
  language_code: string;
  created_year: number;
  origin_name: string;
  condition: "intact" | "worn" | "fragile";
  form: string;
  audience: string;
  length_class: "short" | "single_volume" | "multi_volume" | "";
  status?: "readable" | "unknown_language";
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
  } | null;
  cell?: { x: number; y: number };
  local_map: LocalMap;
  runtime: RuntimeState;
  world_map: WorldMapState;
  informants: Informant[];
  journal: Journal;
  cheats: CheatState;
};

export type ActionResult = {
  action: string;
  journal?: Journal;
  evidence?: Record<string, unknown> | Array<Record<string, unknown>>;
  item_visual?: ItemVisualProfile;
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
  changed_map?: boolean;
  minutes?: number;
  elapsed_minutes?: number;
  location?: Pick<PlayerState, "settlement" | "local_map" | "runtime" | "informants">;
  world_map?: WorldMapState;
  origin?: { id: string; name: string };
  destination?: { id: string; name: string; site_type: "settlement" | "ruin" };
  container?: Record<string, unknown>;
  bookshelf?: Record<string, unknown>;
  library_books?: LibraryBook[];
  library_book?: LibraryBook;
  library_sections?: Array<{
    heading: string;
    text: string;
    status?: "readable" | "damaged" | "missing";
    damage_type?: string;
    damage_label?: string;
  }>;
  readability_ratio?: number | null;
  damage_labels?: string[];
  discovered_evidence?: MapEntity[];
  subject?: Record<string, unknown>;
  local_map?: LocalMap;
  newly_discovered_count?: number;
  cheats?: CheatState;
};

export type ItemVisualProfile = {
  version: number;
  seed: number;
  kind: "codex" | "scroll" | "sheet" | "tablet" | "coin" | "seal" | "weapon" | "tool" | "vessel" | "icon" | "model" | "fragment" | "monument" | "ruins" | "layer";
  material: string;
  state: string;
  condition: number;
  variant: number;
  damage: Array<"water" | "holes" | "charred" | "cracked" | "rust" | "torn" | "soil" | "faded">;
};

export type PersonVisualProfile = {
  version: number;
  seed: number;
  skin_tone: number;
  hair_color: number;
  hair_style: "short" | "cropped" | "long" | "braided" | "wavy" | "balding";
  face_shape: "round" | "oval" | "angular";
  age_group: "young" | "adult" | "mature" | "elder";
  outfit: "scholar" | "merchant" | "artisan" | "guard" | "laborer" | "official" | "cleric" | "traveler" | "common";
  headwear: "none" | "cap" | "wrap" | "hood" | "hat" | "helmet";
  expression: "calm" | "warm" | "focused" | "stern" | "weary";
  detail: "none" | "freckles" | "scar" | "earring";
  accent: number;
};
