#!/usr/bin/env python3

from __future__ import annotations

import html
import json
import os
import subprocess
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT_DIR = Path(os.environ.get("WEB_TEST_ROOT", "/home/opc/laiwan-web-test"))
CONTROL_DIR = Path(os.environ.get("WEB_TEST_CONTROL_DIR", ROOT_DIR / "control"))
STATE_FILE = Path(os.environ.get("WEB_TEST_STATE_FILE", CONTROL_DIR / "state.json"))
NGINX_CONTROL_DIR = Path(
    os.environ.get("WEB_TEST_NGINX_CONTROL_DIR", "/etc/nginx/laiwan-web-test")
)
GATE_FILE = Path(os.environ.get("WEB_TEST_GATE_FILE", CONTROL_DIR / "gate.conf"))
MAINTENANCE_FILE = Path(
    os.environ.get("WEB_TEST_MAINTENANCE_FILE", CONTROL_DIR / "maintenance.html")
)
NGINX_GATE_FILE = NGINX_CONTROL_DIR / "gate.conf"
NGINX_MAINTENANCE_FILE = NGINX_CONTROL_DIR / "maintenance.html"
NGINX_ADMIN_FILE = NGINX_CONTROL_DIR / "admin.htpasswd"
ADMIN_FILE = Path(os.environ.get("WEB_TEST_ADMIN_FILE", CONTROL_DIR / "admin.htpasswd"))
SITE_HOST = os.environ.get(
    "WEB_TEST_SITE_HOST",
    "laiwan-production-web-test.tokinonagare.com",
)
CONTROL_HOST = os.environ.get("WEB_TEST_CONTROL_HOST", "127.0.0.1")
CONTROL_PORT = int(os.environ.get("WEB_TEST_CONTROL_PORT", "8090"))
DEFAULT_OPEN = os.environ.get("WEB_TEST_DEFAULT_OPEN", "false").lower() == "true"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    CONTROL_DIR.mkdir(parents=True, exist_ok=True)


def sync_to_nginx(source: Path, target: Path) -> None:
    subprocess.run(
        ["sudo", "install", "-d", "-m", "0755", str(NGINX_CONTROL_DIR)],
        check=True,
    )
    subprocess.run(
        ["sudo", "install", "-m", "0644", str(source), str(target)],
        check=True,
    )


def load_state() -> dict:
    ensure_dirs()
    if STATE_FILE.exists():
        try:
            with STATE_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                if isinstance(data, dict) and "open" in data:
                    return data
        except Exception:
            pass

    state = {
        "open": DEFAULT_OPEN,
        "updated_at": now_iso(),
        "updated_by": "bootstrap",
    }
    save_state(state, reload_nginx=False)
    return state


def write_atomic(path: Path, content: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    tmp_path.replace(path)


def render_gate_conf(is_open: bool) -> str:
    value = "1" if is_open else "0"
    return (
        'set $laiwan_web_test_gate_open "' + value + '";\n'
    )


def render_maintenance_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LaiWan 测试站点维护中</title>
  <style>
    :root { color-scheme: light; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, #f7f7fb 0%, #ffffff 100%);
      color: #1f2937;
    }
    .card {
      width: min(720px, calc(100vw - 32px));
      border: 1px solid #e5e7eb;
      border-radius: 20px;
      padding: 32px;
      box-shadow: 0 20px 60px rgba(15, 23, 42, 0.08);
      background: rgba(255, 255, 255, 0.9);
    }
    h1 { margin: 0 0 12px; font-size: 32px; }
    p { margin: 0; line-height: 1.7; font-size: 16px; color: #4b5563; }
  </style>
</head>
<body>
  <main class="card">
    <h1>测试站点暂时关闭</h1>
    <p>这个环境默认关闭。需要时请先到管理页面开启，再访问正式测试网址。</p>
  </main>
</body>
</html>
"""


def save_state(state: dict, reload_nginx: bool = True, updated_by: str | None = None) -> None:
    ensure_dirs()
    normalized = {
        "open": bool(state.get("open")),
        "updated_at": state.get("updated_at", now_iso()),
        "updated_by": updated_by or state.get("updated_by") or "control-server",
    }
    write_atomic(STATE_FILE, json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
    write_atomic(GATE_FILE, render_gate_conf(normalized["open"]))
    if not MAINTENANCE_FILE.exists():
        write_atomic(MAINTENANCE_FILE, render_maintenance_html())
    if ADMIN_FILE.exists():
        sync_to_nginx(ADMIN_FILE, NGINX_ADMIN_FILE)
    sync_to_nginx(GATE_FILE, NGINX_GATE_FILE)
    sync_to_nginx(MAINTENANCE_FILE, NGINX_MAINTENANCE_FILE)
    if reload_nginx:
        subprocess.run(["sudo", "nginx", "-t"], check=True)
        subprocess.run(["sudo", "nginx", "-s", "reload"], check=True)


def current_state() -> dict:
    state = load_state()
    state.setdefault("open", False)
    state.setdefault("updated_at", now_iso())
    state.setdefault("updated_by", "unknown")
    return state


def html_page(state: dict) -> str:
    status_text = "开启" if state["open"] else "关闭"
    status_color = "#16a34a" if state["open"] else "#dc2626"
    updated_at = html.escape(str(state.get("updated_at", "")))
    updated_by = html.escape(str(state.get("updated_by", "")))
    site_url = html.escape(f"https://{SITE_HOST}/")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LaiWan 测试站点管理</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #0f172a;
      --panel: rgba(255,255,255,0.92);
      --border: rgba(15, 23, 42, 0.08);
      --text: #0f172a;
      --muted: #64748b;
      --primary: #0f766e;
      --danger: #dc2626;
      --shadow: 0 24px 80px rgba(15, 23, 42, 0.18);
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.20), transparent 30%),
        radial-gradient(circle at top right, rgba(220, 38, 38, 0.12), transparent 25%),
        linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
      color: var(--text);
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .card {{
      width: min(860px, 100%);
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 32px;
      backdrop-filter: blur(14px);
    }}
    .eyebrow {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.18em;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(28px, 4vw, 44px);
      line-height: 1.05;
    }}
    .sub {{
      margin: 14px 0 0;
      font-size: 16px;
      line-height: 1.7;
      color: var(--muted);
      max-width: 60ch;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-top: 28px;
    }}
    .panel {{
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 18px;
      background: rgba(255,255,255,0.7);
    }}
    .label {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }}
    .value {{
      font-size: 20px;
      font-weight: 700;
    }}
    .value.open {{ color: {status_color}; }}
    .actions {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 24px;
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 12px 18px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }}
    .open {{ background: var(--primary); color: white; }}
    .close {{ background: var(--danger); color: white; }}
    .secondary {{
      background: #e2e8f0;
      color: #0f172a;
    }}
    .footer {{
      margin-top: 22px;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.7;
    }}
    code {{
      background: rgba(15, 23, 42, 0.06);
      padding: 0.15rem 0.35rem;
      border-radius: 6px;
    }}
    @media (max-width: 720px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .card {{ padding: 24px; }}
    }}
  </style>
</head>
<body>
  <main class="card">
    <div class="eyebrow">LaiWan Web Test Control</div>
    <h1>测试站点访问开关</h1>
    <p class="sub">
      当前测试站点地址：<code>{site_url}</code>。默认保持关闭，部署和打 包不会改变状态；
      需要验证时手动开启，结束后再关闭即可。
    </p>

    <div class="grid">
      <section class="panel">
        <div class="label">当前状态</div>
        <div id="state" class="value {'open' if state['open'] else ''}">{status_text}</div>
      </section>
      <section class="panel">
        <div class="label">最近更新</div>
        <div class="value" style="font-size: 16px; font-weight: 600;" id="updatedAt">{updated_at}</div>
        <div class="footer">更新者：<span id="updatedBy">{updated_by}</span></div>
      </section>
    </div>

    <div class="actions">
      <button class="open" onclick="setState(true)">开启访问</button>
      <button class="close" onclick="setState(false)">关闭访问</button>
      <button class="secondary" onclick="refreshStatus()">刷新状态</button>
    </div>

    <div class="footer" id="message">状态以服务器侧为准，页面会在切换后 自动刷新。</div>
  </main>

  <script>
    async function setState(open) {{
      const path = open ? 'api/open' : 'api/close';
      const response = await fetch(path, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
      }});
      if (!response.ok) {{
        throw new Error('状态切换失败');
      }}
      await refreshStatus();
    }}

    async function refreshStatus() {{
      const response = await fetch('api/status');
      const data = await response.json();
      document.getElementById('state').textContent = data.open ? '开启' : '关闭';
      document.getElementById('state').className = 'value ' + (data.open ? 'open' : '');
      document.getElementById('updatedAt').textContent = data.updated_at || '';
      document.getElementById('updatedBy').textContent = data.updated_by || '';
      document.getElementById('message').textContent = data.open
        ? '站点当前允许外部访问。'
        : '站点当前关闭，外部访问会返回维护页。';
    }}

    refreshStatus().catch((error) => {{
      document.getElementById('message').textContent = error.message;
    }});
  </script>
</body>
</html>
"""


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "LaiWanWebTestControl/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str, status: int = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_html(html_page(current_state()))
            return
        if path == "/api/status":
            state = current_state()
            self._send_json(
                {
                    "open": bool(state.get("open")),
                    "updated_at": state.get("updated_at"),
                    "updated_by": state.get("updated_by"),
                    "site_url": f"https://{SITE_HOST}/",
                }
            )
            return
        if path == "/healthz":
            self._send_json({"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/open":
            self._set_open_state(True)
            return
        if path == "/api/close":
            self._set_open_state(False)
            return
        if path == "/api/toggle":
            self._set_open_state(not bool(current_state().get("open")))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _set_open_state(self, open_state: bool) -> None:
        state = {
            "open": open_state,
            "updated_at": now_iso(),
            "updated_by": "admin-ui",
        }
        save_state(state, reload_nginx=True, updated_by="admin-ui")
        self._send_json(
            {
                "open": open_state,
                "updated_at": state["updated_at"],
                "updated_by": state["updated_by"],
                "site_url": f"https://{SITE_HOST}/",
            }
        )


def main() -> None:
    ensure_dirs()
    if not STATE_FILE.exists():
        save_state(
            {
                "open": DEFAULT_OPEN,
                "updated_at": now_iso(),
                "updated_by": "bootstrap",
            },
            reload_nginx=False,
            updated_by="bootstrap",
        )
    if not GATE_FILE.exists():
        save_state(current_state(), reload_nginx=False)
    if not MAINTENANCE_FILE.exists():
        write_atomic(MAINTENANCE_FILE, render_maintenance_html())
    if ADMIN_FILE.exists():
        sync_to_nginx(ADMIN_FILE, NGINX_ADMIN_FILE)
    sync_to_nginx(GATE_FILE, NGINX_GATE_FILE)
    sync_to_nginx(MAINTENANCE_FILE, NGINX_MAINTENANCE_FILE)

    server = ThreadingHTTPServer((CONTROL_HOST, CONTROL_PORT), ControlHandler)
    print(
        f"[control] listening on http://{CONTROL_HOST}:{CONTROL_PORT}, "
        f"site={SITE_HOST}, root={ROOT_DIR}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
