"""A real model/tool loop. No cached answers and no model-controlled mutations."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from contracts import PROMPT, SCHEMA, VALIDATOR
from deployment_support import find_codex
from domain import ROOT, canonical, digest, now, read_inputs
from projection import ContractError, compare


class ModelError(RuntimeError):
    pass


class CodexAdapter:
    def __init__(self, work, timeout=90):
        self.work, self.timeout = Path(work), timeout
        self.work.mkdir(parents=True, exist_ok=True)
        self.schema = self.work / "decision.schema.json"
        self.schema.write_text(canonical(SCHEMA), encoding="utf-8")
        found = find_codex()
        self.exe = found

    def decide(self, context):
        if not self.exe:
            raise ModelError("没有找到Codex CLI，请配置FDE_CODEX_EXE并确认模型登录状态")
        args = [self.exe, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "--json",
                "--output-schema", str(self.schema), "--cd", str(self.work)]
        # Invocation-only configuration; keep the user's model/provider/credentials.
        for setting in ("mcp_servers.rea.enabled=false", "mcp_servers.node_repl.enabled=false",
                        "features.shell_tool=false", "features.multi_agent=false", "features.plugins=false",
                        "features.remote_plugin=false", "features.hooks=false", "skills.bundled.enabled=false",
                        "skills.include_instructions=false", "web_search=\"disabled\""):
            args += ["-c", setting]
        args += ["-"]
        started = time.monotonic()
        prompt = PROMPT + "\n本轮context JSON：\n" + canonical(context)
        try:
            result = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=self.timeout, shell=False,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as exc:
            raise ModelError(f"模型调用超过{self.timeout}秒，已中止；基础登记仍可用") from exc
        except OSError as exc:
            raise ModelError("无法启动已配置模型，请检查本机Codex CLI") from exc
        if result.returncode != 0:
            # Never publish raw stderr: a provider may include configuration data.
            raise ModelError(f"模型调用失败（退出码{result.returncode}），请在本机检查Codex连接后重试")
        messages, usage, thread_id = [], {}, None
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id")
            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})
            if event.get("type") == "item.completed":
                item = event.get("item", {})
                if item.get("type") in ("command_execution", "mcp_tool_call", "web_search"):
                    raise ModelError("检测到非业务工具调用；本次结果已拒绝")
                if item.get("type") == "agent_message":
                    messages.append(item.get("text", ""))
        if not messages or len(messages[-1]) > 16000:
            raise ModelError("模型没有返回可用的结构化建议")
        try:
            proposal = json.loads(messages[-1])
            VALIDATOR.validate(proposal)
        except Exception as exc:
            raise ModelError("模型输出不符合严格JSON契约，本次不生成可采纳建议") from exc
        return proposal, {"adapter": "codex-cli-live", "thread_id": thread_id, "usage": usage,
                          "duration_seconds": round(time.monotonic() - started, 2),
                          "request_sha256": digest(context), "system_prompt_sha256": digest(PROMPT),
                          "schema_sha256": digest(SCHEMA), "authentication": "existing_local_configuration",
                          "model_selection": "existing_configured_model_no_override", "cli_tools_enabled": False}


def business_tool(s, call, previous):
    args, name = call["arguments"], call["name"]
    if name != "get_evidence" and args["topic"] is not None:
        raise ContractError("此工具不接收topic")
    if name != "compare_plans" and (args["quantity"] is not None or args["ready_minute"] is not None):
        raise ContractError("只允许比较工具接收数量和时间")
    if name == "get_snapshot":
        return {k: copy.deepcopy(s[k]) for k in ("version", "display_sku", "store_id", "source_item_id", "as_of_minute",
                 "on_hand", "reserved", "blocked", "plan", "demand_due", "prep_minutes", "unreconciled_past_quantity")}
    if name == "get_evidence":
        _, meta, _ = read_inputs()
        all_evidence = {
            "task_schedule": {"plan": s["plan"], "prep_minutes": s["prep_minutes"],
                "confirmation": "制作岗位核实现场进度、可调整产能；店长确认缺失规则", "origin": "classroom_assumption"},
            "batch_rules": {"old_sellable_until": s["old_sellable_until"], "new_hold_minutes": s["new_hold_minutes"],
                "actual_batches": s["actual_batches"], "origin": "classroom_assumption", "not_general_safety_standard": True},
            "source_lineage": {"source_url": meta["source_url"], "attribution": meta["attribution"], "license": meta["license"],
                "source_item_id": s["source_item_id"], "seed_source_item_row": 35741, "seed_receipt_row": 3836,
                "limitations": meta["limitations"], "new_scraping_performed": False}}
        if args["topic"] == "all":
            return all_evidence
        if args["topic"] not in all_evidence:
            raise ContractError("请明确证据topic")
        return {args["topic"]: all_evidence[args["topic"]]}
    if name == "compare_plans":
        names = {t["name"] for t in previous}
        topics = {key for t in previous if t["name"] == "get_evidence" for key in t["output"]}
        if "get_snapshot" not in names or not {"task_schedule", "batch_rules"} <= topics:
            raise ContractError("比较前需要当前快照、任务与规则证据")
        if (args["quantity"] is None) != (args["ready_minute"] is None):
            raise ContractError("候选数量和时点须同时提供或同时为空")
        return compare(s, args["quantity"], args["ready_minute"])
    if name == "get_execution":
        return {"human_reviews": s["human_reviews"], "execution": s["execution"],
                "unreconciled_past_quantity": s["unreconciled_past_quantity"],
                "warning": "均为本次课堂操作者记录，不是企业实测或用户历史人审的新签名"}
    raise ContractError("未知工具")


def validate_recommendation(s, trigger, rec, trace):
    refs = rec["evidence_refs"]
    if not refs or not set(refs) <= {t["call_id"] for t in trace}:
        raise ContractError("建议引用了不存在的工具证据")
    comparisons = [t for t in trace if t["name"] == "compare_plans" and "error" not in t["output"]]
    cited = [t for t in comparisons if t["call_id"] in refs]
    if not cited:
        raise ContractError("建议须引用本轮真实比较结果")
    if trigger == "completion_recorded" and not any(t["name"] == "get_execution" for t in trace):
        raise ContractError("完成后复评须查询执行记录")
    if not 2 <= len(rec["checks"]) <= 5 or not 5 <= len(rec["summary"]) <= 150 or len(rec["explanation"]) > 1800:
        raise ContractError("建议摘要或人审项不符合契约")
    c = cited[-1]["output"]
    b = c["baseline"]
    uncertain = s["prep_minutes"] is None or s["unreconciled_past_quantity"] > 0 or b["status"] == "blocked"
    if uncertain and rec["status"] != "needs_verification":
        raise ContractError("关键条件不全，不允许给出可采纳动作或关闭风险")
    if rec["status"] == "adjust_existing":
        if (not c["action_adoptable"] or (rec["quantity"], rec["ready_minute"], rec["additional_quantity"]) !=
                (c["quantity"], c["ready_minute"], 0) or c["candidate"]["late_units"] >= b["late_units"]):
            raise ContractError("模型动作未通过当前版本的确定性计算校验")
    else:
        if any(rec[k] is not None for k in ("quantity", "ready_minute", "additional_quantity")):
            raise ContractError("观察或待核实状态不能给可采纳数量")
        if rec["status"] == "observe" and b.get("late_units", 0) > 0:
            raise ContractError("存在未解决迟供风险，不能关闭为正常观察")


class Agent:
    def __init__(self, store, work, adapter=None):
        self.store, self.work = store, Path(work)
        self.work.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter or CodexAdapter(self.work / "model-work")
        self.gate = threading.Lock()

    def start(self, sid, trigger, async_run=True):
        with self.store.lock:
            s = self.store.state(sid)
            for r in reversed(self.store.runs(sid)):
                if r["snapshot_version"] == s["version"] and r["status"] in ("queued", "running"):
                    return r
            r = {"id": uuid.uuid4().hex, "session_id": sid, "snapshot_version": s["version"], "trigger": trigger,
                 "status": "queued", "started_at_utc": now(), "finished_at_utc": None,
                 "snapshot_sha256": digest(s), "snapshot": s, "model_calls": [], "trace": [],
                 "recommendation": None, "error": None, "source": "live_model_not_replay"}
            self.store.save_run(r)
        if async_run:
            threading.Thread(target=self._execute, args=(copy.deepcopy(r),), daemon=True).start()
        else:
            self._execute(r)
        return next(x for x in self.store.runs(sid) if x["id"] == r["id"])

    def _persist(self, r):
        self.store.save_run(r)
        (self.work / f"run-{r['id']}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _execute(self, r):
        with self.gate:
            s = r["snapshot"]
            r["status"] = "running"
            self._persist(r)
            try:
                if self.store.state(r["session_id"])["version"] != r["snapshot_version"]:
                    raise ContractError("排队时状态已变化，请根据新版本重新调查")
                history = []
                for turn in range(1, 6):
                    context = {"trigger": r["trigger"], "snapshot_version": s["version"],
                               "scope": "1店1商品课堂模拟；只可读工具；写操作须人审", "history": history,
                               "remaining_rounds": 6 - turn}
                    proposal, receipt = self.adapter.decide(context)
                    r["model_calls"].append(dict(receipt, round=turn, returned=proposal, request_context=copy.deepcopy(context)))
                    self._persist(r)
                    if proposal["kind"] == "final":
                        if proposal["tool_calls"] or proposal["recommendation"] is None:
                            raise ContractError("最终输出结构冲突")
                        validate_recommendation(s, r["trigger"], proposal["recommendation"], r["trace"])
                        r.update(recommendation=proposal["recommendation"], status="completed")
                        break
                    if proposal["recommendation"] is not None or not 1 <= len(proposal["tool_calls"]) <= 3:
                        raise ContractError("工具选择数量或结构无效")
                    outputs = []
                    for call in proposal["tool_calls"]:
                        call_id = f"{r['id'][:8]}-T{len(r['trace']) + 1:02d}"
                        try:
                            output = business_tool(s, call, r["trace"])
                        except ContractError as exc:
                            output = {"error": str(exc), "action_adoptable": False, "quantity": None}
                        t = dict(call, call_id=call_id, at_utc=now(), snapshot_version=s["version"],
                                 input_sha256=digest(s), output=output, selected_by="live_model")
                        r["trace"].append(t)
                        outputs.append(t)
                    history.append({"model": proposal, "tool_results": outputs})
                    self._persist(r)
                else:
                    raise ModelError("达到5轮调查上限，未生成可采纳建议；可查看工具记录并重新调查")
                if self.store.state(r["session_id"])["version"] != s["version"]:
                    r.update(status="stale", error="调查期间状态已变化，此建议不允许采纳")
            except Exception as exc:
                r.update(status="unavailable", error=str(exc) if isinstance(exc, (ModelError, ContractError)) else "本次调查异常，未生成可采纳动作")
            r["finished_at_utc"] = now()
            self._persist(r)
