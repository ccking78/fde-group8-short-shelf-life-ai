"""Windows handoff launcher. Offline checks never invoke the model."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
import uuid
import webbrowser
from datetime import datetime, timezone

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "app"))
from deployment_support import find_codex, local_work


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def report_dir():
    override = os.environ.get("FDE_HANDOFF_REPORT_DIR")
    if override:
        result = Path(override)
    else:
        result = local_work().parent / "handoff-reports"
    result.mkdir(parents=True, exist_ok=True)
    return result


def save_report(label, report):
    destination = report_dir() / (label + "-" + stamp() + ".json")
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("报告：" + str(destination), flush=True)
    return destination


def integrity():
    manifest = json.loads((PACKAGE / "package-manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        target = (PACKAGE / relative).resolve()
        if not target.is_relative_to(PACKAGE.resolve()):
            raise RuntimeError("文件清单含越界路径")
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise RuntimeError("交接文件缺失或已改动：" + relative + "；请重新完整解压原包")
    return len(manifest["files"])


def local_probe(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/bootstrap", timeout=2) as response:
            boot = json.load(response)
        return boot.get("app_id") == "fde-minimum-agent-0.3"
    except (ValueError, OSError, urllib.error.URLError):
        return False


def quiet_cli(exe, *args):
    return subprocess.run([exe, *args], capture_output=True, encoding="utf-8", errors="replace",
                          timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ensure_cli():
    exe = find_codex()
    if not exe:
        raise RuntimeError("未找到Codex CLI。先运行03_安装Codex_仅首次.cmd，再运行04_登录组员模型.cmd")
    return exe


def check():
    print("环境自检：不发起模型请求。", flush=True)
    if os.name != "nt" or sys.maxsize <= 2**32:
        raise RuntimeError("此便携版需要Windows 10/11的64位x64环境；ARM设备需AI另配原生运行时")
    count = integrity()
    print(f"[通过] {count}项交接文件SHA256", flush=True)
    lock = json.loads((PACKAGE / "tools/runtime-lock.json").read_text(encoding="utf-8"))
    versions = {name: importlib.metadata.version(name) for name in lock["packages"]}
    if versions != lock["packages"]:
        raise RuntimeError("随包依赖版本不匹配")
    from domain import read_inputs
    read_inputs()
    print("[通过] Python、依赖、SQLite与课堂输入校验", flush=True)
    run_tests()
    exe = find_codex()
    auth_ok = False
    cli_version = None
    if exe:
        version = quiet_cli(exe, "--version")
        if version.returncode:
            raise RuntimeError("Codex已找到但无法运行，请让部署AI核对其完整安装")
        cli_version = version.stdout.strip().splitlines()[0]
        if not cli_version.startswith("codex-cli "):
            raise RuntimeError("Codex版本输出不符合预期")
        help_result = quiet_cli(exe, "exec", "--help")
        if help_result.returncode or not all(flag in help_result.stdout for flag in ("--output-schema", "--ephemeral", "--json")):
            raise RuntimeError("Codex版本缺少所需结构化输出参数；请让部署AI安装受支持的版本")
        auth_ok = quiet_cli(exe, "login", "status").returncode == 0
        print("[通过] CLI可运行：" + cli_version, flush=True)
        print("[通过] 检测到本机登录状态；是否可用仍需真实试跑" if auth_ok else "[待处理] 未检测到标准登录；若已配自定义provider请直接试跑，否则运行04登录", flush=True)
    else:
        print("[待处理] 未安装Codex：离线汇报已可用；实时AI请先运行03、04", flush=True)
    record = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "package_files_verified": count,
              "python_version": platform.python_version(), "packages": versions, "domain_tests_passed": True,
              "codex_found": bool(exe), "codex_version": cli_version, "standard_login_detected": auth_ok,
              "new_model_requests": 0, "target_live_model_verified": False,
              "next_step": "运行05_真实AI试跑.cmd；必须成功后才声称这台电脑已接通实时AI"}
    save_report("environment", record)
    print("自检完成。离线展示可直接用；实时AI还需05试跑通过。", flush=True)
    return 0


def run_tests():
    root = report_dir() / ("boundary-tests-" + stamp())
    root.mkdir()
    previous = os.environ.get("FDE_TEST_WORK")
    os.environ["FDE_TEST_WORK"] = str(root)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName("test_boundaries")
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        if not result.wasSuccessful():
            raise RuntimeError("库存/人审边界自检未通过")
        print(f"[通过] {result.testsRun}项关键业务边界；没有调用模型", flush=True)
    finally:
        if previous is None:
            os.environ.pop("FDE_TEST_WORK", None)
        else:
            os.environ["FDE_TEST_WORK"] = previous


def start(args):
    integrity()
    port = args.port
    if local_probe(port):
        print(f"检测到本机已有v0.3服务：http://127.0.0.1:{port}/；保留其原账本。", flush=True)
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return 0
    from domain import read_inputs
    from server import App, LocalHTTPServer, handler
    read_inputs()
    work = Path(args.work).resolve() if args.work else local_work()
    app = App(work)
    try:
        httpd = LocalHTTPServer(("127.0.0.1", port), handler(app))
    except OSError as exc:
        raise RuntimeError(f"端口{port}被占用。不要关闭陌生进程；让部署AI选用其他端口并记录地址。") from exc
    print(f"实时智能体已启动：http://127.0.0.1:{port}/", flush=True)
    print("账本与新运行记录：" + str(work), flush=True)
    print("此窗口须保持打开；按Ctrl+C停止。登记延期/重新调查/完成复评会发起真实模型请求。", flush=True)
    print("如果模型尚未配置，页面可打开，但不能声称实时AI已接通；请运行03/04/05。", flush=True)
    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("服务已停止，账本保留。", flush=True)
    finally:
        httpd.server_close()
    return 0


def live_smoke():
    integrity()
    exe = ensure_cli()
    print("将用组员本机配置和账号发起一次真实延期调查，可能消耗额度。", flush=True)
    print("通常约1分钟，最多5轮、每轮90秒；这不是历史结果回放。", flush=True)
    from domain import Store, apply_delay, now
    from runtime import Agent
    work = report_dir() / ("live-smoke-" + stamp())
    work.mkdir()
    store = Store(work / "ledger.sqlite3")
    s = store.create()
    sid = s["session_id"]
    store.mutate(sid, "handoff-delay", {"expected_version": 0}, lambda state, db: apply_delay(state))
    agent = Agent(store, work / "runs")
    agent.start(sid, "eta_changed")
    deadline = time.monotonic() + 480
    last_progress = None
    next_progress = 0
    while True:
        run = store.runs(sid)[-1]
        progress = (run["status"], len(run["model_calls"]), len(run["trace"]))
        if progress != last_progress or time.monotonic() >= next_progress:
            print(f"调查状态：{progress[0]}；已完成模型请求{progress[1]}，业务工具{progress[2]}", flush=True)
            last_progress, next_progress = progress, time.monotonic() + 15
        if run["status"] not in ("queued", "running"):
            break
        if time.monotonic() > deadline:
            raise RuntimeError("部署试跑超过总等待上限，未声称成功；请查看独立试跑目录")
        time.sleep(1)
    rec = run["recommendation"] or {}
    passed = run["status"] == "completed" and rec.get("status") == "adjust_existing" and (
        rec.get("quantity"), rec.get("ready_minute"), rec.get("additional_quantity")) == (8, 8, 0)
    record = {"checked_at_utc": now(), "passed": passed, "live_model": True,
              "run_status": run["status"], "model_requests": len(run["model_calls"]),
              "business_tools": len(run["trace"]), "recommendation": run["recommendation"], "error": run["error"],
              "full_run_path": str(work / "runs" / ("run-" + run["id"] + ".json")),
              "human_review_performed": False, "business_completion_recorded": False,
              "note": "仅部署试跑；未采纳、未执行，不代表企业运行或用户新签审"}
    save_report("live-smoke", record)
    if not passed:
        raise RuntimeError("真实AI试跑未通过：" + str(run["error"] or run["status"]) + "；离线汇报仍可用")
    print("[通过] 这台电脑已完成一次真实AI工具调查：原8份调整到第8分钟，新增0；尚无人审。", flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "start", "live-smoke", "login", "device-login", "cli", "test"])
    parser.add_argument("--port", type=int, default=int(os.environ.get("FDE_PORT", "8765")))
    parser.add_argument("--work")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "check":
            return check()
        if args.action == "start":
            return start(args)
        if args.action == "live-smoke":
            return live_smoke()
        if args.action == "test":
            run_tests()
            return 0
        if args.action == "cli":
            exe = find_codex()
            if not exe:
                return 3
            print(exe)
            return 0
        exe = ensure_cli()
        print("请使用组员自己的账号完成官方登录；本工具不读取、复制或导出登录凭据。", flush=True)
        command = [exe, "login"] + (["--device-auth"] if args.action == "device-login" else [])
        return subprocess.call(command)
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired, importlib.metadata.PackageNotFoundError) as exc:
        print("[未完成] " + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
