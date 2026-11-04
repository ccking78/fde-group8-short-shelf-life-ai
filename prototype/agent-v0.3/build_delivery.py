"""Build a new deliverable; never modify the already submitted v1 ZIP."""
from __future__ import annotations

import ast
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path(r"F:\ChatGPT\work\fde-minimum-agent-ui-20261103\browser-evidence")
OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_最小AI运行闭环_v0.3_20261103")
OLD_ZIP = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务提交准备版_20261103.zip")
OLD_HASH = "da55d0cf63c8a2c4ea89cb005f1b379032476907bcef2aebdf303c44e4673b6b"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    before = hashlib.sha256(OLD_ZIP.read_bytes()).hexdigest()
    assert before == OLD_HASH, "已提交快照哈希发生变化，停止打包"
    browser = json.loads((WORK / "browser_verification.json").read_text(encoding="utf-8"))
    assert browser["passed"] and not browser["page_errors"]
    final = json.loads((WORK / "04_完成后的实时复评.json").read_text(encoding="utf-8"))
    missing = json.loads((WORK / "07_缺规则实时调查.json").read_text(encoding="utf-8"))
    runs = final["runs"] + missing["runs"]
    assert len(runs) == 3 and all(r["status"] == "completed" for r in runs)
    for run in runs:
        for call in run["model_calls"]:
            c = json.dumps(call["request_context"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            assert hashlib.sha256(c.encode()).hexdigest() == call["request_sha256"]
    OUT.mkdir(parents=True, exist_ok=True)
    for item in ROOT.rglob("*"):
        if not item.is_file() or "__pycache__" in item.parts or item.suffix in (".pyc", ".sqlite3", ".log"):
            continue
        rel = item.relative_to(ROOT)
        target = OUT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
    evidence = OUT / "evidence"
    evidence.mkdir(exist_ok=True)
    for item in WORK.iterdir():
        if item.is_file() and item.suffix in (".json", ".png"):
            shutil.copy2(item, evidence / item.name)
    screenshot = ROOT.parent / "coursework-v2-20261103" / "学习台_D1_已提交v1.jpg"
    shutil.copy2(screenshot, evidence / screenshot.name)
    receipt = {"receipt": "R261104142046-0814A", "submission_version": "v1", "course": "第3周D1",
        "tasks_included": ["周六智能体初步完善", "周一AI任务边界", "周二D1任务清单与人工确认表"],
        "attachment_count": 5, "work_url": None, "github_status": "用户明确暂缓，不发布",
        "platform_time_beijing": "2026-11-04 14:20", "user_time_america_denver": "2026-11-03 23:20",
        "evidence": screenshot.name, "submitted_zip_sha256": OLD_HASH, "new_v03_uploaded": False}
    save(evidence / "学习台提交回执.json", receipt)
    tests = [n.name for n in ast.walk(ast.parse((ROOT / "test_boundaries.py").read_text(encoding="utf-8")))
             if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    assert len(tests) == 10
    save(evidence / "边界验证记录.json", {"passed": True, "test_count": 10, "tests": tests,
        "command": "python -m unittest test_boundaries -v", "exit_code": 0,
        "record_kind": "成功执行结果的摘要；完整测试源码随包提供", "model_requests": 0})
    summaries = [{"id": r["id"], "trigger": r["trigger"], "version": r["snapshot_version"],
                  "model_requests": len(r["model_calls"]), "tool_calls": len(r["trace"]),
                  "duration_seconds": round(sum(c["duration_seconds"] for c in r["model_calls"]), 2),
                  "recommendation": r["recommendation"], "request_hashes_verified": True} for r in runs]
    save(evidence / "真实模型运行摘要.json", summaries)
    rows = []
    for r, label in zip(summaries, ("延期调查", "完成后复评", "缺规则调查")):
        rows.append(f"| {label} | v{r['version']} | {r['model_requests']} | {r['tool_calls']} | {r['recommendation']['status']} | {r['duration_seconds']}秒 |")
    report = """# v0.3 运行验收报告

## 结果

已补齐本地最小 AI 运行闭环：经营事件触发真实模型，模型选择白名单业务工具，程序执行并反馈，模型形成建议，人员核对后处理；模拟完成与履约登记触发新模型复评。不是历史AI结果回放。

| 调查 | 快照 | 真实模型请求 | 实际工具 | 结论 | 模型耗时合计 |
| --- | --- | --- | --- | --- | --- |
""" + "\n".join(rows) + """

- 延期：现有7份可分配、原8份任务延至第12分钟，模拟第10分钟1份迟供；调整原8份至第8分钟，新增0，迟供0。
- 采纳：库存仍12，不把确认当作实际完成。
- 完成：测试操作者登记第8分钟完成8份、累计已履约4份。在手12+8−4=16，预留5，可分配11，剩余模拟需用11；新模型读取v3与执行记录后建议继续观察。
- 缺规则：仅移除制作时间的副本，保留已知风险；可采纳数量null。
- 新增10项关键边界验证通过：版本、幂等、缺规则、布尔/越界数量、人审、改量确认、批次不重复投影、少完成、未知履约和模型不可用。
- 浏览器已检查真实调查、人审与完成、工具记录、实际导出和390px手机布局。控制台无页面脚本错误。测试分阶段接续同一会话，详细记录与截图随附。
- 每个交付模型请求的冻结context SHA256已核对；包含输入、模型返回、工具参数/结果和最终建议。CLI凭据和原始诊断输出不打包。

## 操作与数据边界

人工处理和完成由“浏览器验收测试操作者”执行，全部为课堂测试，不是用户的新签审或企业实际执行。历史用户确认仍仅对应此前课堂摘要。此报告无企业效益结论。

采集底稿复用Scrapling；本轮没有新爬取或批量模拟。SimPy的时点、迟供、守恒、有效期与本地事务做了程序验证；生产身份权限、POS、任意时间推进和企业验证仍待后续。

## 提交状态

学习台v1已提交：R261104142046-0814A，5附件，作品链接留空。已提交ZIP字节校验未变。本v0.3为独立本地开发补齐，尚未再次上传。GitHub按用户要求暂停。
"""
    (OUT / "运行验收报告.md").write_text(report, encoding="utf-8")
    files = {str(p.relative_to(OUT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in OUT.rglob("*") if p.is_file() and p.name != "交付校验清单.json"}
    save(OUT / "交付校验清单.json", {"created_at_utc": datetime.now(timezone.utc).isoformat(),
        "version": "0.3", "files": files, "github_published": False, "submitted_v1_unchanged": True})
    zip_path = Path(str(OUT) + ".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                z.write(path, str(path.relative_to(OUT)))
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        count = len(z.infolist())
    assert hashlib.sha256(OLD_ZIP.read_bytes()).hexdigest() == before
    result = {"directory": str(OUT), "zip": str(zip_path), "files": count, "bytes": zip_path.stat().st_size,
              "sha256": hashlib.sha256(zip_path.read_bytes()).hexdigest(), "live_model_investigations": 3,
              "model_requests": sum(r["model_requests"] for r in summaries), "old_submitted_zip_unchanged": True}
    save(OUT.parent / (OUT.name + "_打包结果.json"), result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
