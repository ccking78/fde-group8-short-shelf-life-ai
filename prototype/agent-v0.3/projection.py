"""Bounded classroom projection, adapted from the existing data_pipeline.py.

Counts and event ordering are deterministic. SimPy schedules at most 256 steps.
No projection writes inventory, and forecast demand is never an actual order.
"""
from __future__ import annotations

import copy
import simpy


class ContractError(ValueError):
    pass


def integer(value, field, low=0, high=10000):
    if type(value) is not int or not low <= value <= high:
        raise ContractError(f"{field}须为{low}至{high}的整数")
    return value


def validate(s):
    for k in ("on_hand", "reserved", "blocked", "actual_discard_recorded"):
        integer(s.get(k), k)
    if s["on_hand"] < s["reserved"] + s["blocked"]:
        raise ContractError("预留与不可分配量超过在手")
    for k in ("as_of_minute", "window_minutes", "old_sellable_until", "new_hold_minutes"):
        integer(s.get(k), k, high=1440)
    if s["as_of_minute"] > s["window_minutes"]:
        raise ContractError("当前时点超过观察窗口")
    if s.get("prep_minutes") is not None:
        integer(s["prep_minutes"], "prep_minutes", 1, 1440)
    p = s["plan"]
    if p["id"] != "TASK-8" or p["status"] not in ("not_started", "accepted", "completed", "partial"):
        raise ContractError("任务状态或编号不属于本切片")
    integer(p["quantity"], "plan.quantity", high=8)
    if p.get("ready_minute") is not None:
        integer(p["ready_minute"], "plan.ready_minute", s["as_of_minute"], 1440)
    if len(s["demand_due"]) > 8:
        raise ContractError("模拟需用时点超限")
    for d in s["demand_due"]:
        integer(d["minute"], "demand.minute", s["as_of_minute"], s["window_minutes"])
        integer(d["quantity"], "demand.quantity", 1)
    for b in s.get("actual_batches", []):
        integer(b["quantity"], "actual_batch.quantity")
        integer(b["deadline"], "actual_batch.deadline", s["as_of_minute"] + 1, 1440)
    if sum(b["quantity"] for b in s.get("actual_batches", [])) > s["on_hand"] - s["reserved"] - s["blocked"]:
        raise ContractError("批次数量超过可分配账面量")


def project(s):
    validate(s)
    if s["plan"]["quantity"] and s["plan"]["ready_minute"] is None:
        return {"status": "blocked", "reason": "剩余任务完成时间未知", "quantity": None}
    if simpy.__version__ != "4.1.2":
        raise ContractError("本切片固定使用SimPy 4.1.2")
    initial = s["on_hand"] - s["reserved"] - s["blocked"]
    batches = copy.deepcopy(s.get("actual_batches", []))
    batches.append({"id": "old", "quantity": initial - sum(b["quantity"] for b in batches),
                    "deadline": s["old_sellable_until"]})
    events = [(b["deadline"], 0, "expiry", b["id"]) for b in batches]
    q, ready = s["plan"]["quantity"], s["plan"]["ready_minute"]
    if q:
        events += [(ready, 1, "projected_supply", q), (ready + s["new_hold_minutes"], 0, "expiry", "planned")]
    events += [(d["minute"], 2, "simulated_need_due", d["quantity"]) for d in s["demand_due"]]
    if len(events) > 32:
        raise ContractError("业务事件数超限")
    backlog, trace = [], []
    served = supplied = excluded = late = delay = 0
    first_late = None

    def take(wanted, now):
        nonlocal served
        left = wanted
        for b in sorted(batches, key=lambda b: b["deadline"]):
            if b["deadline"] > now:
                n = min(left, b["quantity"])
                b["quantity"] -= n
                left -= n
                served += n
        return left

    def process():
        nonlocal late, supplied, excluded, delay, first_late, backlog
        for minute, _, kind, amount in sorted(events):
            if minute < s["as_of_minute"]:
                continue
            yield env.timeout(minute - env.now)
            if kind == "expiry":
                for b in batches:
                    if b["id"] == amount:
                        excluded += b["quantity"]
                        b["quantity"] = 0
            elif kind == "projected_supply":
                supplied += amount
                batches.append({"id": "planned", "quantity": amount, "deadline": minute + s["new_hold_minutes"]})
                for b in backlog:
                    before = b["quantity"]
                    b["quantity"] = take(before, minute)
                    delay += (before - b["quantity"]) * (minute - b["due"])
                backlog = [b for b in backlog if b["quantity"]]
            else:
                left = take(amount, minute)
                if left:
                    late += left
                    first_late = minute if first_late is None else first_late
                    backlog.append({"quantity": left, "due": minute})
            remaining = sum(b["quantity"] for b in batches if b["deadline"] > minute)
            if initial + supplied != served + remaining + excluded:
                raise ContractError("模拟数量守恒校验失败")
            trace.append({"minute": minute, "event": kind, "quantity": amount,
                          "projected_available": remaining, "projected_backlog": sum(b["quantity"] for b in backlog)})

    env = simpy.Environment(initial_time=s["as_of_minute"])
    env.process(process())
    steps = 0
    while env.peek() <= s["window_minutes"]:
        if steps >= 256:
            raise ContractError("SimPy调度步数超限")
        env.step()
        steps += 1
    delay += sum(b["quantity"] * (s["window_minutes"] - b["due"]) for b in backlog)
    return {"status": "projected", "kind": "classroom_hypothetical", "engine": "SimPy 4.1.2",
            "available_initial": initial, "forecast_quantity": sum(d["quantity"] for d in s["demand_due"]),
            "quantity": q, "ready_minute": ready if q else None, "late_units": late,
            "first_late_minute": first_late, "backlog_end": sum(b["quantity"] for b in backlog),
            "delay_unit_minutes": delay, "served_by_horizon": served,
            "remaining_available": sum(b["quantity"] for b in batches if b["deadline"] > s["window_minutes"]),
            "expired_unavailable": excluded, "conservation_pass": True, "trace": trace,
            "meaning": "模拟需用时点未覆盖量，不等于真实丢单、报废或企业收益"}


def compare(s, quantity=None, ready=None):
    baseline = project(s)
    result = {"baseline": baseline, "candidate": None, "action_adoptable": False,
              "unreconciled_past_quantity": s.get("unreconciled_past_quantity", 0)}
    if quantity is None and ready is None:
        return result
    integer(quantity, "candidate.quantity", 1, 8)
    integer(ready, "candidate.ready_minute", 1, 20)
    missing = ["prep_minutes"] if s.get("prep_minutes") is None else []
    if missing:
        return dict(result, missing=missing, quantity=None)
    p = s["plan"]
    if p["status"] != "not_started" or s.get("unreconciled_past_quantity", 0):
        return dict(result, reason="现有任务状态或未核对履约不允许新的调整", quantity=None)
    if quantity > p["alternative_capacity"] or ready < max(s["as_of_minute"] + s["prep_minutes"], p["alternative_ready_minute"]):
        return dict(result, reason="数量、制作时长或模拟产能条件不满足", quantity=None)
    candidate = copy.deepcopy(s)
    candidate["plan"].update(quantity=quantity, ready_minute=ready)
    result.update(candidate=project(candidate), action_adoptable=True, quantity=quantity,
                  ready_minute=ready, additional_quantity=0, requires_human_confirmation=True,
                  note="仅为模拟可行候选；制作岗位仍须核实现场进度、产能和规则")
    return result
