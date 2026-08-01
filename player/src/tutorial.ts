export type TutorialEvent =
  | "move"
  | "select_entity"
  | "investigate"
  | "open_journal"
  | "open_world";

export type TutorialTarget =
  | "scene"
  | "investigation"
  | "journal"
  | "world";

export type TutorialStep = {
  id: string;
  title: string;
  body: string;
  target?: TutorialTarget;
  completionEvent?: TutorialEvent;
};

export type TutorialChapter = {
  id: string;
  title: string;
  steps: TutorialStep[];
};

export type TutorialProgress = {
  version: number;
  chapterIndex: number;
  stepIndex: number;
  completed: boolean;
};

export const TUTORIAL_VERSION = 1;
export const TUTORIAL_STORAGE_KEY = "historyfinder.tutorial.v1";

export const TUTORIAL_CHAPTERS: TutorialChapter[] = [
  {
    id: "field-basics",
    title: "初次田野调查",
    steps: [
      {
        id: "welcome",
        title: "从现场开始",
        body: "你将先熟悉当地地图，再把观察带到更广阔的世界中。教程不会限制任何操作。",
      },
      {
        id: "move",
        title: "接近调查对象",
        body: "在当地地图中移动一步。寻找存储设施、现场证据、人物或荒野痕迹。",
        target: "scene",
        completionEvent: "move",
      },
      {
        id: "select",
        title: "选择现场目标",
        body: "点击地图中的一个对象。右侧调查面板会显示它的身份、状态和可用操作。",
        target: "investigation",
        completionEvent: "select_entity",
      },
      {
        id: "investigate",
        title: "取得一项观察",
        body: "走到目标附近并执行一次检查、搜索、交谈或荒野观察。",
        target: "investigation",
        completionEvent: "investigate",
      },
      {
        id: "journal",
        title: "查看调查记录",
        body: "打开游记。观察、文本、证词和推断会按来源持续积累。",
        target: "journal",
        completionEvent: "open_journal",
      },
      {
        id: "world",
        title: "查看世界地图",
        body: "切换到世界地图，查看聚落、遗址、道路与河流。选择目的地后可以开始旅行。",
        target: "world",
        completionEvent: "open_world",
      },
      {
        id: "complete",
        title: "准备继续调查",
        body: "基础教程已完成。你可以随时通过顶部的问号按钮重新开始；后续章节也会从这里接入。",
      },
    ],
  },
];

export function defaultTutorialProgress(): TutorialProgress {
  return { version: TUTORIAL_VERSION, chapterIndex: 0, stepIndex: 0, completed: false };
}

export function loadTutorialProgress(): TutorialProgress {
  try {
    const stored = window.localStorage.getItem(TUTORIAL_STORAGE_KEY);
    if (!stored) return defaultTutorialProgress();
    const value = JSON.parse(stored) as Partial<TutorialProgress>;
    if (value.version !== TUTORIAL_VERSION) return defaultTutorialProgress();
    const chapterIndex = Math.max(0, Math.min(
      Number(value.chapterIndex) || 0,
      TUTORIAL_CHAPTERS.length - 1,
    ));
    const stepIndex = Math.max(0, Math.min(
      Number(value.stepIndex) || 0,
      TUTORIAL_CHAPTERS[chapterIndex].steps.length - 1,
    ));
    return {
      version: TUTORIAL_VERSION,
      chapterIndex,
      stepIndex,
      completed: Boolean(value.completed),
    };
  } catch {
    return defaultTutorialProgress();
  }
}

export function saveTutorialProgress(progress: TutorialProgress) {
  try {
    window.localStorage.setItem(TUTORIAL_STORAGE_KEY, JSON.stringify(progress));
  } catch {
    // Tutorial persistence is optional when storage is unavailable.
  }
}

export function advanceTutorial(progress: TutorialProgress): TutorialProgress {
  const chapter = TUTORIAL_CHAPTERS[progress.chapterIndex];
  if (progress.stepIndex < chapter.steps.length - 1) {
    return { ...progress, stepIndex: progress.stepIndex + 1, completed: false };
  }
  if (progress.chapterIndex < TUTORIAL_CHAPTERS.length - 1) {
    return { ...progress, chapterIndex: progress.chapterIndex + 1, stepIndex: 0, completed: false };
  }
  return { ...progress, completed: true };
}

export function retreatTutorial(progress: TutorialProgress): TutorialProgress {
  if (progress.stepIndex > 0) {
    return { ...progress, stepIndex: progress.stepIndex - 1, completed: false };
  }
  if (progress.chapterIndex > 0) {
    const chapterIndex = progress.chapterIndex - 1;
    return {
      ...progress,
      chapterIndex,
      stepIndex: TUTORIAL_CHAPTERS[chapterIndex].steps.length - 1,
      completed: false,
    };
  }
  return progress;
}

export function applyTutorialEvent(
  progress: TutorialProgress,
  event: TutorialEvent,
): TutorialProgress {
  if (progress.completed) return progress;
  const step = TUTORIAL_CHAPTERS[progress.chapterIndex].steps[progress.stepIndex];
  return step.completionEvent === event ? advanceTutorial(progress) : progress;
}
