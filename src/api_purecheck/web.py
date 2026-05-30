from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
from urllib.parse import urlparse

from api_purecheck import __version__
from api_purecheck.config import AuditConfig
from api_purecheck.model_profiles import MODEL_PROFILES
from api_purecheck.runner import RunOptions, dry_run_report, run_audit


class PureCheckServer(ThreadingHTTPServer):
    allow_reuse_address = True


def serve_web(host: str, port: int) -> None:
    server = PureCheckServer((host, port), PureCheckHandler)
    try:
        print(f"API PureCheck 本地页面已启动：http://{host}:{server.server_port}")
        print("按 Ctrl+C 停止服务。")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止 API PureCheck 本地服务。")
    finally:
        server.server_close()


class PureCheckHandler(BaseHTTPRequestHandler):
    server_version = "API PureCheck/1.0"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_html(INDEX_HTML)
            return
        if path == "/favicon.ico":
            self._send_bytes(FAVICON_SVG.encode("utf-8"), "image/svg+xml; charset=utf-8")
            return
        if path == "/favicon.svg":
            self._send_bytes(FAVICON_SVG.encode("utf-8"), "image/svg+xml; charset=utf-8")
            return
        if path == "/health":
            self._send_json({"ok": True, "version": __version__, "ui": "2026-05-release"})
            return
        if path == "/api/status":
            self._send_json({"ok": True, "tool": "api-purecheck", "version": __version__, "ui": "2026-05-release"})
            return
        if path == "/api/model-profiles":
            self._send_json({"profiles": [_profile_to_json(profile) for profile in MODEL_PROFILES]})
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if self.path not in {"/api/dry-run", "/api/check"}:
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json()
            config = _config_from_payload(payload)
            config.validate()
            if self.path == "/api/dry-run":
                report = dry_run_report(config)
            else:
                report = run_audit(config, RunOptions(timeout_seconds=config.timeout_seconds))
            self._send_json(report)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": f"internal error: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        data = self.rfile.read(length)
        parsed = json.loads(data.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _config_from_payload(payload: dict[str, Any]) -> AuditConfig:
    return AuditConfig(
        base_url=str(payload.get("base_url", "")).strip(),
        api_key=str(payload.get("api_key", "")).strip(),
        claimed_model=str(payload.get("claimed_model") or payload.get("model") or "").strip(),
        level=str(payload.get("level", "standard")).strip(),
        output_format="json",
        timeout_seconds=float(payload.get("timeout_seconds", 60.0)),
        api_type=str(payload.get("api_type", "openai-compatible")).strip(),
    )


def _profile_to_json(profile: Any) -> dict[str, Any]:
    return {
        "family": profile.family,
        "display_name": profile.display_name,
        "providers": list(profile.providers),
        "api_types": list(profile.api_types),
        "model_names": list(profile.model_names),
        "notes": profile.notes,
    }


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect x="5" y="5" width="54" height="54" rx="14" fill="#111827"/>
  <rect x="5" y="5" width="54" height="54" rx="14" fill="none" stroke="#38bdf8" stroke-width="3"/>
  <text x="32" y="40" text-anchor="middle"
        font-family="Arial, Helvetica, sans-serif"
        font-size="24" font-weight="800" letter-spacing="-1"
        fill="#ffffff">AP</text>
  <circle cx="49" cy="18" r="4" fill="#7dd3fc"/>
</svg>"""


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>API PureCheck</title>
  <link rel="icon" href="/favicon.svg?v=1.0.0" type="image/svg+xml" />
  <style>
    :root {
      color-scheme: light;
      --bg: #eef2f6;
      --surface: #ffffff;
      --text: #151922;
      --muted: #637083;
      --line: #d8dee8;
      --primary: #1263d8;
      --primary-strong: #0c4eb2;
      --primary-soft: #eaf2ff;
      --success: #16794c;
      --warn: #a15c00;
      --danger: #b42318;
      --ink: #0f172a;
      --shadow: 0 18px 48px rgba(24, 39, 75, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }

    .topbar {
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.92);
      backdrop-filter: blur(10px);
      position: sticky;
      top: 0;
      z-index: 10;
    }

    .topbar-inner {
      width: min(1280px, calc(100% - 28px));
      min-height: 56px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-weight: 800;
      color: #172033;
    }

    .brand-text {
      display: grid;
      gap: 1px;
    }

    .brand-title {
      font-size: 16px;
      line-height: 1.1;
    }

    .brand-subtitle {
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }

    .brand-mark {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: #172033;
      color: #fff;
      font-size: 13px;
      letter-spacing: 0;
    }

    .topbar-note {
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }

    main {
      width: min(1280px, calc(100% - 28px));
      margin: 0 auto;
      padding: 12px 0 42px;
    }

    .workbench-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin: 18px 0 0;
    }

    h1 {
      margin: 0;
      font-size: clamp(22px, 2.6vw, 32px);
      line-height: 1.16;
      letter-spacing: 0;
    }

    .lead {
      margin: 0;
      max-width: 760px;
      color: var(--muted);
      font-size: 14px;
    }

    .hero-copy {
      display: grid;
      gap: 8px;
    }

    .hero-badges {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 5px 10px;
      background: #fff;
      color: #334155;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
      gap: 14px;
      align-items: start;
    }

    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }

    .form-panel {
      padding: 14px;
      height: calc(100vh - 82px);
      min-height: 650px;
      overflow: auto;
    }

    .result-panel {
      height: calc(100vh - 82px);
      min-height: 650px;
      padding: 14px;
      overflow: auto;
    }

    form {
      display: grid;
      gap: 9px;
    }

    .launch-strip {
      display: grid;
      gap: 8px;
      margin-bottom: 12px;
      padding: 12px;
      border: 1px solid #c9d8ea;
      border-radius: 8px;
      background: #f8fbff;
    }

    .launch-title {
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
      color: var(--ink);
      letter-spacing: 0;
    }

    .launch-copy {
      margin: 0;
      color: #526176;
      font-size: 13px;
    }

    .cost-grid, .metric-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }

    .cost-card, .metric-card {
      border: 1px solid #dbe4ef;
      border-radius: 7px;
      padding: 8px;
      background: #fff;
      min-width: 0;
    }

    .cost-card b, .metric-card b {
      display: block;
      color: var(--ink);
      font-size: 14px;
    }

    .cost-card span, .metric-card span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .panel-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }

    .panel-title h2 {
      margin: 0;
      font-size: 18px;
      letter-spacing: 0;
    }

    .panel-title span {
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }

    label {
      display: grid;
      gap: 5px;
      color: #293142;
      font-weight: 650;
      font-size: 13px;
    }

    input, select {
      width: 100%;
      min-height: 40px;
      border: 1px solid #c6cfdb;
      border-radius: 6px;
      padding: 8px 10px;
      color: var(--text);
      background: #fff;
      font: inherit;
    }

    input:focus, select:focus {
      border-color: var(--primary);
      outline: 3px solid rgba(20, 87, 217, 0.14);
    }

    .inline {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    .secret-field {
      position: relative;
      display: grid;
    }

    .secret-field input {
      padding-right: 70px;
    }

    .ghost-button {
      position: absolute;
      right: 6px;
      top: 5px;
      min-height: 30px;
      border: 0;
      border-radius: 5px;
      padding: 6px 10px;
      background: #eef2f7;
      color: #39465a;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }

    .ghost-button:hover {
      background: #e2e8f0;
    }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 2px;
      position: sticky;
      bottom: -16px;
      z-index: 2;
      padding: 8px 0 16px;
      background: linear-gradient(180deg, rgba(255,255,255,0.78), #fff 28%);
    }

    .result-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0 2px;
    }

    button {
      min-height: 40px;
      border: 1px solid var(--primary);
      border-radius: 6px;
      padding: 9px 14px;
      background: var(--primary);
      color: #fff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }

    button:hover {
      background: var(--primary-strong);
    }

    button.secondary {
      background: #fff;
      color: var(--primary);
    }

    button.secondary:hover {
      background: #eef5ff;
    }

    .small-action {
      min-height: 34px;
      border-color: #c6cfdb;
      background: #fff;
      color: #334155;
      padding: 6px 10px;
      font-size: 13px;
    }

    .small-action:hover {
      background: #f1f5f9;
    }

    button:disabled {
      opacity: 0.58;
      cursor: wait;
    }

    .notice {
      margin-top: 10px;
      padding: 10px;
      border-radius: 6px;
      background: #eef6ff;
      color: #23476f;
      font-size: 13px;
    }

    .quick-hint {
      margin: -3px 0 0;
      color: var(--muted);
      font-size: 12px;
    }

    .level-note {
      display: grid;
      gap: 4px;
      margin-top: 0;
      padding: 9px 10px;
      border-radius: 6px;
      background: #f8fafc;
      color: #475569;
      font-size: 12px;
    }

    .model-suggestions {
      display: grid;
      gap: 7px;
      padding: 10px;
      border-radius: 6px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      color: #475569;
      font-size: 12px;
      max-height: 92px;
      overflow: auto;
    }

    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .chip {
      border: 1px solid #cbd5e1;
      border-radius: 6px;
      padding: 4px 7px;
      background: #fff;
      color: #334155;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
    }

    .chip:hover {
      border-color: var(--primary);
      color: var(--primary);
      background: #eef5ff;
    }

    .result-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      border-bottom: 1px solid var(--line);
      padding-bottom: 12px;
      margin-bottom: 14px;
    }

    .result-head h2 {
      margin: 0;
      font-size: 20px;
      letter-spacing: 0;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border-radius: 999px;
      padding: 4px 10px;
      background: #eef2f7;
      color: #334155;
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }

    .badge.high { background: #e7f7ee; color: var(--success); }
    .badge.medium { background: #fff4df; color: var(--warn); }
    .badge.low { background: #fff0ee; color: var(--danger); }
    .badge.unavailable { background: #eef2f7; color: #475569; }
    .badge.dry-run { background: #eaf2ff; color: var(--primary); }

    .verdict-card {
      display: grid;
      gap: 10px;
      margin-bottom: 14px;
      padding: 14px;
      border: 1px solid #cfdced;
      border-radius: 8px;
      background: #fbfdff;
    }

    .verdict-card strong {
      font-size: 15px;
      color: var(--ink);
    }

    .verdict-card p {
      margin: 0;
      color: #526176;
      font-size: 13px;
    }

    .progress-card {
      min-height: 430px;
      display: grid;
      align-content: center;
      gap: 14px;
      color: var(--muted);
      padding: 24px;
    }

    .progress-title {
      color: var(--ink);
      font-weight: 800;
      font-size: 22px;
    }

    .progress-bar {
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: #e8edf4;
    }

    .progress-bar span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--primary);
      transition: width 0.25s ease;
    }

    .fix-list {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }

    .fix-item {
      border: 1px solid #dbe4ef;
      border-radius: 6px;
      padding: 8px 10px;
      background: #fff;
      color: #334155;
      font-size: 13px;
    }

    .risk-banner {
      margin: 0 0 12px;
      padding: 10px 12px;
      border: 1px solid #dbe3ee;
      border-radius: 6px;
      background: #f8fafc;
      color: #334155;
      font-weight: 700;
    }

    .empty {
      color: var(--muted);
      min-height: 430px;
      display: grid;
      align-content: center;
      gap: 14px;
      padding: 24px;
    }

    .empty h2 {
      margin: 0;
      color: var(--text);
      font-size: 24px;
      letter-spacing: 0;
    }

    .empty-steps {
      display: grid;
      gap: 10px;
      margin-top: 4px;
    }

    .empty-step {
      display: grid;
      grid-template-columns: 28px 1fr;
      gap: 10px;
      align-items: center;
      padding: 10px;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      background: #fff;
      color: #334155;
      text-align: left;
    }

    .empty-step b {
      width: 28px;
      height: 28px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      background: #e8f1ff;
      color: var(--primary);
      font-size: 13px;
    }

    .prob-list, .evidence-list {
      display: grid;
      gap: 10px;
      margin: 14px 0;
    }

    .prob-row {
      display: grid;
      grid-template-columns: minmax(130px, 180px) 1fr 52px;
      gap: 10px;
      align-items: center;
    }

    .bar {
      height: 10px;
      background: #e8edf4;
      border-radius: 999px;
      overflow: hidden;
    }

    .bar span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--primary);
    }

    .details {
      margin-top: 16px;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    pre {
      overflow: auto;
      max-height: 280px;
      margin: 0;
      padding: 12px;
      border-radius: 6px;
      background: #101827;
      color: #e7edf7;
      font-size: 12px;
    }

    .guide-section {
      margin-top: 18px;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
    }

    .guide-item {
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.82);
      color: #334155;
      font-size: 13px;
    }

    .guide-item h2 {
      margin: 0 0 6px;
      font-size: 15px;
      color: var(--text);
    }

    @media (max-width: 820px) {
      .topbar-inner { width: min(100% - 24px, 720px); }
      main { width: min(100% - 24px, 720px); padding-top: 12px; }
      .workbench-head { align-items: flex-start; flex-direction: column; }
      .hero-badges { justify-content: flex-start; }
      .topbar-note { display: none; }
      .layout { grid-template-columns: 1fr; }
      .inline { grid-template-columns: 1fr; }
      .cost-grid, .metric-grid { grid-template-columns: 1fr; }
      .prob-row { grid-template-columns: 1fr; }
      .result-head { align-items: flex-start; flex-direction: column; }
      .form-panel, .result-panel { height: auto; min-height: 0; }
      .guide-section { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <div class="brand">
        <span class="brand-mark">AP</span>
        <span class="brand-text">
          <span class="brand-title">API PureCheck</span>
          <span class="brand-subtitle">你的中转站，真的纯吗？</span>
        </span>
      </div>
      <div class="topbar-note">本地运行 · Key 不上传 · 概率报告 · v1.0.0</div>
    </div>
  </div>
  <main>
    <section class="layout" aria-label="API 检测工作台">
      <div class="panel form-panel">
        <div class="launch-strip">
          <h1 class="launch-title">API 纯度检测台</h1>
          <p class="launch-copy">填入 API 地址、Key 和声称模型，一页完成预估、检测和报告下载。</p>
          <div class="cost-grid" aria-label="请求数说明">
            <div class="cost-card"><b>快速 3 次</b><span>先试通，成本最低</span></div>
            <div class="cost-card"><b>标准 8 次</b><span>推荐默认，判断够用</span></div>
            <div class="cost-card"><b>深度 18 次</b><span>更充分，仍控成本</span></div>
          </div>
        </div>
        <div class="panel-title">
          <h2>1. 填写检测信息</h2>
          <span>先看成本，再出结论</span>
        </div>
        <form id="check-form">
          <label>
            API 地址
            <input name="base_url" placeholder="https://example.com/v1" required />
          </label>
          <label>
            API Key
            <span class="secret-field">
              <input id="api-key-input" name="api_key" type="password" autocomplete="off" spellcheck="false" placeholder="YOUR_API_KEY" required />
              <button id="toggle-key-btn" class="ghost-button" type="button" aria-controls="api-key-input" aria-pressed="false">显示</button>
            </span>
          </label>
          <p class="quick-hint">Key 只保存在当前页面和本机请求中，不会写入报告。</p>
          <div class="inline">
            <label>
              API 类型
              <select name="api_type">
                <option value="openai-compatible" selected>OpenAI-compatible</option>
                <option value="anthropic">Anthropic Messages API</option>
              </select>
            </label>
            <label>
              模型族
              <select name="model_family" id="model-family-select">
                <option value="">不确定 / 手动填写</option>
              </select>
            </label>
          </div>
          <div class="model-suggestions" id="model-suggestions">
            <strong>模型名提示</strong>
            <span>选择模型族后，会显示常见模型名。中转站以自己的文档为准。</span>
          </div>
          <label>
            声称模型
            <input id="claimed-model-input" name="claimed_model" placeholder="gpt-4o" required />
          </label>
          <div class="inline">
            <label>
              检测强度
              <select name="level">
                <option value="quick">快速</option>
                <option value="standard" selected>标准</option>
                <option value="deep">深度</option>
              </select>
            </label>
            <label>
              超时秒数
              <input name="timeout_seconds" type="number" min="1" step="1" value="60" />
            </label>
          </div>
          <div class="level-note" id="level-note">
            <strong>标准模式预计 8 次请求</strong>
            <span>默认轻量检测，先控成本，再给结论。</span>
          </div>
          <div class="actions">
            <button id="check-btn" type="submit">开始检测</button>
            <button class="secondary" id="dry-btn" type="button">只预估请求数</button>
          </div>
        </form>
        <div class="notice">API Key 只发送到本机 localhost 服务，由本机向你的 API 地址发起请求。报告会自动脱敏。</div>
      </div>

      <div class="panel result-panel" id="result">
        <div class="empty">
          <h2>2. 查看检测结论</h2>
          <div>点击左侧按钮后，结论、概率、风险项、访问诊断和下载入口都会显示在这里。</div>
          <div class="empty-steps">
            <div class="empty-step"><b>1</b><span>填写 API 地址、Key 和声称模型。</span></div>
            <div class="empty-step"><b>2</b><span>点击“只预估请求数”确认成本。</span></div>
            <div class="empty-step"><b>3</b><span>开始检测并下载 JSON 或 HTML 报告。</span></div>
          </div>
        </div>
      </div>
    </section>

    <section class="workbench-head" aria-label="工具说明">
      <div class="hero-copy">
        <h1>你的中转站，真的纯吗？</h1>
        <p class="lead">API PureCheck 面向普通用户、学生和开发者，把复杂的协议检查和行为探针压缩成一份可读的纯度报告。</p>
      </div>
      <div class="hero-badges">
        <span class="pill">OpenAI-compatible</span>
        <span class="pill">Anthropic</span>
        <span class="pill">本地检测</span>
      </div>
    </section>

    <section class="guide-section" aria-label="说明">
      <div class="guide-item">
        <h2>怎么判断</h2>
        <div>工具会结合协议返回、模型自报、黑盒探针、行为画像和风险检查，给出概率参考。</div>
      </div>
      <div class="guide-item">
        <h2>适合谁用</h2>
        <div>普通用户、学生和开发者都可以用。它更像体检工具，不是法律级审计报告。</div>
      </div>
      <div class="guide-item">
        <h2>隐私边界</h2>
        <div>Key 只交给本机 localhost 服务使用，报告和日志会自动脱敏。</div>
      </div>
    </section>
  </main>

  <script>
    const form = document.querySelector('#check-form');
    const result = document.querySelector('#result');
    const checkBtn = document.querySelector('#check-btn');
    const dryBtn = document.querySelector('#dry-btn');
    const keyInput = document.querySelector('#api-key-input');
    const toggleKeyBtn = document.querySelector('#toggle-key-btn');
    const apiTypeSelect = form.querySelector('select[name="api_type"]');
    const levelSelect = form.querySelector('select[name="level"]');
    const levelNote = document.querySelector('#level-note');
    const modelFamilySelect = document.querySelector('#model-family-select');
    const modelSuggestions = document.querySelector('#model-suggestions');
    const claimedModelInput = document.querySelector('#claimed-model-input');
    let lastReport = null;
    let modelProfiles = [];

    const levelCopy = {
      quick: ['快速模式预计 3 次请求', '最低成本，适合先确认 API 是否打通。'],
      standard: ['标准模式预计 8 次请求', '默认推荐，覆盖核心探针、流式检查和错误泄漏检查。'],
      deep: ['深度模式预计 18 次请求', '更充分，但仍控制成本。']
    };

    async function loadModelProfiles() {
      try {
        const data = await fetch('/api/model-profiles').then(response => response.json());
        modelProfiles = Array.isArray(data.profiles) ? data.profiles : [];
        for (const profile of modelProfiles) {
          const option = document.createElement('option');
          option.value = profile.family;
          option.textContent = profile.display_name;
          modelFamilySelect.appendChild(option);
        }
      } catch (error) {
        modelSuggestions.innerHTML = '<strong>模型名提示</strong><span>模型族信息加载失败，不影响手动检测。</span>';
      }
    }

    function payloadFromForm() {
      const data = new FormData(form);
      return {
        base_url: data.get('base_url'),
        api_key: data.get('api_key'),
        claimed_model: data.get('claimed_model'),
        api_type: data.get('api_type'),
        level: data.get('level'),
        timeout_seconds: Number(data.get('timeout_seconds') || 60)
      };
    }

    async function postJson(path, payload) {
      const response = await fetch(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || '请求失败');
      return body;
    }

    function setBusy(isBusy) {
      checkBtn.disabled = isBusy;
      dryBtn.disabled = isBusy;
      checkBtn.textContent = isBusy ? '检测中...' : '开始检测';
    }

    function renderProgress(title, detail, percent) {
      result.innerHTML = `
        <div class="progress-card">
          <div class="progress-title">${escapeHtml(title)}</div>
          <div>${escapeHtml(detail)}</div>
          <div class="progress-bar"><span style="width: ${Math.max(4, Math.min(100, Number(percent || 0)))}%"></span></div>
          <div>页面可以保持打开，API Key 不会写入报告。</div>
        </div>
      `;
    }

    function renderReport(report) {
      lastReport = report;
      const consistency = report.claim_consistency || '';
      const confidence = report.confidence || '';
      const topMatches = Array.isArray(report.top_matches) ? report.top_matches : [];
      const evidence = Array.isArray(report.evidence) ? report.evidence : [];
      const limitations = Array.isArray(report.limitations) ? report.limitations : [];
      const diagnostics = report.diagnostics || {};
      const modelProfile = report.model_profile || {};
      const checks = report.checks || {};
      const behaviorFingerprint = report.behavior_fingerprint || {};
      const familyLikelihoods = Array.isArray(report.family_likelihoods) ? report.family_likelihoods : [];
      const verdict = verdictForReport(report);
      const badgeClass = consistency || (report.status === 'dry_run' ? 'dry-run' : 'unavailable');

      result.innerHTML = `
        <div class="result-head">
          <h2>${escapeHtml(verdict.title)}</h2>
          <span class="badge ${escapeHtml(badgeClass)}">${escapeHtml(verdict.badge)}</span>
        </div>
        <div class="verdict-card">
          <strong>${escapeHtml(verdict.headline)}</strong>
          <p>${escapeHtml(verdict.detail)}</p>
          ${renderMetricGrid(report, topMatches)}
        </div>
        ${report.risk_level ? `<div class="risk-banner">总体风险：${escapeHtml(labelRisk(report.risk_level))}</div>` : ''}
        ${topMatches.length ? `<div class="prob-list">${topMatches.map(renderProbability).join('')}</div>` : ''}
        ${renderModelProfile(modelProfile)}
        ${renderChecks(checks)}
        ${renderBehaviorFingerprint(behaviorFingerprint)}
        ${renderFamilyLikelihoods(familyLikelihoods)}
        ${evidence.length ? `<div class="evidence-list">${evidence.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}</div>` : ''}
        ${renderDiagnostics(diagnostics)}
        ${renderFixSuggestions(report, diagnostics)}
        <div class="result-actions">
          <button class="small-action" type="button" onclick="downloadReport('json')">下载 JSON</button>
          <button class="small-action" type="button" onclick="downloadReport('markdown')">下载 Markdown</button>
          <button class="small-action" type="button" onclick="downloadReport('html')">下载 HTML</button>
        </div>
        ${limitations.length ? `<div class="details"><strong>局限说明</strong>${limitations.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}</div>` : ''}
        <div class="details">
          <strong>JSON 报告</strong>
          <pre>${escapeHtml(JSON.stringify(displayReportForUser(report), null, 2))}</pre>
        </div>
      `;
    }

    function verdictForReport(report) {
      if (report.status === 'dry_run') {
        const count = Number(report.estimated_request_count || 0);
        return {
          title: '配置可用，可以开始检测',
          headline: `预计消耗 ${count} 次 API 请求`,
          detail: 'dry-run 没有发起真实模型请求，只检查配置格式和预计成本。',
          badge: 'dry-run'
        };
      }
      if (report.status === 'auth_error') {
        return {
          title: '认证没有通过',
          headline: 'API 地址有响应，但 Key 或权限被拒绝',
          detail: '先换一个有效 key，或确认这个 key 是否有权限访问所填模型。',
          badge: '不可判断'
        };
      }
      if (report.status === 'request_error') {
        return {
          title: 'API 拒绝了请求参数',
          headline: '优先检查模型名、API 类型和 base_url',
          detail: '这通常不是工具失效，而是中转站不接受当前模型名或协议格式。',
          badge: '不可判断'
        };
      }
      if (report.status === 'endpoint_error') {
        return {
          title: 'API 暂时没有打通',
          headline: '还没有拿到可用于判断模型的响应',
          detail: '先按下方访问诊断修正地址、协议类型、网络或 key。',
          badge: '不可判断'
        };
      }
      const consistency = report.claim_consistency || 'unavailable';
      if (consistency === 'high') {
        return {
          title: '纯度结论：高度吻合',
          headline: '这条 API 链路很像它声称的模型',
          detail: '协议特征、模型自报、行为探针和风险项整体支持当前声明。',
          badge: '高'
        };
      }
      if (consistency === 'medium') {
        return {
          title: '纯度结论：需要复核',
          headline: '有证据支持声称模型，但还不够干净',
          detail: '建议切换到深度模式，或对比同模型官方/可信渠道的输出。',
          badge: '中'
        };
      }
      if (consistency === 'low') {
        return {
          title: '纯度结论：明显可疑',
          headline: '当前结果不像它声称的模型',
          detail: '建议检查中转站配置，或换一个可信 endpoint 重新测试。',
          badge: '低'
        };
      }
      return {
        title: '纯度结论：暂不可判断',
        headline: '成功响应不足，无法给出模型身份判断',
        detail: '先处理访问诊断中的问题，再重新检测。',
        badge: '不可判断'
      };
    }

    function renderMetricGrid(report, topMatches) {
      const top = topMatches && topMatches.length ? topMatches[0] : null;
      const topModel = top ? displayModelLabel(top.model || '') : '暂无';
      const topPct = top ? `${Math.round(Number(top.probability || 0) * 1000) / 10}%` : 'n/a';
      const requestCount = report.estimated_request_count || report.planned_request_count || 'n/a';
      return `
        <div class="metric-grid">
          <div class="metric-card"><b>${escapeHtml(topModel)}</b><span>最可能匹配：${escapeHtml(topPct)}</span></div>
          <div class="metric-card"><b>${escapeHtml(labelOf(report.confidence || 'none'))}</b><span>报告置信度</span></div>
          <div class="metric-card"><b>${escapeHtml(String(requestCount))}</b><span>预计/计划请求数</span></div>
        </div>
      `;
    }

    function renderFixSuggestions(report, diagnostics) {
      const suggestions = [];
      if (report.status === 'dry_run') {
        suggestions.push('确认请求数可以接受后，点击“开始检测”运行真实探针。');
      }
      if (report.status === 'auth_error') {
        suggestions.push('重新复制 API key，确认没有多余空格。');
        suggestions.push('检查 key 是否绑定了当前模型或当前中转站套餐。');
      }
      if (report.status === 'request_error') {
        suggestions.push('把“声称模型”改成中转站文档里完全一致的模型名。');
        suggestions.push('如果你填的是 Claude，请确认 API 类型是 Anthropic Messages API 还是 OpenAI-compatible 包装。');
      }
      if (report.status === 'endpoint_error') {
        suggestions.push('确认 API 地址不是网站首页，而是文档里的 base_url。');
        suggestions.push('OpenAI-compatible 通常以 /v1 结尾；Anthropic 中转常见 /v1 或 /anthropic。');
      }
      const hints = Array.isArray(diagnostics.hints) ? diagnostics.hints : [];
      for (const item of hints.slice(0, 3)) suggestions.push(item);
      const unique = [...new Set(suggestions)].slice(0, 5);
      if (!unique.length) return '';
      return `
        <div class="details">
          <strong>下一步建议</strong>
          <div class="fix-list">${unique.map(item => `<div class="fix-item">${escapeHtml(item)}</div>`).join('')}</div>
        </div>
      `;
    }

    function renderChecks(checks) {
      const entries = Object.entries(checks || {});
      if (!entries.length) return '';
      return `
        <div class="details">
          <strong>风险检查</strong>
          ${entries.map(([name, item]) => {
            const status = item && item.status ? item.status : 'inconclusive';
            const summary = item && item.summary ? item.summary : '';
            return `<div>• ${escapeHtml(checkLabel(name))}：${escapeHtml(labelCheckStatus(status))}。${escapeHtml(summary)}</div>`;
          }).join('')}
        </div>
      `;
    }

    function renderBehaviorFingerprint(fingerprint) {
      const entries = Object.entries(fingerprint || {});
      if (!entries.length) return '';
      return `
        <div class="details">
          <strong>行为画像</strong>
          ${entries.map(([name, item]) => {
            const score = item && typeof item.score === 'number' ? item.score.toFixed(2) : 'n/a';
            const count = item && Number.isFinite(Number(item.probe_count)) ? Number(item.probe_count) : 0;
            return `<div>• ${escapeHtml(behaviorLabel(name))}：${escapeHtml(score)}（${count} 个探针）</div>`;
          }).join('')}
        </div>
      `;
    }

    function renderFamilyLikelihoods(items) {
      if (!items.length) return '';
      return `
        <div class="details">
          <strong>模型族倾向</strong>
          ${items.map(item => `<div>• ${escapeHtml(displayModelLabel(item.family || ''))}：${Math.round(Number(item.probability || 0) * 1000) / 10}%</div>`).join('')}
        </div>
      `;
    }

    function renderModelProfile(modelProfile) {
      const claimed = modelProfile && modelProfile.claimed ? modelProfile.claimed : null;
      const observed = modelProfile && Array.isArray(modelProfile.observed) ? modelProfile.observed : [];
      if (!claimed && !observed.length) return '';
      const consistency = modelProfile.family_consistency || 'unknown';
      const observedRows = observed.length
        ? observed.map(item => `<div>• ${escapeHtml(item.model || '')} → ${escapeHtml(item.display_name || item.family || 'unknown')}（${escapeHtml(item.match_type || 'none')}，${Number(item.count || 0)} 次）</div>`).join('')
        : '<div>• 暂无 API 自报模型</div>';
      return `
        <div class="details">
          <strong>模型族画像</strong>
          <div>声称模型族：${escapeHtml(profileLabel(claimed))}</div>
          <div>模型族一致性：${escapeHtml(labelProfileConsistency(consistency))}</div>
          ${observedRows}
        </div>
      `;
    }

    function renderProbability(item) {
      const probability = Number(item.probability || 0);
      const pct = Math.round(probability * 1000) / 10;
      return `
        <div class="prob-row">
          <strong>${escapeHtml(displayModelLabel(item.model || ''))}</strong>
          <div class="bar"><span style="width: ${Math.max(0, Math.min(100, pct))}%"></span></div>
          <span>${pct}%</span>
        </div>
      `;
    }

    function renderDiagnostics(diagnostics) {
      const hints = Array.isArray(diagnostics.hints) ? diagnostics.hints : [];
      if (!diagnostics.first_error && !hints.length) return '';
      return `
        <div class="details">
          <strong>访问诊断</strong>
          ${diagnostics.effective_base_url ? `<div>实际请求 Base URL：${escapeHtml(diagnostics.effective_base_url)}</div>` : ''}
          ${diagnostics.first_error ? `<div>首个错误：${escapeHtml(diagnostics.first_error)}</div>` : ''}
          ${hints.map(item => `<div>• ${escapeHtml(item)}</div>`).join('')}
        </div>
      `;
    }

    function labelOf(value) {
      if (value === 'high') return '高';
      if (value === 'medium') return '中';
      if (value === 'low') return '低';
      if (value === 'unavailable') return '不可判断';
      if (value === 'none') return '无';
      return value || '未知';
    }

    function labelProfileConsistency(value) {
      if (value === 'same_family') return '同一模型族';
      if (value === 'different_family') return '不同模型族';
      if (value === 'mixed') return '混合模型族';
      return '未知';
    }

    function labelRisk(value) {
      if (value === 'high') return '高';
      if (value === 'medium') return '中';
      if (value === 'low') return '低';
      return '未知';
    }

    function labelCheckStatus(value) {
      if (value === 'clean') return '未发现明显异常';
      if (value === 'anomaly') return '发现可疑异常';
      return '无法判断';
    }

    function checkLabel(value) {
      const labels = {
        model_identity: '模型身份',
        token_injection: 'Token 注入',
        context_truncation: '上下文截断',
        error_leakage: '错误泄漏',
        response_rewriting: '响应改写',
        stream_integrity: 'Stream 完整性'
      };
      return labels[value] || value;
    }

    function behaviorLabel(value) {
      const labels = {
        format_following: '格式遵循',
        reasoning: '推理',
        code: '代码',
        chinese: '中文',
        risk: '风险探针',
        general: '通用',
        overall: '总体'
      };
      return labels[value] || value;
    }

    function profileLabel(item) {
      if (!item || item.family === 'unknown') return 'unknown';
      return `${item.display_name || item.family}（${item.family || 'unknown'}，${item.match_type || 'none'}）`;
    }

    function displayModelLabel(value) {
      return value === 'unknown/out-of-set' ? '其他模型' : value;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    }

    function downloadReport(format) {
      if (!lastReport) return;
      const timestamp = new Date().toISOString().replaceAll(':', '').replaceAll('.', '');
      const extension = format === 'markdown' ? 'md' : format;
      const filename = `api-purecheck-${timestamp}.${extension}`;
      const content = format === 'html'
        ? reportToHtml(lastReport)
        : format === 'markdown'
        ? reportToMarkdown(lastReport)
        : JSON.stringify(displayReportForUser(lastReport), null, 2);
      const type = format === 'html'
        ? 'text/html;charset=utf-8'
        : format === 'markdown'
        ? 'text/markdown;charset=utf-8'
        : 'application/json;charset=utf-8';
      const blob = new Blob([content], {type});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }

    function reportToHtml(report) {
      return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>API PureCheck 纯度报告</title>
  <style>
    body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; margin: 32px; color: #151922; }
    pre { white-space: pre-wrap; background: #101827; color: #e7edf7; padding: 16px; border-radius: 8px; overflow: auto; }
  </style>
</head>
<body>
  <h1>API PureCheck 纯度报告</h1>
  <p>${escapeHtml(report.message || '')}</p>
  <pre>${escapeHtml(JSON.stringify(displayReportForUser(report), null, 2))}</pre>
</body>
</html>`;
    }

    function reportToMarkdown(report) {
      report = displayReportForUser(report);
      const config = report.config || {};
      const lines = [
        '# API PureCheck 纯度报告',
        '',
        `- 状态：\`${report.status || 'unknown'}\``,
        `- 说明：${report.message || ''}`,
        `- API 地址：\`${config.base_url || ''}\``,
        `- API Key：\`${config.api_key || ''}\``,
        `- 声称模型：\`${config.claimed_model || ''}\``,
        `- 检测强度：\`${config.level || ''}\``,
        '',
        '## 结论',
        '',
        `- 纯度结论：\`${labelOf(report.claim_consistency || 'unavailable')}\``,
        `- 报告置信度：\`${labelOf(report.confidence || 'none')}\``,
        `- 总体风险：\`${labelRisk(report.risk_level || 'unknown')}\``
      ];
      if (Array.isArray(report.top_matches) && report.top_matches.length) {
        lines.push('', '## 最可能匹配', '', '| 模型 | 概率 |', '| --- | ---: |');
        for (const item of report.top_matches) {
          const pct = `${Math.round(Number(item.probability || 0) * 1000) / 10}%`;
          lines.push(`| \`${displayModelLabel(item.model || '')}\` | ${pct} |`);
        }
      }
      if (report.checks) {
        lines.push('', '## 风险检查', '');
        for (const [name, item] of Object.entries(report.checks)) {
          lines.push(`- ${checkLabel(name)}：\`${item.status || 'inconclusive'}\`。${item.summary || ''}`);
        }
      }
      if (Array.isArray(report.evidence) && report.evidence.length) {
        lines.push('', '## 主要证据', '');
        for (const item of report.evidence) lines.push(`- ${item}`);
      }
      if (Array.isArray(report.limitations) && report.limitations.length) {
        lines.push('', '## 局限说明', '');
        for (const item of report.limitations) lines.push(`- ${item}`);
      }
      return lines.join('\n');
    }

    function displayReportForUser(value) {
      if (Array.isArray(value)) return value.map(displayReportForUser);
      if (value && typeof value === 'object') {
        const result = {};
        for (const [key, item] of Object.entries(value)) {
          result[key] = displayReportForUser(item);
        }
        return result;
      }
      if (value === 'unknown/out-of-set') return '其他模型';
      return value;
    }

    dryBtn.addEventListener('click', async () => {
      try {
        renderProgress('正在预估请求数', '只检查配置和成本，不会发起真实模型请求。', 35);
        setBusy(true);
        const report = await postJson('/api/dry-run', payloadFromForm());
        renderReport(report);
      } catch (error) {
        result.innerHTML = `<div class="empty">配置错误：${escapeHtml(error.message)}</div>`;
      } finally {
        setBusy(false);
      }
    });

    toggleKeyBtn.addEventListener('click', () => {
      const shouldShow = keyInput.type === 'password';
      keyInput.type = shouldShow ? 'text' : 'password';
      toggleKeyBtn.textContent = shouldShow ? '隐藏' : '显示';
      toggleKeyBtn.setAttribute('aria-pressed', shouldShow ? 'true' : 'false');
      keyInput.focus();
    });

    levelSelect.addEventListener('change', () => {
      const copy = levelCopy[levelSelect.value] || levelCopy.standard;
      levelNote.innerHTML = `<strong>${escapeHtml(copy[0])}</strong><span>${escapeHtml(copy[1])}</span>`;
    });

    modelFamilySelect.addEventListener('change', () => {
      const selected = modelProfiles.find(profile => profile.family === modelFamilySelect.value);
      if (!selected) {
        modelSuggestions.innerHTML = '<strong>模型名提示</strong><span>选择模型族后，会显示常见模型名。中转站以自己的文档为准。</span>';
        return;
      }
      if (Array.isArray(selected.api_types) && selected.api_types.length === 1) {
        apiTypeSelect.value = selected.api_types[0];
      }
      const apiTypeHint = Array.isArray(selected.api_types) && selected.api_types.length
        ? `常见 API 类型：${selected.api_types.join(' / ')}。`
        : '';
      modelSuggestions.innerHTML = `
        <strong>${escapeHtml(selected.display_name)} 常见模型名</strong>
        <div class="chips">${selected.model_names.map(name => `<button class="chip" type="button" data-model="${escapeHtml(name)}">${escapeHtml(name)}</button>`).join('')}</div>
        ${apiTypeHint ? `<span>${escapeHtml(apiTypeHint)}</span>` : ''}
        <span>${escapeHtml(selected.notes)}</span>
      `;
    });

    modelSuggestions.addEventListener('click', (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) return;
      const model = target.getAttribute('data-model');
      if (!model) return;
      claimedModelInput.value = model;
      claimedModelInput.focus();
    });

    loadModelProfiles();

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        renderProgress('正在预估请求数', '先确认本次检测会消耗多少 API 请求。', 25);
        setBusy(true);
        const payload = payloadFromForm();
        const preview = await postJson('/api/dry-run', payload);
        const count = preview.estimated_request_count || 0;
        const ok = window.confirm(`本次检测预计发起 ${count} 次 API 请求。确认开始检测吗？`);
        if (!ok) {
          renderReport(preview);
          return;
        }
        renderProgress('正在运行纯度检测', '正在发送行为探针并汇总协议、概率和风险画像。', 68);
        const report = await postJson('/api/check', payload);
        renderReport(report);
      } catch (error) {
        result.innerHTML = `<div class="empty">检测失败：${escapeHtml(error.message)}</div>`;
      } finally {
        setBusy(false);
      }
    });
  </script>
</body>
</html>
"""
