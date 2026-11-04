"""Loopback-only, single-user classroom application. No public hosting."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from domain import ROOT, Store, apply_delay, canonical, complete, decision, digest, read_inputs
from projection import ContractError, compare
from runtime import Agent


class App:
    def __init__(self, work, adapter=None):
        self.work = Path(work)
        self.store = Store(self.work / "ledger.sqlite3")
        self.agent = Agent(self.store, self.work / "runs", adapter)
        self.token = secrets.token_urlsafe(32)

    def view(self, sid):
        return {"state": self.store.state(sid), "runs": self.store.runs(sid)}

    def action(self, name, p):
        if name == "new":
            return self.view(self.store.create(p.get("variant", "normal"))["session_id"])
        sid, key = p.get("session_id"), p.get("request_id")
        if name == "preview":
            s = self.store.state(sid)
            if p.get("expected_version") != s["version"]:
                raise ContractError("快照已变化，请刷新")
            check = compare(s, p.get("quantity"), p.get("ready_minute"))
            return {"comparison": check, "preview_sha256": digest(check), "snapshot_version": s["version"]}
        if name == "investigate":
            if p.get("expected_version") != self.store.state(sid)["version"]:
                raise ContractError("快照已变化，请刷新")
            self.agent.start(sid, "manual_review")
            return self.view(sid)
        if name not in ("delay", "decision", "complete"):
            raise ContractError("未找到操作")
        def change(s, db):
            if name == "delay":
                apply_delay(s)
            elif name == "decision":
                decision(s, db, p)
            else:
                complete(s, p)
        result = self.store.mutate(sid, key, dict(p, action=name), change)
        if name in ("delay", "complete") and not result["duplicate_ignored"]:
            self.agent.start(sid, "eta_changed" if name == "delay" else "completion_recorded")
        return dict(self.view(sid), duplicate_ignored=result["duplicate_ignored"])


def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, value, code=200, mime="application/json; charset=utf-8"):
            body = canonical(value).encode("utf-8") if not isinstance(value, bytes) else value
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def local(self):
            port = self.server.server_address[1]
            if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                raise ContractError("只接受本机访问")
            origin = self.headers.get("Origin")
            if origin and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                raise ContractError("不接受跨站操作")

        def do_GET(self):
            try:
                self.local()
                url = urlparse(self.path)
                if url.path == "/api/bootstrap":
                    _, meta, _ = read_inputs()
                    self.send({"token": app.token, "source": meta, "runtime": "live_model_not_replay", "app_id": "fde-minimum-agent-0.3"})
                elif url.path == "/api/state":
                    self.send(app.view(parse_qs(url.query).get("session_id", [""])[0]))
                elif url.path == "/favicon.ico":
                    self.send(b"", 204, "image/x-icon")
                elif url.path in ("/", "/app.js", "/style.css"):
                    name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}[url.path]
                    mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[name]
                    self.send((ROOT / "web" / name).read_bytes(), mime=mime + "; charset=utf-8")
                else:
                    self.send({"error": "未找到页面"}, 404)
            except ContractError as exc:
                self.send({"error": str(exc)}, 400)
            except Exception:
                self.send({"error": "本地服务暂不可用，请查看终端"}, 500)

        def do_POST(self):
            try:
                self.local()
                if not secrets.compare_digest(self.headers.get("X-FDE-Token", ""), app.token):
                    self.send({"error": "操作令牌失效，请刷新页面"}, 403)
                    return
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ContractError("只接受JSON操作")
                size = int(self.headers.get("Content-Length", "0"))
                if not 1 <= size <= 16000:
                    raise ContractError("请求大小不符合本地切片范围")
                p = json.loads(self.rfile.read(size))
                if not isinstance(p, dict):
                    raise ContractError("请求须为对象")
                self.send(app.action(self.path.removeprefix("/api/"), p))
            except (ContractError, ValueError, TypeError) as exc:
                self.send({"error": str(exc)}, 400)
            except Exception:
                self.send({"error": "本次操作失败，未生成可采纳动作"}, 500)
    return Handler


def main():
    p = argparse.ArgumentParser(description="第8组高峰经营异常助手，本地真实AI最小闭环")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open-browser", action="store_true")
    p.add_argument("--work", type=Path, default=Path(os.environ.get("FDE_AGENT_WORK", r"F:\ChatGPT\work\fde-minimum-agent")))
    args = p.parse_args()
    read_inputs()
    app = App(args.work)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), handler(app))
    print(f"本地助手已启动：http://127.0.0.1:{args.port}  （关闭此进程停止服务）", flush=True)
    print("模型：本机Codex现有配置；每次真实调用；GitHub暂未发布。", flush=True)
    if args.open_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
