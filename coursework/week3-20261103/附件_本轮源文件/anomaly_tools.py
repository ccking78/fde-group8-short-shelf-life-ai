"""Read-only, logged tools for the classroom anomaly investigation.

Late units mean unable to cover a simulated need-by time, not lost sales.
Backlog is served later when supply arrives. Expiry is not recorded discard.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103")
DATA = OUT / "附件_数据与来源" / "04_模拟情景.json"
VERSION = "anomaly-tools-2.0"


def validate(case):
    missing = []
    for key in ["on_hand", "reserved", "blocked", "old_sellable_until", "new_hold_minutes", "prep_minutes"]:
        if case.get(key) is None:
            missing.append(key)
    if case["plan"]["quantity"] and case["plan"].get("ready_minute") is None:
        missing.append("plan.ready_minute")
    invalid = []
    if case["on_hand"] < case["reserved"] + case["blocked"]:
        invalid.append("allocation_exceeds_on_hand")
    for key in ["on_hand", "reserved", "blocked"]:
        if case.get(key) is not None and (case[key] < 0 or int(case[key]) != case[key]):
            invalid.append(key)
    return missing, invalid


def simulate(case, quantity=None, ready=None):
    missing, invalid = validate(case)
    # A missing preparation rule blocks a new action. It does not erase an
    # independently known task ETA used only to observe the existing plan.
    observation_only = quantity is None and ready is None
    blocking = [k for k in missing if not (observation_only and k == "prep_minutes")]
    if blocking or invalid:
        return {"status": "blocked", "quantity": None, "missing": missing, "invalid": invalid}
    q = case["plan"]["quantity"] if quantity is None else quantity
    r = case["plan"]["ready_minute"] if ready is None else ready
    if q < 0 or int(q) != q or (q and (r is None or (case["prep_minutes"] is not None and r < case["prep_minutes"]))):
        return {"status": "invalid", "quantity": None, "reason": "数量或完成时间不满足模拟制作条件"}
    available = case["on_hand"] - case["reserved"] - case["blocked"]
    batches = [{"id": "existing", "quantity": available, "deadline": case["old_sellable_until"]}]
    events = []
    if q:
        events.append((r, 1, "supply", q))
    events.append((case["old_sellable_until"], 0, "expiry", "existing"))
    if q:
        events.append((r + case["new_hold_minutes"], 0, "expiry", "planned"))
    for d in case["demand_due"]:
        events.append((d["minute"], 2, "demand", d["quantity"]))
    backlog = []
    late_units = 0
    served = 0
    delay_unit_minutes = 0
    excluded = 0
    steps = []
    first_late = None

    def fulfill(wanted, now):
        nonlocal served
        remaining = wanted
        for batch in sorted(batches, key=lambda x: x["deadline"]):
            if batch["deadline"] <= now:
                continue
            take = min(remaining, batch["quantity"])
            batch["quantity"] -= take
            remaining -= take
            served += take
        return remaining

    horizon = case["window_minutes"]
    for t, _, kind, amount in sorted(events):
        if t > horizon:
            continue
        if kind == "expiry":
            for b in batches:
                if b["id"] == amount:
                    excluded += b["quantity"]
                    b["quantity"] = 0
        if kind == "supply":
            batches.append({"id": "planned", "quantity": amount, "deadline": t + case["new_hold_minutes"]})
            for b in backlog:
                before = b["quantity"]
                b["quantity"] = fulfill(before, t)
                delay_unit_minutes += (before - b["quantity"]) * (t - b["due"])
            backlog = [b for b in backlog if b["quantity"]]
        if kind == "demand":
            left = fulfill(amount, t)
            if left:
                late_units += left
                if first_late is None:
                    first_late = t
                backlog.append({"quantity": left, "due": t})
        steps.append({"minute": t, "event": kind, "quantity": amount,
                      "available_after": sum(b["quantity"] for b in batches if b["deadline"] > t),
                      "backlog_after": sum(b["quantity"] for b in backlog)})
    for b in backlog:
        delay_unit_minutes += b["quantity"] * (horizon - b["due"])
    return {"status": "observed_with_missing_rule" if missing else "simulated", "quantity": q, "ready_minute": r if q else None,
            "missing_action_rules": missing, "action_adoptable": not bool(missing),
            "forecast_quantity": sum(x["quantity"] for x in case["demand_due"]), "available_initial": available,
            "late_units": late_units, "first_late_minute": first_late, "backlog_end": sum(b["quantity"] for b in backlog),
            "delay_unit_minutes": delay_unit_minutes, "served_by_horizon": served,
            "remaining_available": sum(b["quantity"] for b in batches if b["deadline"] > horizon),
            "expired_unavailable": excluded, "actual_discard_recorded": case["actual_discard_recorded"],
            "steps": steps, "caution": "全部为模拟供需与时点；late_units不等于损失销量；截止排除不等于实际报废"}


def inspect(case):
    missing, invalid = validate(case)
    return {"case": case["id"], "snapshot_version": case["snapshot_version"],
            "status": "needs_verification" if missing or invalid else "ready",
            "on_hand": case["on_hand"], "reserved": case["reserved"], "blocked": case["blocked"],
            "available": case["on_hand"] - case["reserved"] - case["blocked"],
            "demand_due": case["demand_due"], "missing": missing, "invalid": invalid,
            "existing_task_id": case["plan"]["id"], "existing_task_quantity": case["plan"]["quantity"],
            "need_to_read": ["task_schedule", "batch_rules", "source_lineage"], "origin": case["origins"]}


def evidence(case, topic):
    if topic == "task_schedule":
        return {"topic": topic, "task": case["plan"], "prep_minutes": case["prep_minutes"],
                "source": "课堂模拟TASK-8", "verification_role": "制作岗位核实际进度与可调整产能；店长核制作规则",
                "warning": "备选完成时点只是预设可行条件，采纳前必须由人员核实"}
    if topic == "batch_rules":
        return {"topic": topic, "old_sellable_until": case["old_sellable_until"],
                "new_hold_minutes": case["new_hold_minutes"], "actual_discard_recorded": case["actual_discard_recorded"],
                "source": "模拟规则sim-rule-2，不是来源门店规则或通用安全标准"}
    return {"topic": "source_lineage", "source_url": case["source_url"], "source_item_id": case["source_item_id"],
            "source_item_name": case["source_item_name"], "seed_source_item_row": case["seed_source_item_row"],
            "limitations": case["limitations"], "history_quantities": case["history_quantities"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", choices=["inspect", "evidence", "simulate"])
    parser.add_argument("--case", required=True)
    parser.add_argument("--topic", choices=["task_schedule", "batch_rules", "source_lineage"])
    parser.add_argument("--quantity", type=int)
    parser.add_argument("--ready", type=int)
    parser.add_argument("--run", default="current_ai_review")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    cases = json.loads(DATA.read_text(encoding="utf-8"))
    case = next(x for x in cases if x["id"] == args.case)
    if args.tool == "inspect":
        output = inspect(case)
    elif args.tool == "evidence":
        output = evidence(case, args.topic)
    else:
        output = simulate(case, args.quantity, args.ready)
    folder = OUT / "附件_AI查证记录" / args.run
    folder.mkdir(parents=True, exist_ok=True)
    frozen = folder / "input_snapshot.json"
    if not frozen.exists():
        frozen.write_bytes(DATA.read_bytes())
    log = folder / "tool_trace.jsonl"
    seq = len(log.read_text(encoding="utf-8").splitlines()) + 1 if log.exists() else 1
    event = {"call_id": f"{args.run}-T{seq:02d}", "at_utc": datetime.now(timezone.utc).isoformat(),
             "actor": "当前对话AI助手选择并调用本地工具", "case": args.case, "tool": args.tool,
             "version": VERSION, "input_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest(),
             "arguments": {"topic": args.topic, "quantity": args.quantity, "ready": args.ready}, "output": output}
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    display = event
    if args.compact:
        display = dict(event)
        display["output"] = {k: v for k, v in output.items() if k not in ("steps", "origin", "limitations")}
    print(json.dumps(display, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
