"""Dependency-free local HTTP server for the HistoryFinder world viewer."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, urlparse

from simulation.world import World
from viewer.data import build_world_payload


STATIC_DIR = Path(__file__).with_name("static")


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
        relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        self._serve_static(relative)

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

    def _serve_static(self, relative: str):
        path = (STATIC_DIR / relative).resolve()
        try:
            path.relative_to(STATIC_DIR.resolve())
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
