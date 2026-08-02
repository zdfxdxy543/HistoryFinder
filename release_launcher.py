"""Windows release entry point for the bundled browser game."""

from __future__ import annotations

import ctypes
import json
import socket
import sys
import threading
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer

from viewer.server import ViewerHandler


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
PORT_ATTEMPTS = 10


def _set_console_title() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("HistoryFinder Server")
        except (AttributeError, OSError):
            pass


def _healthy_historyfinder(port: int) -> bool:
    try:
        with urllib.request.urlopen(
                f"http://{HOST}:{port}/api/health", timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
            server_name = response.headers.get("Server", "")
            return (payload.get("status") == "ok"
                    and server_name.startswith("HistoryFinderViewer/"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _available_port() -> tuple[int, bool]:
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_ATTEMPTS):
        if _healthy_historyfinder(port):
            return port, True
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((HOST, port))
            except OSError:
                continue
        return port, False
    raise RuntimeError(
        f"无法在 {DEFAULT_PORT}-{DEFAULT_PORT + PORT_ATTEMPTS - 1} 找到可用端口。")


def main() -> None:
    _set_console_title()
    try:
        port, already_running = _available_port()
    except RuntimeError as exc:
        print(f"[HistoryFinder] {exc}")
        input("按回车键退出……")
        raise SystemExit(1) from exc

    game_url = f"http://{HOST}:{port}/play/"
    if already_running:
        print(f"[HistoryFinder] 服务器已运行：{game_url}")
        webbrowser.open(game_url)
        return

    server = ThreadingHTTPServer((HOST, port), ViewerHandler)
    print("[HistoryFinder] 本地服务器已启动。")
    print(f"[HistoryFinder] 游戏地址：{game_url}")
    print("[HistoryFinder] 关闭此窗口或按 Ctrl+C 即可退出。")
    threading.Timer(0.8, webbrowser.open, args=(game_url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[HistoryFinder] 正在关闭……")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
