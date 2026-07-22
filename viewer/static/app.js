"use strict";

const BIOME_STYLE = {
  ocean: { label: "海洋", color: "#356b7b" },
  lake: { label: "湖泊", color: "#4d8998" },
  river: { label: "河流", color: "#5b99a5" },
  mountain: { label: "山地", color: "#6f7472" },
  highland: { label: "高地", color: "#9a9279" },
  river_valley: { label: "河谷", color: "#72a59a" },
  forest: { label: "森林", color: "#547b58" },
  desert: { label: "沙漠", color: "#d2b66f" },
  grassland: { label: "草原", color: "#91ae68" },
  tundra: { label: "苔原", color: "#c4ced0" },
  scrubland: { label: "灌木地", color: "#a89562" },
  plains: { label: "平原", color: "#b4c48d" },
};

const EVENT_LABELS = {
  founding: "建城", war: "战争", disaster: "灾害", rebellion: "叛乱",
  economic: "经济", construction: "建设", trade: "贸易", discovery: "技术发现",
  literary_work: "文学作品", literary_spread: "文学传播",
  theoretical_work: "理论研究", reconstruction: "重建", relief: "外援",
  decline: "衰落", ruler_change: "统治更替", treaty: "条约", festival: "节庆",
  crime: "案件", raid: "袭击", exploration: "探索", omen: "天象",
  notable_birth: "出生", marriage: "婚姻", duel: "决斗",
  population_milestone: "人口里程碑",
};

const ROLE_LABELS = {
  ruler: "统治者", heir: "继承人", general: "将军", rebel_leader: "叛军领袖",
  scholar: "学者", writer: "作家", scribe: "抄写员", diplomat: "外交官",
  founder: "奠基者", noble: "贵族",
};

const PERSPECTIVE_LABELS = {
  official: "官方", folk: "民间", merchant: "商人", scholarly: "学术",
  author: "作者", eyewitness: "目击者", opposition: "反对派",
};

const EVIDENCE_LABELS = {
  document: "文书", artifact: "器物", structure: "建筑遗迹",
  environmental: "环境痕迹", oral: "口述传统",
};

const STORAGE_LABELS = {
  library_collection: "藏书室", administrative_archive: "公文档案室",
  temple_repository: "神庙经库", merchant_archive: "商会账房",
  private_collection: "私人收藏", workshop_store: "工坊库房",
  storehouse: "公共仓库", monument_site: "公共纪念地",
  field_site: "野外遗址", community_tradition: "口述传承",
};

const POLITY_COLORS = [
  "#c84f45", "#3f78b5", "#4f8a5b", "#c49336",
  "#7b61a8", "#2f8f91", "#b05a83", "#70823f",
  "#d27735", "#5b6f91", "#8a6248", "#4882a0",
];

const state = {
  data: null,
  indexes: {},
  view: "map",
  archiveMode: "records",
  selectedSettlementId: null,
  selectedEventId: null,
  selectedPersonId: null,
  selectedArchiveId: null,
  terrainCanvas: null,
  territoryCanvas: null,
  polityColors: new Map(),
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatNumber(value, digits = 0) {
  return Number(value ?? 0).toLocaleString("zh-CN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function labelEvent(type) { return EVENT_LABELS[type] || type; }
function labelRole(role) { return ROLE_LABELS[role] || role; }
function labelPerspective(value) { return PERSPECTIVE_LABELS[value] || value; }
function labelEvidence(value) { return EVIDENCE_LABELS[value] || value; }

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("visible"), 4200);
}

function setLoading(loading, text = "正在生成世界...") {
  $("#loading-text").textContent = text;
  $("#loading-overlay").classList.toggle("hidden", !loading);
}

function buildIndexes(data) {
  const index = (items) => new Map(items.map((item) => [item.id, item]));
  state.indexes = {
    settlements: index(data.settlements),
    events: index(data.events),
    records: index(data.records),
    evidence: index(data.evidence),
    persons: index(data.persons),
    storageSites: index(data.storage_sites || []),
    polities: index(data.territory?.polities || []),
  };
}

async function loadWorld(seed, years) {
  setLoading(true, `正在生成种子 ${seed} 的 ${years} 年世界...`);
  try {
    const response = await fetch(`/api/world?seed=${encodeURIComponent(seed)}&years=${encodeURIComponent(years)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    state.data = payload;
    buildIndexes(payload);
    state.selectedSettlementId = payload.settlements[0]?.id || null;
    state.selectedEventId = payload.events.at(-1)?.id || null;
    state.selectedPersonId = payload.persons[0]?.id || null;
    state.selectedArchiveId = payload.records[0]?.id || null;
    buildTerrainCanvas();
    buildTerritoryCanvas();
    renderSummary();
    populateFilters();
    renderLegend();
    renderMap();
    renderTimeline();
    renderPeople();
    renderArchive();
    history.replaceState(null, "", `?seed=${seed}&years=${years}`);
  } catch (error) {
    showToast(`世界生成失败：${error.message}`);
  } finally {
    setLoading(false);
  }
}

function renderSummary() {
  const s = state.data.summary;
  const items = [
    [state.data.world.current_year, "当前年份"],
    [s.settlements, `聚落 · ${s.alive_settlements} 存续`],
    [s.events, "历史事件"],
    [s.causal_events, "因果事件"],
    [s.persons, "人物"],
    [s.records, "当时记录"],
    [s.evidence, "证物"],
  ];
  $("#summary-strip").innerHTML = items.map(([value, label]) => `
    <div class="summary-item"><span class="summary-value">${formatNumber(value)}</span><span class="summary-label">${escapeHtml(label)}</span></div>
  `).join("");
}

function setOptions(select, values, labeler = (value) => value) {
  const previous = select.value;
  select.innerHTML = '<option value="">全部</option>' + values.map((value) =>
    `<option value="${escapeHtml(value)}">${escapeHtml(labeler(value))}</option>`
  ).join("");
  if (values.includes(previous)) select.value = previous;
}

function populateFilters() {
  setOptions($("#event-type-filter"), Object.keys(state.data.summary.event_types), labelEvent);
  setOptions($("#event-settlement-filter"), state.data.settlements.map((s) => s.id),
    (id) => state.indexes.settlements.get(id)?.name || id);
  const roles = [...new Set(state.data.persons.flatMap((person) => person.roles))].sort();
  setOptions($("#people-role-filter"), roles, labelRole);
  populateArchiveKinds();
}

function populateArchiveKinds() {
  const values = state.archiveMode === "records"
    ? [...new Set(state.data.records.map((record) => record.perspective))].sort()
    : [...new Set(state.data.evidence.map((item) => item.evidence_type))].sort();
  $("#archive-kind-label").childNodes[0].textContent = state.archiveMode === "records" ? "视角" : "证物类型";
  setOptions($("#archive-kind-filter"), values,
    state.archiveMode === "records" ? labelPerspective : labelEvidence);
}

function buildTerrainCanvas() {
  const { terrain, biome_codes: codes } = state.data.geography;
  const canvas = document.createElement("canvas");
  canvas.width = state.data.world.width;
  canvas.height = state.data.world.height;
  const context = canvas.getContext("2d");
  const image = context.createImageData(canvas.width, canvas.height);
  const namesByCode = Object.fromEntries(Object.entries(codes).map(([name, code]) => [code, name]));
  const colorCache = {};
  Object.entries(namesByCode).forEach(([code, name]) => {
    const hex = BIOME_STYLE[name].color.slice(1);
    colorCache[code] = [
      parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16), 255,
    ];
  });
  let offset = 0;
  for (const row of terrain) {
    for (const code of row) {
      image.data.set(colorCache[code], offset);
      offset += 4;
    }
  }
  context.putImageData(image, 0, 0);
  state.terrainCanvas = canvas;
}

function polityColor(code) {
  return POLITY_COLORS[Number(code) % POLITY_COLORS.length];
}

function hexToRgb(hex) {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

function buildTerritoryCanvas() {
  const territory = state.data.territory;
  state.polityColors = new Map();
  state.territoryCanvas = null;
  if (!territory?.owners?.length) return;

  for (const polity of territory.polities) {
    state.polityColors.set(polity.id, polityColor(polity.code));
  }
  const canvas = document.createElement("canvas");
  canvas.width = state.data.world.width;
  canvas.height = state.data.world.height;
  const context = canvas.getContext("2d");
  const image = context.createImageData(canvas.width, canvas.height);
  const colors = Object.fromEntries(territory.polities.map((polity) => [
    polity.code, hexToRgb(polityColor(polity.code)),
  ]));
  const unclaimed = territory.unclaimed_code;
  let offset = 0;
  for (let y = 0; y < canvas.height; y += 1) {
    for (let x = 0; x < canvas.width; x += 1) {
      const code = territory.owners[y][x];
      if (code !== unclaimed && colors[code]) {
        const boundary = (
          x === 0 || y === 0 || x === canvas.width - 1 || y === canvas.height - 1
          || territory.owners[y][x - 1] !== code
          || territory.owners[y][x + 1] !== code
          || territory.owners[y - 1][x] !== code
          || territory.owners[y + 1][x] !== code
        );
        image.data.set([...colors[code], boundary ? 190 : 82], offset);
      }
      offset += 4;
    }
  }
  context.putImageData(image, 0, 0);
  state.territoryCanvas = canvas;
}

function renderLegend() {
  if ($("#toggle-territories").checked && state.data.territory) {
    $("#map-legend").classList.add("territory-legend");
    $("#map-legend").innerHTML = state.data.territory.polities.map((polity) => `
      <span class="legend-item"><span class="swatch" style="background:${polityColor(polity.code)}"></span>${escapeHtml(polity.name)}</span>
    `).join("") + '<span class="legend-item"><span class="swatch swatch-unclaimed"></span>无主地</span>';
    return;
  }
  $("#map-legend").classList.remove("territory-legend");
  $("#map-legend").innerHTML = Object.entries(BIOME_STYLE).map(([name, style]) => `
    <span class="legend-item"><span class="swatch" style="background:${style.color}"></span>${style.label}</span>
  `).join("");
}

function canvasMetrics() {
  const canvas = $("#world-map");
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * ratio));
  const height = Math.max(1, Math.round(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { canvas, rect, ratio, width, height };
}

function renderMap() {
  if (!state.data || !state.terrainCanvas) return;
  const { canvas, width, height, ratio } = canvasMetrics();
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, width, height);
  context.imageSmoothingEnabled = false;
  context.drawImage(state.terrainCanvas, 0, 0, width, height);
  if ($("#toggle-territories").checked && state.territoryCanvas) {
    context.drawImage(state.territoryCanvas, 0, 0, width, height);
  }
  const sx = width / state.data.world.width;
  const sy = height / state.data.world.height;

  if ($("#toggle-relations").checked) drawRelationships(context, sx, sy);
  drawSettlements(context, sx, sy, ratio);

  const selected = state.indexes.settlements.get(state.selectedSettlementId);
  if (selected) renderSettlementDetail(selected, $("#map-inspector"));
  else renderWorldOverview($("#map-inspector"));
}

function drawRelationships(context, sx, sy) {
  const drawn = new Set();
  context.save();
  for (const settlement of state.data.settlements) {
    for (const [partnerId, relation] of Object.entries(settlement.relationships)) {
      const pair = [settlement.id, partnerId].sort().join("|");
      if (drawn.has(pair)) continue;
      drawn.add(pair);
      const partner = state.indexes.settlements.get(partnerId);
      if (!partner) continue;
      const hostile = relation.hostility > relation.trust;
      context.strokeStyle = hostile ? "rgba(162,60,53,0.62)" : "rgba(53,111,145,0.55)";
      context.lineWidth = 1 + Math.min(3, relation.trade_volume / 120);
      context.setLineDash(hostile ? [5, 4] : []);
      context.beginPath();
      context.moveTo((settlement.grid_x + 0.5) * sx, (settlement.grid_y + 0.5) * sy);
      context.lineTo((partner.grid_x + 0.5) * sx, (partner.grid_y + 0.5) * sy);
      context.stroke();
    }
  }
  context.restore();
}

function drawSettlements(context, sx, sy, ratio) {
  const showLabels = $("#toggle-labels").checked;
  const showRuins = $("#toggle-ruins").checked;
  context.save();
  context.font = `${Math.round(11 * ratio)}px "Segoe UI", "Microsoft YaHei", sans-serif`;
  context.textBaseline = "middle";
  for (const settlement of state.data.settlements) {
    if (!showRuins && !settlement.alive) continue;
    const x = (settlement.grid_x + 0.5) * sx;
    const y = (settlement.grid_y + 0.5) * sy;
    const selected = settlement.id === state.selectedSettlementId;
    const radius = (settlement.size === "city" ? 6 : settlement.size === "town" ? 5 : 4) * ratio;
    context.lineWidth = selected ? 3 * ratio : 1.5 * ratio;
    context.strokeStyle = selected ? "#fff7df" : "#202420";
    context.fillStyle = settlement.alive ? "#b88732" : "#a23c35";
    context.beginPath();
    if (settlement.alive) {
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    } else {
      context.moveTo(x - radius, y - radius);
      context.lineTo(x + radius, y + radius);
      context.moveTo(x + radius, y - radius);
      context.lineTo(x - radius, y + radius);
      context.stroke();
    }
    if (showLabels) {
      const label = settlement.name;
      const tx = x + radius + 4 * ratio;
      context.lineWidth = 3 * ratio;
      context.strokeStyle = "rgba(247,248,245,0.92)";
      context.strokeText(label, tx, y);
      context.fillStyle = "#1f231f";
      context.fillText(label, tx, y);
    }
  }
  context.restore();
}

function renderWorldOverview(target) {
  const s = state.data.summary;
  target.innerHTML = `
    <p class="inspector-kicker">世界概览</p>
    <h2>种子 ${state.data.world.seed}</h2>
    <p class="inspector-subtitle">第 ${state.data.world.current_year} 年 · ${state.data.world.width} × ${state.data.world.height} 地理网格</p>
    ${detailSection("事件分布", Object.entries(s.event_types).map(([type, count]) =>
      `<div class="metric-row"><span>${escapeHtml(labelEvent(type))}</span><div class="metric-track"><div class="metric-fill" style="width:${Math.min(100, count / Math.max(...Object.values(s.event_types)) * 100)}%"></div></div><span class="metric-value">${count}</span></div>`
    ).join(""))}
  `;
}

function detailSection(title, content) {
  return `<section class="detail-section"><h3>${escapeHtml(title)}</h3>${content}</section>`;
}

function detailGrid(rows) {
  return `<dl class="detail-grid">${rows.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${value}</dd>`).join("")}</dl>`;
}

function entityLink(type, id, label) {
  if (!id) return '<span class="cell-muted">无</span>';
  return `<button class="entity-link" data-entity-type="${escapeHtml(type)}" data-entity-id="${escapeHtml(id)}">${escapeHtml(label || id)}</button>`;
}

function entityLinks(type, ids, labeler) {
  if (!ids?.length) return '<span class="cell-muted">无</span>';
  return `<div class="link-list">${ids.map((id) => entityLink(type, id, labeler(id))).join("")}</div>`;
}

function renderSettlementDetail(settlement, target) {
  const ruler = state.indexes.persons.get(settlement.ruler_id);
  const polity = state.indexes.polities.get(settlement.controller_polity_id);
  const recent = settlement.event_ids.slice(-8).reverse();
  const relations = Object.values(settlement.relationships).sort((a, b) => b.trust - a.trust);
  const storageSites = (settlement.storage_site_ids || [])
    .map((id) => state.indexes.storageSites.get(id)).filter(Boolean);
  target.innerHTML = `
    <p class="inspector-kicker">聚落 · ${escapeHtml(BIOME_STYLE[settlement.biome]?.label || settlement.biome)}</p>
    <h2>${escapeHtml(settlement.name)}</h2>
    <p class="inspector-subtitle"><span class="status-tag ${settlement.alive ? "status-alive" : "status-dead"}">${settlement.alive ? "存续" : "废墟"}</span> ${escapeHtml(settlement.size)} · 坐标 ${settlement.grid_x}, ${settlement.grid_y}</p>
    ${detailSection("状态", detailGrid([
      ["人口", formatNumber(settlement.population)],
      ["粮食库存", formatNumber(settlement.food_stock, 1)],
      ["财政", formatNumber(settlement.treasury, 1)],
      ["所属国家", escapeHtml(polity?.name || "无")],
      ["统治者", ruler ? entityLink("person", ruler.id, ruler.name) : escapeHtml(settlement.ruler_name || "无")],
      ["建立年份", formatNumber(settlement.founded_year)],
      ["毁灭年份", settlement.destroyed_year == null ? "-" : formatNumber(settlement.destroyed_year)],
    ]))}
    ${detailSection("社会与知识", [
      metric("稳定度", settlement.stability, 1),
      metric("合法性", settlement.legitimacy, 1),
      metric("文化", settlement.cultural_influence, 10),
      metric("理论", settlement.theoretical_knowledge, 10),
      metric("科技", settlement.technology_level, 10),
    ].join(""))}
    ${detailSection("基础设施", Object.keys(settlement.infrastructure).length
      ? detailGrid(Object.entries(settlement.infrastructure).map(([key, value]) => [key, formatNumber(value, 2)]))
      : '<span class="cell-muted">无</span>')}
    ${detailSection("实体收藏点", storageSites.length ? storageSites.map((site) => `
      <div class="claim-block"><p>${escapeHtml(site.name)}</p><span class="claim-meta">${escapeHtml(STORAGE_LABELS[site.site_type] || site.site_type)} · ${site.inventory_count} 件 · ${site.alive ? `状况 ${formatNumber(site.condition, 2)}` : "已毁"} · ${escapeHtml(site.accessibility)}</span></div>
    `).join("") : '<span class="cell-muted">无</span>')}
    ${detailSection("外交关系", relations.length ? relations.map((relation) => {
      const partner = state.indexes.settlements.get(relation.partner_id);
      return `<div class="claim-block"><p>${entityLink("settlement", relation.partner_id, partner?.name || relation.partner_id)}</p><span class="claim-meta">信任 ${formatNumber(relation.trust, 2)} · 敌意 ${formatNumber(relation.hostility, 2)} · 贸易 ${formatNumber(relation.trade_volume, 1)}</span></div>`;
    }).join("") : '<span class="cell-muted">尚无正式关系</span>')}
    ${detailSection("最近事件", entityLinks("event", recent, (id) => state.indexes.events.get(id)?.title || id))}
  `;
}

function metric(label, value, maximum) {
  const normalized = Math.max(0, Math.min(1, Number(value) / maximum));
  return `<div class="metric-row"><span>${escapeHtml(label)}</span><div class="metric-track"><div class="metric-fill" style="width:${normalized * 100}%"></div></div><span class="metric-value">${formatNumber(value, 2)}</span></div>`;
}

function renderTimeline() {
  if (!state.data) return;
  const query = $("#event-search").value.trim().toLocaleLowerCase();
  const type = $("#event-type-filter").value;
  const settlementId = $("#event-settlement-filter").value;
  const causalOnly = $("#event-causal-filter").checked;
  const events = state.data.events.filter((event) => {
    const haystack = `${event.title} ${event.event_type} ${JSON.stringify(event.details)}`.toLocaleLowerCase();
    return (!query || haystack.includes(query))
      && (!type || event.event_type === type)
      && (!settlementId || event.participants.includes(settlementId) || event.primary_location === settlementId)
      && (!causalOnly || event.cause_event_ids.length > 0);
  }).sort((a, b) => b.year - a.year || b.id.localeCompare(a.id));

  $("#event-result-count").textContent = `${events.length} 条`;
  $("#event-table-body").innerHTML = events.length ? events.map((event) => {
    const location = state.indexes.settlements.get(event.primary_location);
    return `<tr data-row-id="${event.id}" class="${event.id === state.selectedEventId ? "selected" : ""}">
      <td>${event.year}</td><td><span class="cell-title">${escapeHtml(event.title)}</span></td>
      <td><span class="type-tag">${escapeHtml(labelEvent(event.event_type))}</span></td>
      <td>${escapeHtml(location?.name || event.primary_location)}</td>
      <td>${event.cause_event_ids.length}</td><td>${event.record_ids.length}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="6" class="cell-muted">没有匹配事件</td></tr>';

  const selected = events.find((event) => event.id === state.selectedEventId) || events[0];
  if (selected) {
    state.selectedEventId = selected.id;
    renderEventDetail(selected, $("#timeline-inspector"));
  } else {
    $("#timeline-inspector").innerHTML = '<p class="inspector-empty">没有事件可显示</p>';
  }
}

function renderEventDetail(event, target) {
  const location = state.indexes.settlements.get(event.primary_location);
  const consequences = state.data.events.filter((candidate) => candidate.cause_event_ids.includes(event.id));
  const description = event.details.description_cn || "无叙述文本";
  const structuredDetails = Object.fromEntries(Object.entries(event.details).filter(([key]) => key !== "description_cn"));
  target.innerHTML = `
    <p class="inspector-kicker">模拟真相 · ${escapeHtml(labelEvent(event.event_type))}</p>
    <h2>${escapeHtml(event.title)}</h2>
    <p class="inspector-subtitle">第 ${event.year} 年 · ${escapeHtml(location?.name || event.primary_location)} · 重要度 ${formatNumber(event.importance_score, 2)}</p>
    ${detailSection("事件叙述", `<p class="detail-copy">${escapeHtml(description)}</p>`)}
    ${detailSection("结构", detailGrid([
      ["事件 ID", `<code>${escapeHtml(event.id)}</code>`],
      ["严重度", formatNumber(event.severity, 2)],
      ["可见度", formatNumber(event.visibility_score, 2)],
      ["历史过程", event.process_id ? `<code>${escapeHtml(event.process_id)}</code>` : "-"],
      ["人物", entityLinks("person", event.person_ids, (id) => state.indexes.persons.get(id)?.name || id)],
    ]))}
    ${detailSection("前置原因", entityLinks("event", event.cause_event_ids, (id) => state.indexes.events.get(id)?.title || id))}
    ${detailSection("后续结果", entityLinks("event", consequences.map((item) => item.id), (id) => state.indexes.events.get(id)?.title || id))}
    ${detailSection("结构化效果", event.effects.length ? event.effects.map((effect) =>
      `<div class="claim-block"><p><strong>${escapeHtml(effect.effect_type)}</strong></p><span class="claim-meta">${escapeHtml(effect.reason || "无原因标签")}</span></div>`
    ).join("") : '<span class="cell-muted">无状态效果</span>')}
    ${detailSection("记录版本", entityLinks("record", event.record_ids, (id) => {
      const record = state.indexes.records.get(id); return `${labelPerspective(record?.perspective)} · ${record?.record_type || id}`;
    }))}
    ${detailSection("证物", entityLinks("evidence", event.evidence_ids, (id) => {
      const item = state.indexes.evidence.get(id); return item?.physical_features?.display_name || item?.subtype || id;
    }))}
    ${Object.keys(structuredDetails).length ? detailSection("原始字段", `<pre class="json-details">${escapeHtml(JSON.stringify(structuredDetails, null, 2))}</pre>`) : ""}
  `;
}

function renderPeople() {
  if (!state.data) return;
  const query = $("#people-search").value.trim().toLocaleLowerCase();
  const role = $("#people-role-filter").value;
  const aliveOnly = $("#people-alive-filter").checked;
  const people = state.data.persons.filter((person) => {
    const settlement = state.indexes.settlements.get(person.settlement_id);
    return (!query || `${person.name} ${settlement?.name || ""}`.toLocaleLowerCase().includes(query))
      && (!role || person.roles.includes(role))
      && (!aliveOnly || person.alive);
  }).sort((a, b) => Number(b.alive) - Number(a.alive) || a.name.localeCompare(b.name));
  $("#people-result-count").textContent = `${people.length} 人`;
  $("#people-table-body").innerHTML = people.length ? people.map((person) => {
    const settlement = state.indexes.settlements.get(person.settlement_id);
    return `<tr data-row-id="${person.id}" class="${person.id === state.selectedPersonId ? "selected" : ""}">
      <td colspan="1"><span class="cell-title">${escapeHtml(person.name)}</span></td>
      <td>${person.roles.map((item) => `<span class="type-tag">${escapeHtml(labelRole(item))}</span>`).join(" ")}</td>
      <td>${escapeHtml(settlement?.name || person.settlement_id)}</td>
      <td>${person.birth_year}–${person.death_year ?? ""}</td><td>${person.event_ids.length}</td>
    </tr>`;
  }).join("") : '<tr><td colspan="5" class="cell-muted">没有匹配人物</td></tr>';
  const selected = people.find((person) => person.id === state.selectedPersonId) || people[0];
  if (selected) {
    state.selectedPersonId = selected.id;
    renderPersonDetail(selected, $("#people-inspector"));
  } else $("#people-inspector").innerHTML = '<p class="inspector-empty">没有人物可显示</p>';
}

function renderPersonDetail(person, target) {
  const settlement = state.indexes.settlements.get(person.settlement_id);
  target.innerHTML = `
    <p class="inspector-kicker">人物</p>
    <h2>${escapeHtml(person.name)}</h2>
    <p class="inspector-subtitle"><span class="status-tag ${person.alive ? "status-alive" : "status-dead"}">${person.alive ? "在世" : "已故"}</span> ${person.roles.map(labelRole).join(" · ") || "无角色"}</p>
    ${detailSection("身份", detailGrid([
      ["出生年份", person.birth_year],
      ["死亡年份", person.death_year ?? "-"],
      ["所属聚落", entityLink("settlement", person.settlement_id, settlement?.name || person.settlement_id)],
      ["父母", entityLinks("person", person.parent_ids, (id) => state.indexes.persons.get(id)?.name || id)],
      ["配偶", entityLinks("person", person.spouse_ids, (id) => state.indexes.persons.get(id)?.name || id)],
    ]))}
    ${detailSection("参与事件", entityLinks("event", person.event_ids, (id) => {
      const event = state.indexes.events.get(id); return event ? `[${event.year}] ${event.title}` : id;
    }))}
  `;
}

function renderArchive() {
  if (!state.data) return;
  const query = $("#archive-search").value.trim().toLocaleLowerCase();
  const kind = $("#archive-kind-filter").value;
  if (state.archiveMode === "records") renderRecordTable(query, kind);
  else renderEvidenceTable(query, kind);
}

function renderRecordTable(query, kind) {
  const records = state.data.records.filter((record) => {
    const text = `${record.record_type} ${record.perspective} ${record.claimed_facts.map((claim) => claim.statement_cn).join(" ")}`.toLocaleLowerCase();
    return (!query || text.includes(query)) && (!kind || record.perspective === kind);
  }).sort((a, b) => b.created_year - a.created_year || b.id.localeCompare(a.id));
  $("#archive-result-count").textContent = `${records.length} 份`;
  $("#archive-table-head").innerHTML = "<tr><th>年份</th><th>类型</th><th>视角</th><th>主张</th><th>载体</th></tr>";
  $("#archive-table-body").innerHTML = records.length ? records.map((record) => `
    <tr data-row-id="${record.id}" class="${record.id === state.selectedArchiveId ? "selected" : ""}">
      <td>${record.created_year}</td><td><span class="cell-title">${escapeHtml(record.record_type)}</span></td>
      <td><span class="type-tag">${escapeHtml(labelPerspective(record.perspective))}</span></td>
      <td>${record.claimed_facts.length}</td><td>${record.evidence_ids.length}</td>
    </tr>`).join("") : '<tr><td colspan="5" class="cell-muted">没有匹配记录</td></tr>';
  const selected = records.find((record) => record.id === state.selectedArchiveId) || records[0];
  if (selected) {
    state.selectedArchiveId = selected.id;
    renderRecordDetail(selected, $("#archive-inspector"));
  } else $("#archive-inspector").innerHTML = '<p class="inspector-empty">没有记录可显示</p>';
}

function renderEvidenceTable(query, kind) {
  const evidence = state.data.evidence.filter((item) => {
    const written = item.content_data?.written_content?.passages?.map((passage) => passage.text).join(" ") || "";
    const text = `${item.subtype} ${item.material} ${item.state} ${item.physical_features?.display_name || ""} ${written}`.toLocaleLowerCase();
    return (!query || text.includes(query)) && (!kind || item.evidence_type === kind);
  }).sort((a, b) => b.created_year - a.created_year || b.id.localeCompare(a.id));
  $("#archive-result-count").textContent = `${evidence.length} 件`;
  $("#archive-table-head").innerHTML = "<tr><th>年份</th><th>证物</th><th>类型</th><th>材质</th><th>状态</th></tr>";
  $("#archive-table-body").innerHTML = evidence.length ? evidence.map((item) => `
    <tr data-row-id="${item.id}" class="${item.id === state.selectedArchiveId ? "selected" : ""}">
      <td>${item.created_year}</td><td><span class="cell-title">${escapeHtml(item.physical_features?.display_name || item.subtype)}</span></td>
      <td><span class="type-tag">${escapeHtml(labelEvidence(item.evidence_type))}</span></td>
      <td>${escapeHtml(item.material)}</td><td>${escapeHtml(item.state)}</td>
    </tr>`).join("") : '<tr><td colspan="5" class="cell-muted">没有匹配证物</td></tr>';
  const selected = evidence.find((item) => item.id === state.selectedArchiveId) || evidence[0];
  if (selected) {
    state.selectedArchiveId = selected.id;
    renderEvidenceDetail(selected, $("#archive-inspector"));
  } else $("#archive-inspector").innerHTML = '<p class="inspector-empty">没有证物可显示</p>';
}

function renderRecordDetail(record, target) {
  const author = state.indexes.persons.get(record.author_person_id);
  const copies = state.data.records.filter((item) => item.copy_parent_id === record.id);
  target.innerHTML = `
    <p class="inspector-kicker">历史记录 · ${escapeHtml(labelPerspective(record.perspective))}</p>
    <h2>${escapeHtml(record.record_type)}</h2>
    <p class="inspector-subtitle">第 ${record.created_year} 年 · ${record.copy_parent_id ? '<span class="status-tag status-copy">抄本</span>' : "原始版本"}</p>
    ${detailSection("记录身份", detailGrid([
      ["记录 ID", `<code>${escapeHtml(record.id)}</code>`],
      ["作者", author ? entityLink("person", author.id, author.name) : escapeHtml(record.author_faction_id || "未署名")],
      ["目标读者", escapeHtml(record.intended_audience)],
      ["载体类型", escapeHtml(record.carrier_subtype)],
      ["语言", escapeHtml(record.language_code)],
      ["母本", record.copy_parent_id ? entityLink("record", record.copy_parent_id, record.copy_parent_id) : "-"],
    ]))}
    ${detailSection("记录主张", record.claimed_facts.map((claim) => `
      <div class="claim-block"><p>${escapeHtml(claim.statement_cn)}</p><span class="claim-meta">${claim.time_range[0]}–${claim.time_range[1]} · ${escapeHtml(claim.subject)} / ${escapeHtml(claim.predicate)} / ${escapeHtml(claim.object)}</span></div>
    `).join("") || '<span class="cell-muted">没有可读主张</span>')}
    ${detailSection("省略与失真", detailGrid([
      ["省略", escapeHtml(record.omitted_facts.join(", ") || "无")],
      ["失真", escapeHtml(record.distortions.join(", ") || "无")],
      ["保密度", formatNumber(record.secrecy, 2)],
    ]))}
    ${detailSection("来源事件", entityLinks("event", record.source_event_ids, (id) => state.indexes.events.get(id)?.title || id))}
    ${detailSection("物理载体", entityLinks("evidence", record.evidence_ids, (id) => state.indexes.evidence.get(id)?.physical_features?.display_name || id))}
    ${copies.length ? detailSection("衍生抄本", entityLinks("record", copies.map((item) => item.id), (id) => id)) : ""}
  `;
}

function renderEvidenceDetail(item, target) {
  const written = item.content_data?.written_content;
  const record = state.indexes.records.get(item.source_record_id);
  const event = state.indexes.events.get(item.event_id);
  const site = state.indexes.storageSites.get(item.container_id);
  const settlement = state.indexes.settlements.get(item.location_id);
  target.innerHTML = `
    <p class="inspector-kicker">证物 · ${escapeHtml(labelEvidence(item.evidence_type))}</p>
    <h2>${escapeHtml(item.physical_features?.display_name || item.subtype)}</h2>
    <p class="inspector-subtitle">第 ${item.created_year} 年 · ${escapeHtml(item.material)} · ${escapeHtml(item.state)} ${item.authenticity === "copy" ? '<span class="status-tag status-copy">抄本</span>' : ""}</p>
    ${detailSection("保存状态", [
      metric("耐久", item.condition_ratio, 1),
      detailGrid([
        ["证物 ID", `<code>${escapeHtml(item.id)}</code>`],
        ["发现难度", formatNumber(item.discoverability, 2)],
        ["可访问性", escapeHtml(item.accessibility)],
        ["叙事视角", escapeHtml(labelPerspective(item.narrative_bias))],
      ]),
    ].join(""))}
    ${detailSection("关联", detailGrid([
      ["后台事件", event ? entityLink("event", event.id, event.title) : "-"],
      ["来源记录", record ? entityLink("record", record.id, `${labelPerspective(record.perspective)} · ${record.record_type}`) : "行动遗留物"],
      ["物理母本", item.is_copy_of ? entityLink("evidence", item.is_copy_of, item.is_copy_of) : "-"],
    ]))}
    ${detailSection("实体位置", detailGrid([
      ["所在聚落", settlement ? entityLink("settlement", settlement.id, settlement.name) : escapeHtml(item.location_id)],
      ["收藏点", escapeHtml(site?.name || item.container_id || "未编目")],
      ["收藏类型", escapeHtml(STORAGE_LABELS[site?.site_type] || site?.site_type || item.holder_type)],
      ["具体位置", escapeHtml(item.storage_position || "未编目")],
      ["保管状态", site ? `${site.alive ? "存续" : "已毁"} · 状况 ${formatNumber(site.condition, 2)}` : "未知"],
    ]))}
    ${item.location_history?.length ? detailSection("位置沿革", item.location_history.map((entry) => {
      const from = state.indexes.storageSites.get(entry.from_container_id)?.name || entry.from_container_id || "生成地点";
      const to = state.indexes.storageSites.get(entry.to_container_id)?.name || entry.to_container_id || "未知地点";
      return `<div class="claim-block"><p>第 ${entry.year} 年：${escapeHtml(from)} → ${escapeHtml(to)}</p><span class="claim-meta">${escapeHtml(entry.reason)}</span></div>`;
    }).join("")) : ""}
    ${detailSection("观察标签", `<div class="link-list">${(item.physical_features?.tags || []).map((tag) => `<span class="type-tag">${escapeHtml(tag)}</span>`).join("")}</div>`)}
    ${item.contamination.length ? detailSection("混入与改动", `<p class="detail-copy">${escapeHtml(item.contamination.join(", "))}</p>`) : ""}
    ${written ? detailSection("文书正文", `<div class="passages">${written.passages.map((passage) => `<p class="passage ${escapeHtml(passage.kind)}">${escapeHtml(passage.text)}</p>`).join("")}</div>`) : ""}
  `;
}

function switchView(view) {
  state.view = view;
  $$(".tab-button").forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  $$(".app-view").forEach((panel) => panel.classList.toggle("active", panel.id === `view-${view}`));
  if (view === "map") requestAnimationFrame(renderMap);
}

function openEntity(type, id) {
  if (type === "settlement") {
    state.selectedSettlementId = id;
    switchView("map");
    renderMap();
  } else if (type === "event") {
    state.selectedEventId = id;
    switchView("timeline");
    renderTimeline();
  } else if (type === "person") {
    state.selectedPersonId = id;
    switchView("people");
    renderPeople();
  } else if (type === "record" || type === "evidence") {
    state.archiveMode = type === "record" ? "records" : "evidence";
    state.selectedArchiveId = id;
    $$(".segment").forEach((button) => button.classList.toggle("active", button.dataset.archive === state.archiveMode));
    populateArchiveKinds();
    switchView("archive");
    renderArchive();
  }
}

function bindEvents() {
  $("#world-form").addEventListener("submit", (event) => {
    event.preventDefault();
    loadWorld(Number($("#seed-input").value), Number($("#years-input").value));
  });
  $$(".tab-button").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  ["#toggle-labels", "#toggle-relations", "#toggle-ruins"].forEach((selector) => $(selector).addEventListener("change", renderMap));
  $("#toggle-territories").addEventListener("change", () => {
    renderLegend();
    renderMap();
  });
  ["#event-search", "#event-type-filter", "#event-settlement-filter", "#event-causal-filter"].forEach((selector) => {
    $(selector).addEventListener(selector.includes("search") ? "input" : "change", renderTimeline);
  });
  ["#people-search", "#people-role-filter", "#people-alive-filter"].forEach((selector) => {
    $(selector).addEventListener(selector.includes("search") ? "input" : "change", renderPeople);
  });
  ["#archive-search", "#archive-kind-filter"].forEach((selector) => {
    $(selector).addEventListener(selector.includes("search") ? "input" : "change", renderArchive);
  });
  $$(".segment").forEach((button) => button.addEventListener("click", () => {
    state.archiveMode = button.dataset.archive;
    state.selectedArchiveId = state.archiveMode === "records" ? state.data.records[0]?.id : state.data.evidence[0]?.id;
    $$(".segment").forEach((item) => item.classList.toggle("active", item === button));
    populateArchiveKinds();
    renderArchive();
  }));
  $("#event-table-body").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-row-id]");
    if (!row) return;
    state.selectedEventId = row.dataset.rowId;
    renderTimeline();
  });
  $("#people-table-body").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-row-id]");
    if (!row) return;
    state.selectedPersonId = row.dataset.rowId;
    renderPeople();
  });
  $("#archive-table-body").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-row-id]");
    if (!row) return;
    state.selectedArchiveId = row.dataset.rowId;
    renderArchive();
  });
  document.body.addEventListener("click", (event) => {
    const link = event.target.closest("[data-entity-type][data-entity-id]");
    if (link) openEntity(link.dataset.entityType, link.dataset.entityId);
  });
  const canvas = $("#world-map");
  canvas.addEventListener("mousemove", updateMapCoordinate);
  canvas.addEventListener("mouseleave", () => $("#map-coordinate").textContent = "坐标 --, --");
  canvas.addEventListener("click", selectSettlementAtPointer);
  new ResizeObserver(() => requestAnimationFrame(renderMap)).observe($(".map-stage"));
}

function pointerWorldPosition(event) {
  const rect = $("#world-map").getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(state.data.world.width - 1, Math.floor((event.clientX - rect.left) / rect.width * state.data.world.width))),
    y: Math.max(0, Math.min(state.data.world.height - 1, Math.floor((event.clientY - rect.top) / rect.height * state.data.world.height))),
  };
}

function updateMapCoordinate(event) {
  if (!state.data) return;
  const point = pointerWorldPosition(event);
  const code = state.data.geography.terrain[point.y][point.x];
  const biome = Object.entries(state.data.geography.biome_codes).find(([, value]) => value === code)?.[0];
  const territoryCode = state.data.territory?.owners?.[point.y]?.[point.x];
  const polity = state.data.territory?.polities.find((item) => item.code === territoryCode);
  $("#map-coordinate").textContent = `坐标 ${point.x}, ${point.y} · ${BIOME_STYLE[biome]?.label || biome}${polity ? ` · ${polity.name}` : " · 无主地"}`;
}

function selectSettlementAtPointer(event) {
  if (!state.data) return;
  const point = pointerWorldPosition(event);
  const visible = state.data.settlements.filter((settlement) => $("#toggle-ruins").checked || settlement.alive);
  const nearest = visible.map((settlement) => ({
    settlement,
    distance: Math.hypot(settlement.grid_x - point.x, settlement.grid_y - point.y),
  })).sort((a, b) => a.distance - b.distance)[0];
  if (nearest && nearest.distance <= 6) {
    state.selectedSettlementId = nearest.settlement.id;
    renderMap();
  }
}

function initialize() {
  bindEvents();
  const params = new URLSearchParams(location.search);
  const seed = Number(params.get("seed") ?? 42);
  const years = Number(params.get("years") ?? 100);
  $("#seed-input").value = seed;
  $("#years-input").value = years;
  loadWorld(seed, years);
}

document.addEventListener("DOMContentLoaded", initialize);
