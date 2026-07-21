"""Dependency-free local HTTP server for the HistoryFinder world viewer."""

from __future__ import annotations

import argparse
import json
import mimetypes
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, RLock
from urllib.parse import parse_qs, urlparse

from simulation.world import World
from game.player_session import PlayerActionError, PlayerSession
from viewer.data import build_world_payload


STATIC_DIR = Path(__file__).with_name("static")
PLAY_STATIC_DIR = Path(__file__).parent.parent / "player" / "dist"


class WorldCache:
    def __init__(self):
        self._lock = Lock()
        self._key: tuple[int, int] | None = None
        self._payload: dict | None = None

    def get(self, seed: int, years: int) -> dict:
        key = (seed, years)
        with self._lock:
            if self._key != key:
                world = World(seed=seed)
                world.generate(years=years)
                self._payload = build_world_payload(world)
                self._key = key
            return self._payload


WORLD_CACHE = WorldCache()


class PlayerSessionStore:
    def __init__(self):
        self._lock = RLock()
        self._world_key: tuple[int, int] | None = None
        self._world: World | None = None
        self._sessions: dict[str, PlayerSession] = {}

    def create(self, seed: int, years: int) -> tuple[str, dict]:
        with self._lock:
            key = (seed, years)
            if self._world_key != key or self._world is None:
                world = World(seed=seed)
                world.generate(years=years)
                self._world = world
                self._world_key = key
                self._sessions = {}
            session_id = uuid.uuid4().hex
            session = PlayerSession(self._world)
            self._sessions[session_id] = session
            return session_id, session.bootstrap()

    def action(self, session_id: str, payload: dict) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(session_id)
            action = payload.get("action")
            if action == "examine":
                return session.examine(str(payload.get("evidence_id", "")))
            if action == "read":
                return session.read(str(payload.get("evidence_id", "")))
            if action == "consult":
                return session.consult(
                    str(payload.get("evidence_id", "")),
                    str(payload.get("informant_id", "")),
                )
            if action == "compare":
                return session.compare(
                    str(payload.get("first_id", "")),
                    str(payload.get("second_id", "")),
                )
            if action == "talk":
                return session.talk(str(payload.get("resident_id", "")))
            if action == "search_container":
                return session.search_container(
                    str(payload.get("container_id", "")))
            if action == "move":
                return session.move(
                    int(payload.get("dx", 0)), int(payload.get("dy", 0)))
            if action == "wait":
                return session.wait(int(payload.get("minutes", 10)))
            if action == "travel":
                return session.travel(str(payload.get("destination_id", "")))
            if action == "journal":
                return {"action": "journal", "journal": session.journal_payload()}
            raise PlayerActionError("无法识别这个调查动作。")


PLAYER_SESSIONS = PlayerSessionStore()


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "HistoryFinderViewer/1.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/world":
            self._serve_world(parse_qs(parsed.query))
            return
        if parsed.path == "/api/health":
            self._send_json({"status": "ok"})
            return
        if parsed.path in {"/play", "/play/"}:
            self._serve_static("index.html", PLAY_STATIC_DIR)
            return
        if parsed.path.startswith("/play/"):
            self._serve_static(
                parsed.path.removeprefix("/play/"), PLAY_STATIC_DIR)
            return
        relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        self._serve_static(relative)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/play/start":
            self._start_player_session(payload)
            return
        if parsed.path == "/api/play/action":
            self._player_action(payload)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _serve_world(self, query: dict[str, list[str]]):
        try:
            seed = int(query.get("seed", ["42"])[0])
            years = int(query.get("years", ["100"])[0])
        except ValueError:
            self._send_json(
                {"error": "seed and years must be integers"},
                HTTPStatus.BAD_REQUEST)
            return
        if not -1_000_000 <= seed <= 1_000_000:
            self._send_json(
                {"error": "seed must be between -1000000 and 1000000"},
                HTTPStatus.BAD_REQUEST)
            return
        if not 0 <= years <= 300:
            self._send_json(
                {"error": "years must be between 0 and 300"},
                HTTPStatus.BAD_REQUEST)
            return
        try:
            self._send_json(WORLD_CACHE.get(seed, years))
        except Exception as exc:
            self._send_json(
                {"error": f"world generation failed: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR)

    def _start_player_session(self, payload: dict):
        try:
            seed = int(payload.get("seed", 42))
            years = int(payload.get("years", 30))
            self._validate_world_options(seed, years)
            session_id, state = PLAYER_SESSIONS.create(seed, years)
            self._send_json({"session_id": session_id, "state": state})
        except (ValueError, PlayerActionError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json(
                {"error": f"player session failed: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR)

    def _player_action(self, payload: dict):
        session_id = str(payload.get("session_id", ""))
        if not session_id:
            self._send_json({"error": "missing session_id"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            result = PLAYER_SESSIONS.action(session_id, payload)
            self._send_json({"session_id": session_id, "result": result})
        except KeyError:
            self._send_json(
                {"error": "player session not found"}, HTTPStatus.NOT_FOUND)
        except PlayerActionError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json(
                {"error": f"player action failed: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR)

    @staticmethod
    def _validate_world_options(seed: int, years: int) -> None:
        if not -1_000_000 <= seed <= 1_000_000:
            raise ValueError("seed must be between -1000000 and 1000000")
        if not 0 <= years <= 300:
            raise ValueError("years must be between 0 and 300")

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0 or length > 1_000_000:
            raise ValueError("request body must contain JSON under 1 MB")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _serve_static(self, relative: str, root: Path = STATIC_DIR):
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type, _ = mimetypes.guess_type(path.name)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args):
        print(f"[viewer] {self.address_string()} {format_string % args}")


def main():
    parser = argparse.ArgumentParser(description="HistoryFinder world viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ViewerHandler)
    print(f"HistoryFinder World Viewer: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
