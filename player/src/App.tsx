import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BookOpen,
  Boxes,
  FileText,
  Footprints,
  Info,
  LoaderCircle,
  MessageSquareText,
  RefreshCw,
  Scale,
  Search,
  Users,
  X,
} from "lucide-react";
import { performAction, startSession } from "./api";
import GameCanvas from "./GameCanvas";
import type { ActionResult, Journal, MapEntity, PlayerState } from "./types";

const TYPE_LABELS: Record<string, string> = {
  document: "文书",
  artifact: "器物",
  structure: "遗构",
  environmental: "环境痕迹",
};

const MATERIAL_LABELS: Record<string, string> = {
  parchment: "羊皮纸",
  stone: "石材",
  metal: "金属",
  wood: "木材",
  cloth: "织物",
};

const BIOME_LABELS: Record<string, string> = {
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

type DockTab = "inspect" | "people" | "journal";
type JournalTab = "observations" | "texts" | "statements" | "claims" | "conflicts";

function value(item: Record<string, unknown>, key: string) {
  return String(item[key] ?? "");
}

function list(item: Record<string, unknown>, key: string) {
  const result = item[key];
  return Array.isArray(result) ? result : [];
}

export default function App() {
  const [seed, setSeed] = useState(42);
  const [years, setYears] = useState(30);
  const [sessionId, setSessionId] = useState("");
  const [state, setState] = useState<PlayerState | null>(null);
  const [journal, setJournal] = useState<Journal | null>(null);
  const [selected, setSelected] = useState<MapEntity | null>(null);
  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null);
  const [nearbyIds, setNearbyIds] = useState<string[]>([]);
  const [examinedIds, setExaminedIds] = useState<Set<string>>(new Set());
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [dockTab, setDockTab] = useState<DockTab>("inspect");
  const [journalTab, setJournalTab] = useState<JournalTab>("observations");
  const [detail, setDetail] = useState<ActionResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const started = useRef(false);

  const createWorld = useCallback(async () => {
    setLoading(true);
    setNotice("");
    try {
      const response = await startSession(seed, years);
      setSessionId(response.session_id);
      setState(response.state);
      setJournal(response.state.journal);
      setSelected(null);
      setActiveEvidenceId(null);
      setExaminedIds(new Set());
      setReadIds(new Set());
      setCompareIds([]);
      setDetail(null);
      setDockTab("inspect");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "无法创建世界");
    } finally {
      setLoading(false);
    }
  }, [seed, years]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void createWorld();
  }, [createWorld]);

  const runAction = useCallback(
    async (payload: Record<string, unknown>) => {
      if (!sessionId) return null;
      setBusy(true);
      setNotice("");
      try {
        const result = await performAction(sessionId, payload);
        if (result.journal) setJournal(result.journal);
        setDetail(result);
        if (payload.action === "examine") {
          const id = String(payload.evidence_id);
          setExaminedIds((current) => new Set(current).add(id));
          setActiveEvidenceId(id);
        }
        if (payload.action === "read") {
          setReadIds((current) => new Set(current).add(String(payload.evidence_id)));
        }
        return result;
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "调查动作失败");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [sessionId],
  );

  const onSelect = useCallback((entity: MapEntity) => {
    setSelected(entity);
    setDockTab(entity.kind === "evidence" ? "inspect" : "people");
    if (entity.kind === "evidence") setActiveEvidenceId(entity.id);
  }, []);

  const onInteract = useCallback(
    (entity: MapEntity | null) => {
      if (!entity) {
        setNotice("附近没有可以互动的对象。靠近证物或人物后再试。 ");
        return;
      }
      onSelect(entity);
      if (entity.kind === "evidence" && !examinedIds.has(entity.id)) {
        void runAction({ action: "examine", evidence_id: entity.id });
      }
    },
    [examinedIds, onSelect, runAction],
  );

  const selectedIsNearby = selected ? nearbyIds.includes(selected.id) : false;
  const selectedEvidence = selected?.kind === "evidence" ? selected : null;
  const selectedPerson = selected && selected.kind !== "evidence" ? selected : null;
  const activeEvidence = useMemo(
    () => state?.local_map.entities.find((item) => item.id === activeEvidenceId) ?? null,
    [activeEvidenceId, state],
  );

  const addToCompare = (id: string) => {
    setCompareIds((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= 2) return [current[1], id];
      return [...current, id];
    });
  };

  const compare = async () => {
    if (compareIds.length !== 2) return;
    const result = await runAction({
      action: "compare",
      first_id: compareIds[0],
      second_id: compareIds[1],
    });
    if (result) setDockTab("inspect");
  };

  if (!state && !loading) {
    return (
      <main className="fatal-state">
        <h1>无法启动调查原型</h1>
        <p>{notice || "世界生成没有返回可用状态。"}</p>
        <button className="command-button primary" onClick={() => void createWorld()}>
          <RefreshCw size={16} /> 重试
        </button>
      </main>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">HF</span>
          <div>
            <h1>HistoryFinder</h1>
            <span>步行调查原型</span>
          </div>
        </div>
        {state && (
          <div className="location-heading">
            <strong>{state.settlement.name}</strong>
            <span>
              {BIOME_LABELS[state.settlement.biome] ?? state.settlement.biome} · 第 {state.world.current_year} 年
            </span>
          </div>
        )}
        <div className="world-settings">
          <label>
            种子
            <input value={seed} type="number" onChange={(event) => setSeed(Number(event.target.value))} />
          </label>
          <label>
            年数
            <input value={years} type="number" min={0} max={300} onChange={(event) => setYears(Number(event.target.value))} />
          </label>
          <button className="icon-command" title="重新生成世界" onClick={() => void createWorld()} disabled={loading}>
            <RefreshCw size={18} />
          </button>
        </div>
      </header>

      <main className="workspace">
        <section className="scene-pane" aria-label="当前聚落">
          {state && (
            <GameCanvas
              map={state.local_map}
              selectedId={selected?.id ?? null}
              onSelect={onSelect}
              onNearby={setNearbyIds}
              onInteract={onInteract}
            />
          )}
          <div className="scene-status">
            <Footprints size={15} />
            <span>方向键 / WASD 移动</span>
            <span className="separator" />
            <span>E / 空格互动</span>
          </div>
          <div className="map-key" aria-label="地图图例">
            <span><i className="key-dot evidence" />证物</span>
            <span><i className="key-dot person" />知情人</span>
            <span><i className="key-dot resident" />居民</span>
            <span><i className="key-dot player" />玩家</span>
          </div>
          <div className="mobile-pad" aria-label="移动控制">
            <button title="向上" onClick={() => move(0, -1)}><ArrowUp /></button>
            <button title="向左" onClick={() => move(-1, 0)}><ArrowLeft /></button>
            <button title="互动" className="interact" onClick={interact}><Search /></button>
            <button title="向右" onClick={() => move(1, 0)}><ArrowRight /></button>
            <button title="向下" onClick={() => move(0, 1)}><ArrowDown /></button>
          </div>
        </section>

        <aside className="investigation-dock">
          <nav className="dock-tabs" aria-label="调查面板">
            <button className={dockTab === "inspect" ? "active" : ""} onClick={() => setDockTab("inspect")}>
              <Search size={16} /> 调查
            </button>
            <button className={dockTab === "people" ? "active" : ""} onClick={() => setDockTab("people")}>
              <Users size={16} /> 人物
            </button>
            <button className={dockTab === "journal" ? "active" : ""} onClick={() => setDockTab("journal")}>
              <BookOpen size={16} /> 游记
              <span className="count-badge">{journal?.counts.claims ?? 0}</span>
            </button>
          </nav>

          <div className="dock-content">
            {dockTab === "inspect" && (
              <InspectPanel
                selected={selectedEvidence}
                nearby={selectedIsNearby}
                examined={selectedEvidence ? examinedIds.has(selectedEvidence.id) : false}
                read={selectedEvidence ? readIds.has(selectedEvidence.id) : false}
                compareIds={compareIds}
                detail={detail}
                busy={busy}
                onExamine={(id) => void runAction({ action: "examine", evidence_id: id })}
                onRead={(id) => void runAction({ action: "read", evidence_id: id })}
                onToggleCompare={addToCompare}
                onCompare={() => void compare()}
                onClearDetail={() => setDetail(null)}
                entities={state?.local_map.entities ?? []}
              />
            )}
            {dockTab === "people" && (
              <PeoplePanel
                informants={state?.informants ?? []}
                residents={state?.local_map.entities.filter((item) => item.kind === "resident") ?? []}
                evidence={state?.local_map.entities.filter(
                  (item) => item.kind === "evidence" && examinedIds.has(item.id),
                ) ?? []}
                selected={selectedPerson}
                nearby={selectedIsNearby}
                activeEvidence={activeEvidence}
                examined={activeEvidence ? examinedIds.has(activeEvidence.id) : false}
                detail={detail}
                busy={busy}
                onSelect={(id) => {
                  const entity = state?.local_map.entities.find((item) => item.id === id);
                  if (entity) onSelect(entity);
                }}
                onSelectEvidence={setActiveEvidenceId}
                onConsult={(informantId) => {
                  if (activeEvidence) {
                    void runAction({
                      action: "consult",
                      evidence_id: activeEvidence.id,
                      informant_id: informantId,
                    });
                  }
                }}
                onTalk={(residentId) => {
                  void runAction({ action: "talk", resident_id: residentId });
                }}
              />
            )}
            {dockTab === "journal" && journal && (
              <JournalPanel journal={journal} tab={journalTab} onTab={setJournalTab} />
            )}
          </div>
        </aside>
      </main>

      {notice && (
        <div className="notice" role="alert">
          <Info size={16} />
          <span>{notice}</span>
          <button title="关闭" onClick={() => setNotice("")}><X size={15} /></button>
        </div>
      )}
      {(loading || busy) && (
        <div className={loading ? "loading-screen" : "busy-indicator"} role="status">
          <LoaderCircle className="spin" size={loading ? 28 : 16} />
          <span>{loading ? "正在生成世界与聚落地图…" : "正在整理调查结果…"}</span>
        </div>
      )}
    </div>
  );
}

function InspectPanel(props: {
  selected: MapEntity | null;
  nearby: boolean;
  examined: boolean;
  read: boolean;
  compareIds: string[];
  detail: ActionResult | null;
  busy: boolean;
  entities: MapEntity[];
  onExamine: (id: string) => void;
  onRead: (id: string) => void;
  onToggleCompare: (id: string) => void;
  onCompare: () => void;
  onClearDetail: () => void;
}) {
  const { selected, detail } = props;
  return (
    <>
      <section className="panel-heading">
        <p className="eyebrow">现场调查</p>
        <h2>{selected?.name ?? "选择一件证物"}</h2>
        <p>
          {selected
            ? `${TYPE_LABELS[selected.subtype] ?? selected.subtype} · ${MATERIAL_LABELS[selected.material] ?? selected.material} · ${selected.zone}`
            : "在地图中靠近并选择证物，客观观察才会写入游记。"}
        </p>
      </section>
      {selected && (
        <div className="command-row">
          <button className="command-button primary" disabled={!props.nearby || props.busy} onClick={() => props.onExamine(selected.id)}>
            <Search size={15} /> {props.examined ? "复查" : "检查"}
          </button>
          {selected.subtype === "document" && (
            <button className="command-button" disabled={!props.nearby || !props.examined || props.busy} onClick={() => props.onRead(selected.id)}>
              <FileText size={15} /> {props.read ? "重读" : "阅读"}
            </button>
          )}
          <button className={props.compareIds.includes(selected.id) ? "command-button selected" : "command-button"} disabled={!props.examined} onClick={() => props.onToggleCompare(selected.id)}>
            <Scale size={15} /> 比较栏
          </button>
        </div>
      )}
      {selected && !props.nearby && <p className="proximity-note">走到相邻格后才能检查或阅读。</p>}

      {props.compareIds.length > 0 && (
        <section className="compare-strip">
          <div>
            <span>比较栏</span>
            <strong>
              {props.compareIds
                .map((id) => props.entities.find((item) => item.id === id)?.name ?? id)
                .join(" / ")}
            </strong>
          </div>
          <button className="icon-command" title="执行比较" disabled={props.compareIds.length !== 2 || props.busy} onClick={props.onCompare}>
            <Scale size={17} />
          </button>
        </section>
      )}

      <ActionDetail detail={detail} onClose={props.onClearDetail} />
    </>
  );
}

function PeoplePanel(props: {
  informants: PlayerState["informants"];
  residents: MapEntity[];
  evidence: MapEntity[];
  selected: MapEntity | null;
  nearby: boolean;
  activeEvidence: MapEntity | null;
  examined: boolean;
  detail: ActionResult | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onSelectEvidence: (id: string | null) => void;
  onConsult: (id: string) => void;
  onTalk: (id: string) => void;
}) {
  const selectedInformant = props.selected?.kind === "informant";
  const selectedResident = props.selected?.kind === "resident";
  const informantRole = props.informants.find((item) => item.id === props.selected?.id)?.role_name;
  return (
    <>
      <section className="panel-heading">
        <p className="eyebrow">聚落居民</p>
        <h2>{props.selected?.name ?? "寻找可以请教的人"}</h2>
        <p>
          {selectedResident
            ? `${props.selected?.role_name} · ${props.selected?.zone}。${props.selected?.description_cn}`
            : props.activeEvidence
              ? `${informantRole ?? "知情人"} · 当前准备出示：${props.activeEvidence.name}`
              : "先检查一件证物，再走近合适的知情人。"}
        </p>
      </section>
      {!selectedResident && (
        <div className="evidence-picker">
          <label htmlFor="consult-evidence">
            <FileText size={15} /> 出示证物
          </label>
          <select
            id="consult-evidence"
            value={props.examined ? props.activeEvidence?.id ?? "" : ""}
            disabled={!props.evidence.length || props.busy}
            onChange={(event) => props.onSelectEvidence(event.target.value || null)}
          >
            <option value="">
              {props.evidence.length ? "选择一件已检查证物" : "尚无已检查证物"}
            </option>
            {props.evidence.map((item) => (
              <option value={item.id} key={item.id}>{item.name}</option>
            ))}
          </select>
        </div>
      )}
      <div className="people-list">
        <p className="people-section-label">可提供调查意见</p>
        {props.informants.map((person) => {
          const active = props.selected?.id === person.id;
          return (
            <button key={person.id} className={active ? "person-row active" : "person-row"} onClick={() => props.onSelect(person.id)}>
              <span className={`role-swatch role-${person.role}`} />
              <span><strong>{person.name}</strong><small>{person.role_name}</small></span>
              {active && props.nearby && <span className="nearby-mark">邻近</span>}
            </button>
          );
        })}
        <p className="people-section-label">普通居民</p>
        {props.residents.map((person) => {
          const active = props.selected?.id === person.id;
          return (
            <button key={person.id} className={active ? "person-row active" : "person-row"} onClick={() => props.onSelect(person.id)}>
              <span className="role-swatch ordinary" />
              <span><strong>{person.name}</strong><small>{person.role_name} · {person.zone}</small></span>
              {active && props.nearby && <span className="nearby-mark">邻近</span>}
            </button>
          );
        })}
      </div>
      {selectedInformant && (
        <div className="command-row sticky-actions">
          <button
            className="command-button primary"
            disabled={!props.nearby || !props.activeEvidence || !props.examined || props.busy}
            onClick={() => props.onConsult(props.selected!.id)}
          >
            <MessageSquareText size={15} /> 出示并请教
          </button>
        </div>
      )}
      {selectedResident && (
        <div className="command-row sticky-actions">
          <button
            className="command-button primary"
            disabled={!props.nearby || props.busy}
            onClick={() => props.onTalk(props.selected!.id)}
          >
            <MessageSquareText size={15} /> 打个招呼
          </button>
        </div>
      )}
      {props.selected && !props.nearby && <p className="proximity-note">走到人物相邻格后才能交谈。</p>}
      <ActionDetail detail={props.detail && ["consult", "talk"].includes(props.detail.action) ? props.detail : null} />
    </>
  );
}

function ActionDetail({ detail, onClose }: { detail: ActionResult | null; onClose?: () => void }) {
  if (!detail) {
    return (
      <section className="empty-detail">
        <Boxes size={25} />
        <p>调查结果会保留观察、原文和他人说法之间的区别。</p>
      </section>
    );
  }
  return (
    <section className="action-detail">
      <div className="section-title">
        <h3>{actionTitle(detail.action)}</h3>
        {onClose && <button className="icon-command quiet" title="关闭结果" onClick={onClose}><X size={15} /></button>}
      </div>
      {detail.description_cn && <p className="long-copy">{detail.description_cn}</p>}
      {detail.text_cn && <p className="long-copy reading-copy">{detail.text_cn}</p>}
      {detail.dialogue_cn && <blockquote>{detail.dialogue_cn}</blockquote>}
      {detail.observations && (
        <ul className="evidence-list">
          {detail.observations.map((item, index) => <li key={index}>{value(item, "description_cn")}</li>)}
        </ul>
      )}
      {detail.consultation && (
        <>
          {list(detail.consultation, "notes_cn").map((note, index) => <p key={`n-${index}`} className="long-copy">{String(note)}</p>)}
          {list(detail.consultation, "statements").map((statement, index) => {
            const item = statement as Record<string, unknown>;
            return <blockquote key={index}>{value(item, "statement_cn")}</blockquote>;
          })}
        </>
      )}
      {detail.comparison && (
        <>
          <ResultList title="相同点" values={list(detail.comparison, "similarities_cn")} />
          <ResultList title="差异点" values={list(detail.comparison, "differences_cn")} />
          <ResultList title="判断限制" values={list(detail.comparison, "limitations_cn")} muted />
        </>
      )}
    </section>
  );
}

function ResultList({ title, values, muted = false }: { title: string; values: unknown[]; muted?: boolean }) {
  return (
    <div className={muted ? "result-group muted" : "result-group"}>
      <h4>{title}</h4>
      {values.length ? <ul>{values.map((item, index) => <li key={index}>{String(item)}</li>)}</ul> : <p>没有记录。</p>}
    </div>
  );
}

function JournalPanel({ journal, tab, onTab }: { journal: Journal; tab: JournalTab; onTab: (tab: JournalTab) => void }) {
  const tabs: Array<[JournalTab, string]> = [
    ["observations", "观察"],
    ["texts", "原文"],
    ["statements", "证言"],
    ["claims", "主张"],
    ["conflicts", "冲突"],
  ];
  return (
    <>
      <section className="panel-heading journal-heading">
        <p className="eyebrow">调查日志</p>
        <h2>{journal.counts.examined} 件证物</h2>
        <p>{journal.counts.source_groups} 个独立来源组 · {journal.counts.comparisons} 次比较</p>
      </section>
      <div className="journal-tabs">
        {tabs.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => onTab(id)}>
            {label}<span>{journalCount(journal, id)}</span>
          </button>
        ))}
      </div>
      <div className="journal-list">
        <JournalEntries journal={journal} tab={tab} />
      </div>
    </>
  );
}

function JournalEntries({ journal, tab }: { journal: Journal; tab: JournalTab }) {
  if (tab === "observations") {
    return <Entries items={journal.observations} render={(item) => <><small>{journal.evidence_names[value(item, "evidence_id")] ?? "证物"}</small><p>{value(item, "description_cn")}</p></>} />;
  }
  if (tab === "texts") {
    return <Entries items={journal.readings} render={(item) => <><small>{journal.evidence_names[value(item, "evidence_id")] ?? "文书"}</small>{list(item, "visible_passages").map((line, index) => <blockquote key={index}>{String(line)}</blockquote>)}</>} />;
  }
  if (tab === "statements") {
    return <Entries items={journal.statements} render={(item) => <><small>{value(item, "speaker_type")}</small><p>{value(item, "statement_cn")}</p></>} />;
  }
  if (tab === "claims") {
    return <Entries items={journal.claims} render={(item) => <><small>{value(item, "status")} · {list(item, "source_groups").length} 个来源组</small><p>{value(item, "statement_cn")}</p><Confidence components={(item.confidence_components ?? {}) as Record<string, number>} /></>} />;
  }
  return <Entries items={journal.conflicts} render={(item) => <><small>强冲突 · 第 {list(item, "overlap_range").join("–")} 年</small><p>{value(item, "reason_cn")}</p></>} />;
}

function Entries({ items, render }: { items: Array<Record<string, unknown>>; render: (item: Record<string, unknown>) => React.ReactNode }) {
  if (!items.length) return <div className="empty-detail"><BookOpen size={23} /><p>这一栏还没有记录。</p></div>;
  return <>{items.map((item, index) => <article className="journal-entry" key={value(item, "id") || index}>{render(item)}</article>)}</>;
}

function Confidence({ components }: { components: Record<string, number> }) {
  const labels: Record<string, string> = {
    carrier_quality: "载体",
    directness: "直接性",
    expertise_match: "专业",
    comprehension: "理解",
    source_independence: "独立来源",
    contradiction: "冲突",
    bias_penalty: "立场",
    transmission_penalty: "传承",
  };
  const values = Object.entries(components).filter(([, amount]) => Math.abs(amount) >= 0.005);
  return <div className="confidence-row">{values.map(([key, amount]) => <span className={amount < 0 ? "negative" : "positive"} key={key}>{labels[key] ?? key} {amount > 0 ? "+" : ""}{Math.round(amount * 100)}%</span>)}</div>;
}

function journalCount(journal: Journal, tab: JournalTab) {
  const map: Record<JournalTab, number> = {
    observations: journal.counts.observations,
    texts: journal.counts.read,
    statements: journal.counts.statements,
    claims: journal.counts.claims,
    conflicts: journal.counts.conflicts,
  };
  return map[tab] ?? 0;
}

function actionTitle(action: string) {
  return { examine: "客观检查", read: "文书阅读", consult: "咨询记录", compare: "证物比较", talk: "街头闲谈" }[action] ?? "调查结果";
}

function move(dx: number, dy: number) {
  window.dispatchEvent(new CustomEvent("hf-move", { detail: { dx, dy } }));
}

function interact() {
  window.dispatchEvent(new CustomEvent("hf-interact"));
}
