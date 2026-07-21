import type { ActionResult, PlayerState } from "./types";

async function request<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `请求失败（${response.status}）`);
  }
  return data as T;
}

export async function startSession(seed: number, years: number) {
  return request<{ session_id: string; state: PlayerState }>(
    "/api/play/start",
    { seed, years },
  );
}

export async function performAction(
  sessionId: string,
  payload: Record<string, unknown>,
) {
  const response = await request<{ session_id: string; result: ActionResult }>(
    "/api/play/action",
    { session_id: sessionId, ...payload },
  );
  return response.result;
}
