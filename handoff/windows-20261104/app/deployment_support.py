"""Locate an existing native Codex CLI without copying account configuration."""
from pathlib import Path
import os
import shutil


def local_work():
    if os.environ.get("FDE_AGENT_WORK"):
        return Path(os.environ["FDE_AGENT_WORK"]).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "FDEGroup8" / "agent-v0.3"


def find_codex():
    explicit = os.environ.get("FDE_CODEX_EXE")
    if explicit:
        p = Path(os.path.expandvars(explicit)).expanduser()
        if not p.is_file() or p.suffix.lower() != ".exe":
            raise ValueError("FDE_CODEX_EXE须指向组员本机的原生codex.exe，不能是cmd/ps1脚本")
        return str(p.resolve())
    candidates = []
    found = shutil.which("codex.exe")
    if found:
        candidates.append(Path(found))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates.append(local / "Programs/OpenAI/Codex/bin/codex.exe")
    config = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    candidates.extend([config / "packages/standalone/current/bin/codex.exe",
                       config / "packages/standalone/current/codex.exe"])
    app_bins = local / "OpenAI/Codex/bin"
    if app_bins.is_dir():
        candidates.extend(sorted(app_bins.glob("*/codex.exe"), key=lambda p: p.stat().st_mtime, reverse=True))
    npm_roots = [Path(os.environ.get("APPDATA", local)) / "npm/node_modules/@openai"]
    for command in ("codex.cmd", "codex.ps1"):
        shim = shutil.which(command)
        if shim:
            npm_roots.append(Path(shim).parent / "node_modules/@openai")
    for npm_root in npm_roots:
        if npm_root.is_dir():
            for pattern in ("codex/vendor/*/codex/codex.exe", "codex/node_modules/@openai/codex-win32-*/vendor/*/codex/codex.exe",
                            "codex-win32-*/vendor/*/codex/codex.exe"):
                candidates.extend(npm_root.glob(pattern))
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.lower() == ".exe":
            return str(candidate.resolve())
    return None
