import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BookOpen,
  Boxes,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cloud,
  CloudFog,
  CloudLightning,
  CloudRain,
  Eye,
  EyeOff,
  FileText,
  Footprints,
  Globe2,
  Info,
  Hourglass,
  LoaderCircle,
  MessageSquareText,
  MapPinned,
  Moon,
  RefreshCw,
  Scale,
  Search,
  Snowflake,
  Sun,
  Terminal,
  Users,
  Wind,
  X,
} from "lucide-react";
import { performAction, startSession } from "./api";
import GameCanvas from "./GameCanvas";
import ItemPixelArt from "./ItemPixelArt";
import LocalMiniMap from "./LocalMiniMap";
import WorldMapView from "./WorldMapView";
import type { ActionResult, Journal, LibraryBook, MapEntity, PlayerState, RuntimeState } from "./types";
import {
  advanceTutorial,
  applyTutorialEvent,
  defaultTutorialProgress,
  loadTutorialProgress,
  retreatTutorial,
  saveTutorialProgress,
  TUTORIAL_CHAPTERS,
  type TutorialEvent,
  type TutorialProgress,
} from "./tutorial";

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
type ViewMode = "world" | "local";

function value(item: Record<string, unknown>, key: string) {
  return String(item[key] ?? "");
}

function list(item: Record<string, unknown>, key: string) {
  const result = item[key];
  return Array.isArray(result) ? result : [];
}

function EnvironmentGlyph({ weather }: { weather: RuntimeState["environment"]["weather"] }) {
  if (weather === "cloudy") return <Cloud size={17} />;
  if (weather === "rain") return <CloudRain size={17} />;
  if (weather === "storm") return <CloudLightning size={17} />;
  if (weather === "fog") return <CloudFog size={17} />;
  if (weather === "snow") return <Snowflake size={17} />;
  if (weather === "dust") return <Wind size={17} />;
  return <Sun size={17} />;
}

export default function App() {
  const [seed, setSeed] = useState(42);
  const [years, setYears] = useState(30);
  const [sessionId, setSessionId] = useState("");
  const [state, setState] = useState<PlayerState | null>(null);
  const [runtime, setRuntime] = useState<RuntimeState | null>(null);
  const [journal, setJournal] = useState<Journal | null>(null);
  const [selected, setSelected] = useState<MapEntity | null>(null);
  const [activeEvidenceId, setActiveEvidenceId] = useState<string | null>(null);
  const [nearbyIds, setNearbyIds] = useState<string[]>([]);
  const [examinedIds, setExaminedIds] = useState<Set<string>>(new Set());
  const [readIds, setReadIds] = useState<Set<string>>(new Set());
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [libraryBooks, setLibraryBooks] = useState<LibraryBook[]>([]);
  const [dockTab, setDockTab] = useState<DockTab>("inspect");
  const [journalTab, setJournalTab] = useState<JournalTab>("observations");
  const [detail, setDetail] = useState<ActionResult | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("local");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [cheatDialogOpen, setCheatDialogOpen] = useState(false);
  const [cheatCode, setCheatCode] = useState("");
  const [tutorialProgress, setTutorialProgress] = useState(loadTutorialProgress);
  const [tutorialOpen, setTutorialOpen] = useState(
    () => !loadTutorialProgress().completed,
  );
  const started = useRef(false);

  useEffect(() => {
    saveTutorialProgress(tutorialProgress);
  }, [tutorialProgress]);

  const recordTutorialEvent = useCallback((event: TutorialEvent) => {
    if (!tutorialOpen) return;
    setTutorialProgress((current) => applyTutorialEvent(current, event));
  }, [tutorialOpen]);

  const createWorld = useCallback(async () => {
    setLoading(true);
    setNotice("");
    try {
      const response = await startSession(seed, years);
      setSessionId(response.session_id);
      setState(response.state);
      setRuntime(response.state.runtime);
      setJournal(response.state.journal);
      setSelected(null);
      setActiveEvidenceId(null);
      setExaminedIds(new Set());
      setReadIds(new Set());
      setCompareIds([]);
      setLibraryBooks([]);
      setDetail(null);
      setDockTab("inspect");
      setViewMode("local");
      setCheatDialogOpen(false);
      setCheatCode("");
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
        if (result.runtime) setRuntime(result.runtime);
        if (result.library_books) setLibraryBooks(result.library_books);
        if (result.local_map) {
          setState((current) => current ? {
            ...current,
            local_map: result.local_map!,
          } : current);
          setSelected((current) => {
            if (!current) return current;
            return result.local_map!.entities.find((item) => item.id === current.id)
              ?? result.local_map!.discovered_evidence.find((item) => item.id === current.id)
              ?? null;
          });
        }
        if (!["wait", "journal"].includes(String(payload.action))) setDetail(result);
        if (payload.action === "examine") {
          const id = String(payload.evidence_id);
          setExaminedIds((current) => new Set(current).add(id));
          setActiveEvidenceId(id);
        }
        if (payload.action === "read") {
          setReadIds((current) => new Set(current).add(String(payload.evidence_id)));
        }
        if (["examine", "read", "search_container", "browse_bookshelf", "read_library_book", "consult", "talk", "inspect_wilderness"].includes(String(payload.action))) {
          recordTutorialEvent("investigate");
        }
        return result;
      } catch (error) {
        setNotice(error instanceof Error ? error.message : "调查动作失败");
        return null;
      } finally {
        setBusy(false);
      }
    },
    [recordTutorialEvent, sessionId],
  );

  const movePlayer = useCallback(async (dx: number, dy: number) => {
    if (!sessionId) return null;
    try {
      const result = await performAction(sessionId, { action: "move", dx, dy });
      if (result.location && result.world_map) {
        setState((current) => current ? {
          ...current,
          ...result.location,
          world_map: result.world_map!,
        } : current);
        setSelected(null);
        setActiveEvidenceId(null);
        setNearbyIds([]);
        setCompareIds([]);
        setLibraryBooks([]);
        setDetail(null);
      } else if (result.local_map) {
        setState((current) => current ? {
          ...current,
          local_map: result.local_map!,
        } : current);
        setSelected(null);
        setNearbyIds([]);
      }
      if (result.runtime) setRuntime(result.runtime);
      recordTutorialEvent("move");
      return result.runtime ?? null;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "无法移动");
      return null;
    }
  }, [recordTutorialEvent, sessionId]);

  const travelTo = useCallback(async (destinationId: string) => {
    if (!sessionId) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await performAction(sessionId, {
        action: "travel",
        destination_id: destinationId,
      });
      if (!result.location || !result.world_map) return;
      setState((current) => current ? {
        ...current,
        ...result.location,
        world_map: result.world_map!,
      } : current);
      setRuntime(result.location.runtime);
      setSelected(null);
      setActiveEvidenceId(null);
      setNearbyIds([]);
      setCompareIds([]);
      setLibraryBooks([]);
      setDetail(null);
      setDockTab("inspect");
      setViewMode("local");
      setNotice(`已抵达${result.destination?.name ?? "目的地"}。`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "旅行失败");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const onSelect = useCallback((entity: MapEntity) => {
    setSelected(entity);
    setDockTab(["informant", "resident"].includes(entity.kind) ? "people" : "inspect");
    if (entity.kind === "evidence") setActiveEvidenceId(entity.id);
    if (entity.kind !== "bookshelf") setLibraryBooks([]);
    recordTutorialEvent("select_entity");
  }, [recordTutorialEvent]);

  const onInteract = useCallback(
    (entity: MapEntity | null) => {
      if (!entity) {
        setNotice("附近没有可以互动的对象。靠近调查地点或人物后再试。");
        return;
      }
      onSelect(entity);
      if (entity.kind === "container") {
        void runAction({ action: "search_container", container_id: entity.id });
      } else if (entity.kind === "bookshelf") {
        void runAction({ action: "browse_bookshelf", shelf_id: entity.id });
      } else if (entity.kind === "evidence" && !examinedIds.has(entity.id)) {
        void runAction({ action: "examine", evidence_id: entity.id });
      } else if (["landmark", "camp", "caravan", "traveler", "trace", "wildlife"].includes(entity.kind)) {
        void runAction({ action: "inspect_wilderness", entity_id: entity.id });
      }
    },
    [examinedIds, onSelect, runAction],
  );

  const selectedIsNearby = selected ? (
    selected.kind === "evidence" && runtime
      ? Math.abs(selected.x - runtime.player.x) + Math.abs(selected.y - runtime.player.y) <= 1
      : nearbyIds.includes(selected.id)
  ) : false;
  const selectedEvidence = selected?.kind === "evidence" ? selected : null;
  const selectedContainer = selected?.kind === "container" ? selected : null;
  const selectedBookshelf = selected?.kind === "bookshelf" ? selected : null;
  const selectedWilderness = selected && ["landmark", "camp", "caravan", "traveler", "trace", "wildlife"].includes(selected.kind) ? selected : null;
  const selectedPerson = selected && ["informant", "resident"].includes(selected.kind) ? selected : null;
  const activeEvidence = useMemo(
    () => state?.local_map.discovered_evidence.find((item) => item.id === activeEvidenceId) ?? null,
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

  const submitCheatCode = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!sessionId || !cheatCode.trim()) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await performAction(sessionId, {
        action: "enter_cheat",
        code: cheatCode,
      });
      if (result.cheats) {
        setState((current) => current ? { ...current, cheats: result.cheats! } : current);
      }
      if (result.runtime) setRuntime(result.runtime);
      setCheatCode("");
      setNotice("作弊码已接受。全图视野选项已解锁。");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "作弊码无效");
    } finally {
      setBusy(false);
    }
  };

  const setFullMapVision = async (enabled: boolean) => {
    if (!sessionId) return;
    setBusy(true);
    setNotice("");
    try {
      const result = await performAction(sessionId, {
        action: "set_cheat",
        cheat_id: "full_map_vision",
        enabled,
      });
      if (result.cheats) {
        setState((current) => current ? { ...current, cheats: result.cheats! } : current);
      }
      if (result.runtime) setRuntime(result.runtime);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "无法切换作弊选项");
    } finally {
      setBusy(false);
    }
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
            <nav className="view-switch" aria-label="地图层级">
              <button className={`${viewMode === "world" ? "active" : ""}${tutorialOpen && TUTORIAL_CHAPTERS[tutorialProgress.chapterIndex].steps[tutorialProgress.stepIndex].target === "world" ? " tutorial-focus" : ""}`} onClick={() => {
                setViewMode("world");
                recordTutorialEvent("open_world");
              }}>
                <Globe2 size={14} /> 世界
              </button>
              <button className={viewMode === "local" ? "active" : ""} onClick={() => setViewMode("local")}>
                <MapPinned size={14} /> 当地
              </button>
            </nav>
            <span>{state.settlement
              ? `${state.settlement.name} · ${state.local_map.site_type === "ruin" ? "废墟" : BIOME_LABELS[state.settlement.biome] ?? state.settlement.biome}`
              : `${state.local_map.profile.landscape_name} · 荒野 (${state.local_map.cell.x}, ${state.local_map.cell.y})`}</span>
          </div>
        )}
        <div className="world-settings">
          {runtime && (
            <div className="clock-readout" title="本地时间">
              {runtime.environment.daylight === "day"
                || runtime.environment.daylight === "dawn"
                ? <Clock3 size={17} /> : <Moon size={17} />}
              <span><strong>{runtime.time_label}</strong><small>第 {runtime.day} 日 · {runtime.period_name}</small></span>
            </div>
          )}
          {runtime && (
            <div
              className="environment-readout"
              title={runtime.full_map_vision
                ? "全图视野已开启"
                : `${runtime.environment.daylight_name}，${runtime.environment.weather_name}，可见 ${runtime.environment.visibility_radius} 格`}
            >
              <EnvironmentGlyph weather={runtime.environment.weather} />
              <span>
                <strong>{runtime.environment.weather_name}</strong>
                <small><Eye size={10} /> {runtime.full_map_vision
                  ? "全图视野"
                  : `${runtime.environment.daylight_name} · ${runtime.environment.visibility_radius} 格`}</small>
              </span>
            </div>
          )}
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
          <button className="icon-command" title="等待 10 分钟" onClick={() => void runAction({ action: "wait", minutes: 10 })} disabled={loading || busy}>
            <Hourglass size={18} />
          </button>
          <button className="icon-command" title="作弊码控制台" onClick={() => setCheatDialogOpen(true)} disabled={loading || busy}>
            <Terminal size={18} />
          </button>
          <button
            className={`icon-command${tutorialOpen ? " selected" : ""}`}
            title="新手教程"
            aria-pressed={tutorialOpen}
            onClick={() => {
              if (tutorialProgress.completed) setTutorialProgress(defaultTutorialProgress());
              setTutorialOpen((current) => !current || tutorialProgress.completed);
            }}
            disabled={loading}
          >
            <CircleHelp size={18} />
          </button>
          {state?.cheats.full_map_vision.unlocked && (
            <button
              className={`icon-command cheat-quick-toggle${state.cheats.full_map_vision.enabled ? " selected" : ""}`}
              title={state.cheats.full_map_vision.enabled ? "关闭全图视野" : "开启全图视野"}
              aria-pressed={state.cheats.full_map_vision.enabled}
              onClick={() => void setFullMapVision(!state.cheats.full_map_vision.enabled)}
              disabled={loading || busy}
            >
              {state.cheats.full_map_vision.enabled ? <Eye size={18} /> : <EyeOff size={18} />}
            </button>
          )}
        </div>
      </header>

      {state && viewMode === "world" ? (
        <WorldMapView map={state.world_map} busy={busy} onTravel={(id) => void travelTo(id)} />
      ) : (
      <main className="workspace">
        <section className={`scene-pane${tutorialOpen && TUTORIAL_CHAPTERS[tutorialProgress.chapterIndex].steps[tutorialProgress.stepIndex].target === "scene" ? " tutorial-focus" : ""}`} aria-label="当前聚落">
          {state && runtime && (
            <>
              <GameCanvas
                map={state.local_map}
                runtime={runtime}
                selectedId={selected?.id ?? null}
                onSelect={onSelect}
                onNearby={setNearbyIds}
                onInteract={onInteract}
                onMove={movePlayer}
              />
              <LocalMiniMap map={state.local_map} runtime={runtime} />
            </>
          )}
          <div className="scene-status">
            <Footprints size={15} />
            <span>方向键 / WASD 移动</span>
            <span className="separator" />
            <span>E / 空格互动</span>
          </div>
          <div className="map-key" aria-label="地图图例">
            <span><i className="key-dot storage" />存储设施</span>
            <span><i className="key-dot evidence" />现场证据</span>
            <span><i className="key-dot person" />知情人</span>
            <span><i className="key-dot resident" />居民</span>
            <span><i className="key-dot landmark" />路标、圣所与陈设</span>
            <span><i className="key-dot trace" />活动痕迹</span>
            <span><i className="key-dot wildlife" />野生动物</span>
            <span><i className="key-dot caravan" />商队</span>
            <span><i className="key-dot traveler" />道路行人</span>
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

        <aside className={`investigation-dock${tutorialOpen && TUTORIAL_CHAPTERS[tutorialProgress.chapterIndex].steps[tutorialProgress.stepIndex].target === "investigation" ? " tutorial-focus" : ""}`}>
          <nav className="dock-tabs" aria-label="调查面板">
            <button className={dockTab === "inspect" ? "active" : ""} onClick={() => setDockTab("inspect")}>
              <Search size={16} /> 调查
            </button>
            <button className={dockTab === "people" ? "active" : ""} onClick={() => setDockTab("people")}>
              <Users size={16} /> 人物
            </button>
            <button className={`${dockTab === "journal" ? "active" : ""}${tutorialOpen && TUTORIAL_CHAPTERS[tutorialProgress.chapterIndex].steps[tutorialProgress.stepIndex].target === "journal" ? " tutorial-focus" : ""}`} onClick={() => {
              setDockTab("journal");
              recordTutorialEvent("open_journal");
            }}>
              <BookOpen size={16} /> 游记
              <span className="count-badge">{journal?.counts.claims ?? 0}</span>
            </button>
          </nav>

          <div className="dock-content">
            {dockTab === "inspect" && (
              <InspectPanel
                selected={selectedEvidence ?? selectedContainer ?? selectedBookshelf ?? selectedWilderness}
                nearby={selectedIsNearby}
                examined={selectedEvidence ? examinedIds.has(selectedEvidence.id) : false}
                read={selectedEvidence ? readIds.has(selectedEvidence.id) : false}
                compareIds={compareIds}
                detail={detail}
                busy={busy}
                evidence={state?.local_map.discovered_evidence ?? []}
                libraryBooks={libraryBooks}
                onSelect={onSelect}
                onSearch={(id) => void runAction({ action: "search_container", container_id: id })}
                onBrowseBookshelf={(id) => void runAction({ action: "browse_bookshelf", shelf_id: id })}
                onReadLibraryBook={(id) => void runAction({ action: "read_library_book", book_id: id })}
                onExamine={(id) => void runAction({ action: "examine", evidence_id: id })}
                onRead={(id) => void runAction({ action: "read", evidence_id: id })}
                onInspectWilderness={(id) => void runAction({ action: "inspect_wilderness", entity_id: id })}
                onToggleCompare={addToCompare}
                onCompare={() => void compare()}
                onClearDetail={() => setDetail(null)}
                entities={state?.local_map.discovered_evidence ?? []}
              />
            )}
            {dockTab === "people" && (
              <PeoplePanel
                informants={state?.informants ?? []}
                residents={state?.local_map.entities.filter((item) => item.kind === "resident") ?? []}
                evidence={state?.local_map.discovered_evidence.filter(
                  (item) => examinedIds.has(item.id),
                ) ?? []}
                runtime={runtime}
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
      )}

      {cheatDialogOpen && state && (
        <div className="cheat-backdrop" role="presentation" onMouseDown={() => setCheatDialogOpen(false)}>
          <section className="cheat-dialog" role="dialog" aria-modal="true" aria-labelledby="cheat-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div>
                <small>系统控制台</small>
                <h2 id="cheat-dialog-title">作弊码</h2>
              </div>
              <button className="icon-command quiet" title="关闭" onClick={() => setCheatDialogOpen(false)}><X size={16} /></button>
            </header>
            <form className="cheat-code-form" onSubmit={(event) => void submitCheatCode(event)}>
              <label htmlFor="cheat-code">输入作弊码</label>
              <div>
                <input id="cheat-code" value={cheatCode} onChange={(event) => setCheatCode(event.target.value)} autoComplete="off" spellCheck={false} autoFocus />
                <button className="command-button primary" type="submit" disabled={busy || !cheatCode.trim()}><Terminal size={15} /> 提交</button>
              </div>
            </form>
            {state.cheats.full_map_vision.unlocked && (
              <label className="cheat-option">
                <span><Eye size={18} /><strong>全图视野</strong></span>
                <input
                  type="checkbox"
                  checked={state.cheats.full_map_vision.enabled}
                  onChange={(event) => void setFullMapVision(event.target.checked)}
                  disabled={busy}
                />
              </label>
            )}
          </section>
        </div>
      )}

      {tutorialOpen && state && (
        <TutorialPanel
          progress={tutorialProgress}
          onBack={() => setTutorialProgress((current) => retreatTutorial(current))}
          onNext={() => {
            const next = advanceTutorial(tutorialProgress);
            setTutorialProgress(next);
            if (next.completed) setTutorialOpen(false);
          }}
          onClose={() => setTutorialOpen(false)}
          onSkip={() => {
            setTutorialProgress((current) => ({ ...current, completed: true }));
            setTutorialOpen(false);
          }}
        />
      )}

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

function TutorialPanel({
  progress,
  onBack,
  onNext,
  onClose,
  onSkip,
}: {
  progress: TutorialProgress;
  onBack: () => void;
  onNext: () => void;
  onClose: () => void;
  onSkip: () => void;
}) {
  const chapter = TUTORIAL_CHAPTERS[progress.chapterIndex];
  const step = chapter.steps[progress.stepIndex];
  const isFirst = progress.chapterIndex === 0 && progress.stepIndex === 0;
  const isLast = progress.chapterIndex === TUTORIAL_CHAPTERS.length - 1
    && progress.stepIndex === chapter.steps.length - 1;
  const completedSteps = TUTORIAL_CHAPTERS
    .slice(0, progress.chapterIndex)
    .reduce((total, item) => total + item.steps.length, 0) + progress.stepIndex;
  const totalSteps = TUTORIAL_CHAPTERS.reduce(
    (total, item) => total + item.steps.length,
    0,
  );

  return (
    <section className="tutorial-panel" aria-live="polite" aria-label="新手教程">
      <header>
        <div>
          <small>{chapter.title} · {completedSteps + 1}/{totalSteps}</small>
          <h2>{step.title}</h2>
        </div>
        <button className="icon-command quiet" title="暂时收起教程" onClick={onClose}><X size={16} /></button>
      </header>
      <div className="tutorial-progress" aria-hidden="true">
        <span style={{ width: `${((completedSteps + 1) / totalSteps) * 100}%` }} />
      </div>
      <p>{step.body}</p>
      {step.completionEvent && <small className="tutorial-condition">完成当前操作后自动继续</small>}
      <footer>
        <button className="tutorial-skip" onClick={onSkip}>跳过教程</button>
        <div>
          <button className="icon-command" title="上一步" onClick={onBack} disabled={isFirst}><ChevronLeft size={16} /></button>
          <button className="command-button primary" onClick={onNext}>
            {step.completionEvent ? "跳过此步" : isLast ? <><Check size={15} /> 完成</> : <>继续 <ChevronRight size={15} /></>}
          </button>
        </div>
      </footer>
    </section>
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
  evidence: MapEntity[];
  libraryBooks: LibraryBook[];
  entities: MapEntity[];
  onSelect: (entity: MapEntity) => void;
  onSearch: (id: string) => void;
  onBrowseBookshelf: (id: string) => void;
  onReadLibraryBook: (id: string) => void;
  onExamine: (id: string) => void;
  onRead: (id: string) => void;
  onInspectWilderness: (id: string) => void;
  onToggleCompare: (id: string) => void;
  onCompare: () => void;
  onClearDetail: () => void;
}) {
  const { selected, detail } = props;
  const [catalogQuery, setCatalogQuery] = useState("");
  const [catalogGenre, setCatalogGenre] = useState("all");
  const isContainer = selected?.kind === "container";
  const isBookshelf = selected?.kind === "bookshelf";
  const isWilderness = Boolean(
    selected && ["landmark", "camp", "caravan", "traveler", "trace", "wildlife"].includes(selected.kind));
  const visibleEvidence = isContainer
    ? props.evidence.filter((item) => item.container_id === selected.id)
    : props.evidence;
  const normalizedQuery = catalogQuery.trim().toLocaleLowerCase();
  const visibleBooks = props.libraryBooks.filter((book) => (
    (catalogGenre === "all" || book.genre === catalogGenre)
    && (!normalizedQuery || `${book.title} ${book.author_name} ${book.genre_name}`.toLocaleLowerCase().includes(normalizedQuery))
  ));
  const catalogGenres = Array.from(new Map(
    props.libraryBooks.map((book) => [book.genre, book.genre_name]),
  ).entries());
  return (
    <>
      <section className="panel-heading">
        <p className="eyebrow">现场调查</p>
        <h2>{selected?.name ?? "选择调查地点"}</h2>
        <p>
          {isWilderness
            ? `${selected?.role_name} · ${selected?.zone}${selected?.wear_name
              ? ` · ${selected.wear_name} · ${selected.repair_name}${selected.repair_error_type !== "none"
                ? ` · ${selected.repair_error_name}`
                : ""}`
              : ""}。${selected?.description_cn}`
            : isContainer || isBookshelf
            ? `${selected.role_name} · ${selected.condition}。${selected.description_cn}`
            : selected
            ? `${TYPE_LABELS[selected.subtype] ?? selected.subtype} · ${MATERIAL_LABELS[selected.material] ?? selected.material} · ${selected.zone}`
            : "靠近地图上的存储地点进行搜索，找到的材料会进入调查目录。"}
        </p>
      </section>
      {selected?.kind === "evidence" && selected.description_cn && (
        <p className="plain-sight-copy">{selected.description_cn}</p>
      )}
      {isContainer && (
        <div className="command-row">
          <button className="command-button primary" disabled={!props.nearby || props.busy} onClick={() => props.onSearch(selected.id)}>
            <Search size={15} /> {selected.searched ? "重新搜索" : "搜索此处"}
          </button>
        </div>
      )}
      {isBookshelf && selected && (
        <div className="command-row">
          <button className="command-button primary" disabled={!props.nearby || props.busy} onClick={() => props.onBrowseBookshelf(selected.id)}>
            <BookOpen size={15} /> {props.libraryBooks.length ? "刷新目录" : `浏览 ${selected.book_count ?? 0} 册馆藏`}
          </button>
        </div>
      )}
      {isWilderness && selected && (
        <div className="command-row">
          <button className="command-button primary" disabled={!props.nearby || props.busy} onClick={() => props.onInspectWilderness(selected.id)}>
            <Search size={15} /> {selected.kind === "caravan"
              ? "与领队交谈"
              : selected.kind === "traveler" ? "与行人交谈"
              : selected.kind === "wildlife" ? "观察动物" : "查看此处"}
          </button>
        </div>
      )}
      {selected?.kind === "evidence" && (
        <div className="command-row">
          <button className="command-button primary" disabled={!props.nearby || props.busy} onClick={() => props.onExamine(selected.id)}>
            <Search size={15} /> {props.examined ? "复查" : "检查"}
          </button>
          {selected.can_read && (
            <button className="command-button" disabled={!props.nearby || (!props.examined && !selected.quick_read) || props.busy} onClick={() => props.onRead(selected.id)}>
              <FileText size={15} /> {props.read ? "重读" : selected.quick_read ? "阅读铭文" : "阅读"}
            </button>
          )}
          <button className={props.compareIds.includes(selected.id) ? "command-button selected" : "command-button"} disabled={!props.examined} onClick={() => props.onToggleCompare(selected.id)}>
            <Scale size={15} /> 比较栏
          </button>
        </div>
      )}
      {selected && !props.nearby && (
        <p className="proximity-note">
          {isBookshelf ? "走到书架相邻格后才能浏览和阅读。" : isContainer ? "走到调查地点相邻格后才能搜索。" : "返回证物存放地点旁才能检查或阅读。"}
        </p>
      )}

      {isBookshelf && props.libraryBooks.length > 0 && (
        <section className="library-catalog">
          <div className="section-title">
            <h3>书架目录</h3>
            <span>{visibleBooks.length}/{props.libraryBooks.length}</span>
          </div>
          <div className="catalog-filters">
            <label>
              <Search size={14} />
              <input value={catalogQuery} onChange={(event) => setCatalogQuery(event.target.value)} placeholder="检索书名、作者或主题" />
            </label>
            <select value={catalogGenre} onChange={(event) => setCatalogGenre(event.target.value)} aria-label="按主题筛选">
              <option value="all">全部主题</option>
              {catalogGenres.map(([id, name]) => <option value={id} key={id}>{name}</option>)}
            </select>
          </div>
          <div className="library-book-list">
            {visibleBooks.map((book) => (
              <div className="library-book-row" key={book.id}>
                <BookOpen size={17} />
                <span>
                  <strong>{book.title}</strong>
                  <small>{book.genre_name} · {book.author_name} · 第 {book.catalog_number} 号</small>
                </span>
                <button className="command-button" disabled={props.busy} onClick={() => props.onReadLibraryBook(book.id)}>阅读</button>
              </div>
            ))}
            {!visibleBooks.length && <p className="catalog-empty">没有符合当前条件的书目。</p>}
          </div>
        </section>
      )}

      {!isWilderness && !isBookshelf && <section className="discovered-catalog">
        <div className="section-title">
          <h3>{isContainer ? "此处已发现的材料" : "已发现证物"}</h3>
          <span>{visibleEvidence.length}</span>
        </div>
        {visibleEvidence.length ? (
          <div className="discovered-list">
            {visibleEvidence.map((item) => (
              <button
                key={item.id}
                className={selected?.id === item.id ? "discovered-row active" : "discovered-row"}
                onClick={() => props.onSelect(item)}
              >
                <span><strong>{item.name}</strong><small>{TYPE_LABELS[item.subtype] ?? item.subtype} · {item.storage_position || item.zone}</small></span>
                {props.examined && selected?.id === item.id && <span className="nearby-mark">已检查</span>}
              </button>
            ))}
          </div>
        ) : (
          <p className="catalog-empty">
            {isContainer && !selected.searched ? "这里尚未搜索。" : "尚未在这里发现可登记的实体证物。"}
          </p>
        )}
      </section>}

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
  runtime: RuntimeState | null;
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
  const selectedInformantProfile = props.informants.find(
    (item) => item.id === props.selected?.id,
  );
  const informantRole = selectedInformantProfile?.presence_label;
  const selectedActivity = props.runtime?.npcs.find(
    (item) => item.id === props.selected?.id,
  )?.activity_name;
  return (
    <>
      <section className="panel-heading">
        <p className="eyebrow">聚落居民与访客</p>
        <h2>{props.selected?.name ?? "寻找可以请教的人"}</h2>
        <p>
          {selectedResident
            ? `${props.selected?.role_name} · ${selectedActivity ?? props.selected?.zone}。${props.selected?.description_cn}`
            : props.activeEvidence
              ? `${informantRole ?? "知情人"} · ${selectedActivity ?? "在聚落中"} · 当前准备出示：${props.activeEvidence.name}`
              : selectedInformantProfile
                ? `${selectedInformantProfile.presence_label} · ${selectedActivity ?? "在聚落中"}`
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
          const activity = props.runtime?.npcs.find((item) => item.id === person.id)?.activity_name;
          return (
            <button key={person.id} className={active ? "person-row active" : "person-row"} onClick={() => props.onSelect(person.id)}>
              <span className={`role-swatch role-${person.role}`} />
              <span><strong>{person.name}</strong><small>{person.presence_label} · {activity ?? "在聚落中"}</small></span>
              {active && props.nearby && <span className="nearby-mark">邻近</span>}
            </button>
          );
        })}
        <p className="people-section-label">普通居民</p>
        {props.residents.map((person) => {
          const active = props.selected?.id === person.id;
          const activity = props.runtime?.npcs.find((item) => item.id === person.id)?.activity_name;
          return (
            <button key={person.id} className={active ? "person-row active" : "person-row"} onClick={() => props.onSelect(person.id)}>
              <span className="role-swatch ordinary" />
              <span><strong>{person.name}</strong><small>{person.role_name} · {activity ?? person.zone}</small></span>
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
  const evidence = detail.evidence && !Array.isArray(detail.evidence) ? detail.evidence : null;
  return (
    <section className="action-detail">
      <div className="section-title">
        <h3>{actionTitle(detail.action)}</h3>
        {onClose && <button className="icon-command quiet" title="关闭结果" onClick={onClose}><X size={15} /></button>}
      </div>
      {detail.action === "examine" && detail.item_visual && evidence && (
        <ItemPixelArt profile={detail.item_visual} label={value(evidence, "observed_name") || "未识别物件"} />
      )}
      {detail.description_cn && <p className="long-copy">{detail.description_cn}</p>}
      {detail.text_cn && <p className="long-copy reading-copy">{detail.text_cn}</p>}
      {detail.action === "read_library_book" && detail.readability_ratio != null && (
        <div className="book-condition" role="status">
          <span>可读内容 {Math.round(detail.readability_ratio * 100)}%</span>
          {detail.damage_labels?.map((label) => <span key={label}>{label}</span>)}
        </div>
      )}
      {detail.library_sections && (
        <div className="book-sections">
          {detail.library_sections.map((section, index) => (
            <section className={section.status === "missing" ? "missing" : section.status === "damaged" ? "damaged" : ""} key={`${section.heading}-${index}`}>
              <h4>{section.heading}</h4>
              <p>{section.text}</p>
            </section>
          ))}
        </div>
      )}
      {detail.dialogue_cn && <blockquote>{detail.dialogue_cn}</blockquote>}
      {detail.discovered_evidence && detail.action === "search_container" && (
        <ul className="evidence-list">
          {detail.discovered_evidence.map((item) => (
            <li key={item.id}>{item.name}<small>{TYPE_LABELS[item.subtype] ?? item.subtype} · {item.storage_position || item.zone}</small></li>
          ))}
        </ul>
      )}
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
  return { examine: "客观检查", read: "文书阅读", browse_bookshelf: "馆藏目录", read_library_book: "馆藏阅读", consult: "咨询记录", compare: "证物比较", talk: "街头闲谈", inspect_wilderness: "荒野见闻" }[action] ?? "调查结果";
}

function move(dx: number, dy: number) {
  window.dispatchEvent(new CustomEvent("hf-move", { detail: { dx, dy } }));
}

function interact() {
  window.dispatchEvent(new CustomEvent("hf-interact"));
}
