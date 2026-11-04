"""Small, traceable data pilot. Projections never mutate observed inventory.

The input contract is a classroom draft, not the future production event schema.
Only the existing one-store, one-SKU ETA change is admitted in this pilot.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.metadata
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import simpy

if simpy.__version__ != "4.1.2":
    raise RuntimeError("此小样例固定使用SimPy 4.1.2，请按requirements.lock安装")

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103")
DEFAULT_DOWNLOADS = Path(r"F:\ChatGPT\downloads\FDE_经营异常优化_20261103")
DEFAULT_OUT = Path(r"F:\ChatGPT\outputs\FDE_数据管线小样例_20261103")
WORK = Path(r"F:\ChatGPT\work\FDE_数据管线小样例_20261103")
RUNTIME = Path(r"F:\ChatGPT\work\runtimes\fde-data-simulation\runtime.json")
VERSION = "classroom-data-pilot-0.1"
INPUT_DIR = "01_输入_可供智能体"
REPORT_DIR = "02_运行与验收_不作为AI输入"
RULES = {
    "version": "pilot-rules-0.1",
    "time_unit": "minute",
    "horizon_inclusive": True,
    "same_time_order": ["expiry", "projected_supply", "simulated_need_due"],
    "max_business_events": 32,
    "max_scheduler_steps": 256,
    "randomness": {"enabled": False, "seed_reserved": 20261103},
    "scope": "1店1SKU；沿用既有情景；唯一外部增量为预计完成时间4改12",
}
KINDS = {
    "scraped_fact": "真实采集",
    "derived_from_scraped": "真实字段派生",
    "scenario_assumption": "课堂情景假设",
    "simulated_increment": "模拟增量",
}


class DataContractError(ValueError):
    """A bounded input or a state transition violates the pilot contract."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def require_int(value, name, minimum=0, maximum=10000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise DataContractError(f"{name}: 必须是{minimum}至{maximum}的整数")


def leaves(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child, f"{prefix}.{key}" if prefix else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from leaves(child, f"{prefix}[{index}]")
    else:
        yield prefix, value


def validate_snapshot(case):
    for field in ("on_hand", "reserved", "blocked", "actual_discard_recorded"):
        require_int(case.get(field), field)
    if case["reserved"] + case["blocked"] > case["on_hand"]:
        raise DataContractError("预留与不可分配之和超过在手")
    for field in ("window_minutes", "old_sellable_until", "new_hold_minutes"):
        require_int(case.get(field), field, minimum=1, maximum=1440)
    require_int(case.get("as_of_minute"), "as_of_minute", maximum=case["window_minutes"])
    if case.get("prep_minutes") is not None:
        require_int(case["prep_minutes"], "prep_minutes", minimum=1, maximum=1440)
    plan = case.get("plan", {})
    require_int(plan.get("quantity"), "plan.quantity")
    for field in ("ready_minute", "alternative_ready_minute"):
        require_int(plan.get(field), f"plan.{field}", maximum=1440)
    require_int(plan.get("alternative_capacity"), "plan.alternative_capacity")
    if plan["quantity"] and plan["ready_minute"] < case["as_of_minute"]:
        raise DataContractError("仍待完成的任务预计完成早于快照时间")
    if not isinstance(plan.get("id"), str) or not plan["id"]:
        raise DataContractError("缺任务编号")
    if plan.get("status") not in ("not_started", "in_progress"):
        raise DataContractError("本切片只处理未完成任务")
    demand = case.get("demand_due")
    if not isinstance(demand, list) or not 1 <= len(demand) <= 8:
        raise DataContractError("模拟需用时点必须为1至8条")
    for row in demand:
        require_int(row.get("minute"), "demand_due.minute", maximum=case["window_minutes"])
        require_int(row.get("quantity"), "demand_due.quantity", minimum=1)
        if row["minute"] < case["as_of_minute"]:
            raise DataContractError("未来需用时点早于当前快照")
    if not case.get("store_id") or not case.get("source_item_id"):
        raise DataContractError("缺门店或商品标识")


def create_delay_event(case):
    return {
        "event_id": "SIM-INC-01", "scenario_id": "PILOT-01", "store_id": case["store_id"],
        "sku_id": case["source_item_id"], "entity_id": case["plan"]["id"],
        "type": "task_eta_changed", "event_minute": 1, "recorded_minute": 1,
        "previous_version": 0, "new_version": 1,
        "payload": {"before": case["plan"]["ready_minute"], "after": 12},
        "provenance": {"kind": "simulated_increment", "rule_version": RULES["version"]},
    }


class EventLedger:
    """An atomic in-memory ETA ledger, with ID collision and version checks."""

    def __init__(self, snapshot):
        validate_snapshot(snapshot)
        self.snapshot = copy.deepcopy(snapshot)
        self.version = 0
        self.events = []
        self._fingerprints = {}

    def apply(self, event):
        event_hash = digest(event)
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id or len(event_id) > 80:
            raise DataContractError("事件编号无效")
        if event_id in self._fingerprints:
            if self._fingerprints[event_id] != event_hash:
                raise DataContractError("相同事件编号对应不同内容")
            return {"status": "duplicate_ignored", "version": self.version}
        if len(self.events) >= 1:
            raise DataContractError("本次小样例最多接收1条外部增量事件")
        if event.get("type") != "task_eta_changed":
            raise DataContractError("此临时切片只接收预计完成时间变化")
        for key, expected in (("store_id", self.snapshot["store_id"]),
                              ("sku_id", self.snapshot["source_item_id"]),
                              ("entity_id", self.snapshot["plan"]["id"])):
            if event.get(key) != expected:
                raise DataContractError(f"{key}: 引用不匹配")
        if event.get("provenance") != {"kind": "simulated_increment", "rule_version": RULES["version"]}:
            raise DataContractError("事件缺正确的模拟来源或规则版本")
        if event.get("scenario_id") != "PILOT-01":
            raise DataContractError("情景编号不匹配")
        for field in ("event_minute", "recorded_minute", "previous_version", "new_version"):
            require_int(event.get(field), field, maximum=1440)
        if not self.snapshot["as_of_minute"] <= event["event_minute"] <= event["recorded_minute"] <= self.snapshot["window_minutes"]:
            raise DataContractError("事件时间或登记时间超出切片窗口")
        if event["previous_version"] != self.version or event["new_version"] != self.version + 1:
            raise DataContractError("状态版本冲突")
        payload = event.get("payload", {})
        for key in ("before", "after"):
            require_int(payload.get(key), f"payload.{key}", maximum=1440)
        if payload["before"] != self.snapshot["plan"]["ready_minute"]:
            raise DataContractError("事件修改前值与当前记录不符")
        updated = copy.deepcopy(self.snapshot)
        updated["plan"]["ready_minute"] = payload["after"]
        updated["as_of_minute"] = event["recorded_minute"]
        validate_snapshot(updated)
        self.snapshot = updated
        self.version = event["new_version"]
        self.events.append(copy.deepcopy(event))
        self._fingerprints[event_id] = event_hash
        return {"status": "applied", "version": self.version}


def project(case):
    """Forecast unreserved demand on [as_of, horizon], including the endpoint.

    All supply and demand transitions are hypothetical. Snapshot on_hand/reserved
    remain factual *within the classroom scenario* and are never written here.
    """
    validate_snapshot(case)
    initial = case["on_hand"] - case["reserved"] - case["blocked"]
    horizon = case["window_minutes"]
    batches = [{"id": "existing", "quantity": initial, "deadline": case["old_sellable_until"]}]
    business_events = [(case["old_sellable_until"], 0, "expiry", "existing")]
    quantity, ready = case["plan"]["quantity"], case["plan"]["ready_minute"]
    if quantity:
        business_events += [(ready, 1, "projected_supply", quantity),
                            (ready + case["new_hold_minutes"], 0, "expiry", "planned")]
    business_events += [(row["minute"], 2, "simulated_need_due", row["quantity"]) for row in case["demand_due"]]
    if len(business_events) > RULES["max_business_events"]:
        raise DataContractError("模拟事件数超限")
    late = served = excluded = supplied = unit_minutes = 0
    first_late = None
    backlog = []
    trace = []

    def fulfill(wanted, now):
        nonlocal served
        remaining = wanted
        for batch in sorted(batches, key=lambda b: b["deadline"]):
            if batch["deadline"] <= now:
                continue
            take = min(remaining, batch["quantity"])
            batch["quantity"] -= take
            remaining -= take
            served += take
        return remaining

    def observe(now, kind, amount):
        remaining = sum(b["quantity"] for b in batches if b["deadline"] > now)
        balance = initial + supplied == served + remaining + excluded
        if not balance:
            raise DataContractError("可分配供给对账失败")
        trace.append({"minute": now, "event": kind, "quantity": amount,
                      "projected_available": remaining,
                      "projected_backlog": sum(b["quantity"] for b in backlog),
                      "projected_supplied": supplied, "projected_served": served,
                      "late_units_so_far": late, "conservation_pass": balance})

    observe(case["as_of_minute"], "projection_start", 0)
    env = simpy.Environment(initial_time=case["as_of_minute"])

    def transitions():
        nonlocal late, served, excluded, supplied, unit_minutes, first_late, backlog
        for minute, _, kind, amount in sorted(business_events):
            if minute < case["as_of_minute"]:
                continue
            yield env.timeout(minute - env.now)
            if kind == "expiry":
                for batch in batches:
                    if batch["id"] == amount:
                        excluded += batch["quantity"]
                        batch["quantity"] = 0
            elif kind == "projected_supply":
                supplied += amount
                batches.append({"id": "planned", "quantity": amount, "deadline": minute + case["new_hold_minutes"]})
                for pending in backlog:
                    before = pending["quantity"]
                    pending["quantity"] = fulfill(before, minute)
                    unit_minutes += (before - pending["quantity"]) * (minute - pending["due"])
                backlog = [pending for pending in backlog if pending["quantity"]]
            else:
                left = fulfill(amount, minute)
                if left:
                    late += left
                    first_late = minute if first_late is None else first_late
                    backlog.append({"quantity": left, "due": minute})
            observe(minute, kind, amount)

    env.process(transitions())
    scheduler_steps = 0
    # Numeric run(until=horizon) excludes ordinary events exactly at the horizon.
    # A capped step loop deliberately includes demand at minute 20 in this model.
    while env.peek() <= horizon:
        if scheduler_steps >= RULES["max_scheduler_steps"]:
            raise DataContractError("SimPy调度步数超限")
        env.step()
        scheduler_steps += 1
    unit_minutes += sum(p["quantity"] * (horizon - p["due"]) for p in backlog)
    return {
        "kind": "hypothetical_projection", "engine": "SimPy", "simpy_version": simpy.__version__,
        "available_initial": initial, "quantity": quantity, "ready_minute": ready if quantity else None,
        "forecast_quantity": sum(row["quantity"] for row in case["demand_due"]),
        "late_units": late, "first_late_minute": first_late,
        "backlog_end": sum(p["quantity"] for p in backlog), "delay_unit_minutes": unit_minutes,
        "served_by_horizon": served,
        "remaining_available": sum(b["quantity"] for b in batches if b["deadline"] > horizon),
        "expired_unavailable": excluded, "actual_discard_recorded": case["actual_discard_recorded"],
        "missing_action_rules": ["prep_minutes"] if case.get("prep_minutes") is None else [],
        "conservation_pass": all(row["conservation_pass"] for row in trace),
        "scheduler_steps": scheduler_steps, "trace": trace,
        "meaning": "需用时点未覆盖量；后续可以补供；不等于损失销量或实测经营收益",
    }


def check_adjustment(case, quantity=8, ready=8):
    validate_snapshot(case)
    if case.get("prep_minutes") is None:
        return {"action_adoptable": False, "quantity": None, "missing": ["prep_minutes"]}
    require_int(quantity, "candidate.quantity", minimum=1)
    require_int(ready, "candidate.ready_minute", minimum=1, maximum=1440)
    if (case["plan"]["status"] != "not_started"
            or ready < case["as_of_minute"] + case["prep_minutes"]
            or quantity > case["plan"]["alternative_capacity"]
            or ready < case["plan"]["alternative_ready_minute"]):
        return {"action_adoptable": False, "quantity": None, "reason": "调整未满足模拟进度、时长或产能条件"}
    adjusted = copy.deepcopy(case)
    adjusted["plan"].update(quantity=quantity, ready_minute=ready)
    return {"action_adoptable": True, "requires_human_confirmation": True,
            "candidate_feasibility_only": True,
            "quantity": quantity, "ready_minute": ready, "additional_quantity": 0,
            "projection": project(adjusted)}


def read_source_csv(downloads, name, partial=False):
    body = (downloads / name).read_bytes()
    if partial:
        body = body[:body.rfind(b"\n") + 1]
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))


def build_inputs(source, downloads, output):
    source_data = source / "附件_数据与来源"
    source_manifest = load(source_data / "数据清单.json")
    checks = []
    names = ("E1_Receipts_prefix_4MiB.csv", "E3_Item_on_Receipt_prefix_4MiB.csv", "E4_Menu_Items.csv")
    acquisitions = {row["file"]: row for row in source_manifest["source_acquisitions"]}
    for name in names:
        actual = hashlib.sha256((downloads / name).read_bytes()).hexdigest()
        if actual != acquisitions[name]["sha256"]:
            raise DataContractError(f"源文件哈希与Scrapling采集记录不符: {name}")
        checks.append({"file": name, "sha256": actual, "verified": True,
                       "acquisition": acquisitions[name]["acquisition"],
                       "fetched_at_utc": acquisitions[name]["fetched_at_utc"]})
    selected = source_manifest["selected_source_row"]
    receipts = read_source_csv(downloads, names[0], partial=True)
    items = read_source_csv(downloads, names[1], partial=True)
    menu = read_source_csv(downloads, names[2])
    receipt = receipts[selected["source_receipt_row"] - 1]
    item = items[selected["source_item_row"] - 1]
    menu_item = next(row for row in menu if row["Inv_Num"] == item["Inv_Num"])
    matches = [receipt["Receipt_ID"] == item["Receipt_ID"] == selected["receipt_id"],
               item["Inv_Num"] == selected["source_item_id"],
               float(item["Count"]) == selected["source_count"],
               menu_item["Item_Description"] == selected["source_item_name"],
               receipt["Date"] == selected["source_date"],
               receipt["Start_Time"] == selected["source_start_time"],
               receipt["End_Time"] == selected["source_end_time"],
               receipt["Store_Num"] == selected["source_store"]]
    if not all(matches):
        raise DataContractError("选定商品、收据和菜单不能按原ID及源行号核对")
    base = next(row for row in load(source_data / "04_模拟情景.json") if row["id"] == "normal")
    fields = ("display_sku", "source_item_id", "store_id", "window_minutes", "on_hand", "reserved", "blocked",
              "old_sellable_until", "new_hold_minutes", "prep_minutes", "plan", "demand_due", "actual_discard_recorded")
    base = {key: copy.deepcopy(base[key]) for key in fields}
    base.update(as_of_minute=0, id="PILOT-01")
    validate_snapshot(base)
    if base["source_item_id"] != selected["source_item_id"]:
        raise DataContractError("模拟商品映射与源商品不一致")
    observed_keys = ("receipt_id", "source_store", "source_date", "source_start_time", "source_end_time",
                     "source_item_id", "source_item_name", "source_count")
    observed = {key: selected[key] for key in observed_keys}
    date = datetime.strptime(observed["source_date"], "%Y-%m-%d")
    derived = {"source_hour": int(observed["source_start_time"].split(":")[0]),
               "source_weekday_iso": date.isoweekday(), "menu_match": True}
    event = create_delay_event(base)
    missing_overlay = {"prep_minutes": None}
    record = {"public_seed": observed, "derived": derived, "scenario": base, "increment": event,
              "missing_overlay": missing_overlay}
    lineage = []
    for field, value in leaves(record):
        section = field.split(".", 1)[0]
        kind = {"public_seed": "scraped_fact", "derived": "derived_from_scraped",
                "scenario": "scenario_assumption", "increment": "simulated_increment",
                "missing_overlay": "scenario_assumption"}[section]
        rule = {"public_seed": "按原ID和源行号精确核对；保留原字段值",
                "derived": "日期/时间确定性解析或菜单ID关联；时区未知，不转换时区",
                "scenario": "沿用既有课堂情景；不据不完整前缀拟合需求强度",
                "increment": "课堂预设：第1分钟登记原任务预计完成4改12",
                "missing_overlay": "在延期快照上仅删除制作时间；缺规则副本，不新增业务事件"}[section]
        if field == "scenario.source_item_id" or field == "increment.sku_id":
            kind, rule = "derived_from_scraped", "引用public_seed.source_item_id；所属门店与事件仍为模拟"
        lineage.append({"field": field, "value": value, "kind": kind, "kind_label": KINDS[kind],
                        "basis": rule, "source_url": source_manifest["source_url"],
                        "source_item_row": selected["source_item_row"],
                        "source_receipt_row": selected["source_receipt_row"], "rule_version": RULES["version"]})
    manifest = {key: source_manifest[key] for key in ("source_url", "doi", "license", "attribution", "license_url", "limitations")}
    manifest.update(version=VERSION, source_files=checks,
                    source_row_reference={key: selected[key] for key in ("source_item_row", "source_receipt_row")},
                    reused_scrapling_acquisition=True, new_scraping_performed=False,
                    source_record_count_in_pilot=1, external_increment_count=1,
                    sample_contiguous=False, demand_intensity_calibrated=False,
                    production_schema_status="课堂临时切片；正式增量规范与批量扩展待后续安排",
                    rules=RULES,
                    ai_input_boundary="只向AI提供本目录输入；验收答案和运行投影另存")
    inputs = output / INPUT_DIR
    save(inputs / "01_真实选定记录.json", observed)
    save(inputs / "02_真实字段派生.json", derived)
    save(inputs / "03_课堂基础快照.json", base)
    save(inputs / "04_字段来源.json", lineage)
    save(inputs / "06_缺制作时间副本覆写.json", missing_overlay)
    save(inputs / "来源与规则.json", manifest)
    (inputs / "05_唯一延期事件.jsonl").write_text(canonical(event) + "\n", encoding="utf-8")
    shutil.copy2(source / "新版人工核对记录.json", output / "历史人工核对_沿用原记录.json")
    return manifest


def run_inputs(inputs):
    base = load(inputs / "03_课堂基础快照.json")
    observed = load(inputs / "01_真实选定记录.json")
    derived = load(inputs / "02_真实字段派生.json")
    missing_overlay = load(inputs / "06_缺制作时间副本覆写.json")
    if missing_overlay != {"prep_minutes": None}:
        raise DataContractError("缺规则副本只能删除prep_minutes")
    lineage = load(inputs / "04_字段来源.json")
    events = [json.loads(line) for line in (inputs / "05_唯一延期事件.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if len(events) != 1:
        raise DataContractError("当前切片必须且只能包含1条延期事件")
    field_values = dict(leaves({"public_seed": observed, "derived": derived,
                               "scenario": base, "increment": events[0], "missing_overlay": missing_overlay}))
    fields = set(field_values)
    listed = [row["field"] for row in lineage]
    if fields != set(listed) or len(listed) != len(set(listed)):
        raise DataContractError("字段来源存在缺口或重复")
    if any(row["kind"] not in KINDS for row in lineage):
        raise DataContractError("未知字段来源类型")
    if any(canonical(row["value"]) != canonical(field_values[row["field"]]) for row in lineage):
        raise DataContractError("字段来源表的值与输入文件不一致")
    frozen = digest(base)
    ledger = EventLedger(base)
    applied = ledger.apply(events[0])
    delayed = copy.deepcopy(ledger.snapshot)
    before_duplicate = digest(ledger.snapshot)
    duplicate = ledger.apply(events[0])
    if digest(ledger.snapshot) != before_duplicate:
        raise DataContractError("重复事件改变状态")
    missing = copy.deepcopy(delayed)
    missing.update(missing_overlay)
    cases = {"normal": base, "delay": delayed, "missing": missing}
    results = {key: {"projection": project(case), "adjustment_check": check_adjustment(case)} for key, case in cases.items()}
    results["normal"]["adjustment_check"] = {"not_requested": True, "reason": "已有计划及时覆盖，维持计划"}
    if digest(base) != frozen:
        raise DataContractError("推演修改了基础快照")
    expected = {
        "normal": {"late_units": 0, "backlog_end": 0, "remaining_available": 0, "served_by_horizon": 15, "delay_unit_minutes": 0},
        "delay": {"late_units": 1, "backlog_end": 0, "remaining_available": 0, "served_by_horizon": 15, "delay_unit_minutes": 2},
        "missing": {"late_units": 1, "backlog_end": 0, "remaining_available": 0, "served_by_horizon": 15, "delay_unit_minutes": 2},
    }
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    for key, target in expected.items():
        check(f"{key}：与人工可核算结果一致", all(results[key]["projection"][k] == v for k, v in target.items()), target)
        check(f"{key}：每个事件后数量守恒", results[key]["projection"]["conservation_pass"], "期初可分配+投影到货=投影履约+剩余+截止排除")
    check("缺规则保留风险并阻断调整", results["missing"]["adjustment_check"]["quantity"] is None
          and not results["missing"]["adjustment_check"]["action_adoptable"], "缺prep_minutes；可采纳数量为空")
    check("调整原待办满足情景条件", results["delay"]["adjustment_check"]["projection"]["late_units"] == 0,
          "仅检验预设第8分钟完成方案；须人工确认，未登记实际完成")
    check("唯一事件重复导入无副作用", duplicate["status"] == "duplicate_ignored" and ledger.version == 1,
          "忽略同ID同内容；状态版本仍为1")
    check("基础库存未被投影或采纳改变", base["on_hand"] == delayed["on_hand"] == 12
          and base["reserved"] == delayed["reserved"] == 5, "在手12、预留5、可分配7；实际完成另记")
    check("字段来源逐项覆盖", len(fields) == len(lineage), {"leaf_fields": len(fields), "lineage_rows": len(lineage)})
    allowed_inputs = {"01_真实选定记录.json", "02_真实字段派生.json", "03_课堂基础快照.json",
                      "04_字段来源.json", "05_唯一延期事件.jsonl", "06_缺制作时间副本覆写.json", "来源与规则.json"}
    check("验收答案与智能体输入隔离", {path.name for path in inputs.iterdir()} == allowed_inputs,
          "输入目录只含7份业务输入与来源文件；验收答案另存")
    check("确定性复现", digest(project(delayed)) == digest(project(delayed)), "本轮不抽样；记录预留种子，不声称拟合真实分布")
    # An independent, previously verified implementation, used only for validation.
    # It is not imported or called by project() or by an AI input tool.
    from anomaly_tools import simulate
    comparison_fields = ("late_units", "first_late_minute", "backlog_end", "delay_unit_minutes",
                         "served_by_horizon", "remaining_available", "expired_unavailable")
    for key, case in cases.items():
        legacy = simulate(case)
        check(f"{key}：与既有课堂算法交叉核对", all(results[key]["projection"][k] == legacy[k] for k in comparison_fields),
              list(comparison_fields))
    if not all(row["passed"] for row in checks):
        raise DataContractError("小样例核验未全部通过")
    input_bundle = {"observed": observed, "derived": derived, "base": base, "event": events[0],
                    "missing_overlay": missing_overlay, "lineage": lineage,
                    "source_manifest": load(inputs / "来源与规则.json")}
    return {"version": VERSION, "rules": RULES, "input_sha256": digest(input_bundle),
            "input": {"observed": observed, "derived": derived, "base": base, "event": events[0],
                      "missing_overlay": missing_overlay, "lineage": lineage},
            "results": results, "checks": checks, "passed": True,
            "ingestion": {"first": applied, "second": duplicate, "events_applied": len(ledger.events)},
            "actual_inventory": {"on_hand": base["on_hand"], "reserved": base["reserved"], "available": 7},
            "actual_completion_recorded": False,
            "runtime": {"python": sys.version.split()[0], "simpy": importlib.metadata.version("simpy")}}


def write_report(output, report):
    reports = output / REPORT_DIR
    save(reports / "管线运行结果.json", report)
    save(reports / "验收答案_不得作为AI输入.json", {
        "normal_late_units": 0, "delay_late_units": 1, "missing_action_quantity": None,
        "adjusted_ready_minute": 8, "additional_quantity": 0,
        "warning": "验收夹具；不得混入供智能体查证的输入目录"})
    template = (ROOT / "data_pipeline_report.html").read_text(encoding="utf-8")
    payload = json.dumps(report, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    (output / "00_打开数据管线演示.html").write_text(template.replace("__PAYLOAD_JSON__", payload), encoding="utf-8")
    checks_md = "\n".join(f"- {'通过' if c['passed'] else '失败'}：{c['name']}" for c in report["checks"])
    (output / "运行核验.md").write_text(f"# 数据管线小样例运行核验\n\nSimPy {report['runtime']['simpy']}；输入摘要 `{report['input_sha256']}`。\n\n{checks_md}\n\n实际完成未登记；本次输出为供需投影，不代表实测经营成效。\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "replay"), nargs="?", default="build")
    parser.add_argument("--source-package", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--downloads", type=Path, default=DEFAULT_DOWNLOADS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--inputs", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.mode == "build":
        build_inputs(args.source_package, args.downloads, output)
    inputs = args.inputs or output / INPUT_DIR
    report = run_inputs(inputs)
    write_report(output, report)
    if args.mode == "build":
        for name in ("data_pipeline.py", "data_pipeline_report.html", "test_data_pipeline.py", "anomaly_tools.py", "数据管线说明.md"):
            shutil.copy2(ROOT / name, output / name)
        for source in (WORK / "skill_installation_manifest.json", RUNTIME):
            shutil.copy2(source, output / source.name)
        runtime = load(RUNTIME)
        dep = runtime["dependencies"][0]
        (output / "requirements.lock").write_text(f"simpy=={dep['version']} --hash=sha256:{dep['sha256']}\n", encoding="utf-8")
        save(output / "构建记录.json", {"built_at_utc": datetime.now(timezone.utc).isoformat(),
                                        "source_package": str(args.source_package), "new_external_events": 1,
                                        "new_sampled_orders": 0, "input_sha256": report["input_sha256"],
                                        "source_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    print(json.dumps({"output": str(output), "passed": report["passed"], "checks": len(report["checks"]),
                      "events_applied": report["ingestion"]["events_applied"], "input_sha256": report["input_sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
