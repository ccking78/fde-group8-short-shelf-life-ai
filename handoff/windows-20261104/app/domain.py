"""Single-user classroom ledger, atomic writes and optimistic version checks."""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from projection import ContractError, compare, integer, validate

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def read_inputs():
    index = json.loads((ROOT / "inputs" / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in index["files"].items():
        if hashlib.sha256((ROOT / "inputs" / name).read_bytes()).hexdigest() != expected:
            raise ContractError(f"输入哈希不符：{name}")
    base = json.loads((ROOT / "inputs" / "03_课堂基础快照.json").read_text(encoding="utf-8"))
    meta = json.loads((ROOT / "inputs" / "来源许可与版本.json").read_text(encoding="utf-8"))
    event = json.loads((ROOT / "inputs" / "05_唯一延期事件_CloudEvents.jsonl").read_text(encoding="utf-8"))
    validate(base["state"])
    return base, meta, event


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path, self.lock = str(path), threading.RLock()
        with self.db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, state TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS requests(session_id TEXT, key TEXT, fingerprint TEXT, result TEXT,
                 PRIMARY KEY(session_id,key));
              CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, session_id TEXT, version INTEGER, record TEXT);
            """)
            for row in db.execute("SELECT id,record FROM runs").fetchall():
                r = json.loads(row[1])
                if r["status"] in ("queued", "running"):
                    r.update(status="unavailable", error="服务重启中断了模型调查，可重新调查", finished_at_utc=now())
                    db.execute("UPDATE runs SET record=? WHERE id=?", (canonical(r), row[0]))

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def create(self, variant="normal"):
        if variant not in ("normal", "missing"):
            raise ContractError("情景仅支持normal或missing")
        base, _, _ = read_inputs()
        s = copy.deepcopy(base["state"])
        if variant == "missing":
            s["prep_minutes"] = None
        s.update(session_id=uuid.uuid4().hex, version=0, variant=variant, actual_batches=[],
                 execution=[], human_reviews=[], events=[], unreconciled_past_quantity=0)
        with self.lock, self.db() as db:
            db.execute("INSERT INTO sessions VALUES (?,?)", (s["session_id"], canonical(s)))
        return s

    @staticmethod
    def _state(db, session_id):
        row = db.execute("SELECT state FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise ContractError("未找到课堂会话")
        return json.loads(row[0])

    def state(self, session_id):
        with self.lock, self.db() as db:
            return self._state(db, session_id)

    def runs(self, session_id):
        with self.lock, self.db() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT record FROM runs WHERE session_id=? ORDER BY rowid", (session_id,))]

    def save_run(self, r):
        with self.lock, self.db() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                       (r["id"], r["session_id"], r["snapshot_version"], canonical(r)))

    def mutate(self, sid, key, payload, change):
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise ContractError("缺少有效的幂等请求编号")
        fp = digest(payload)
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT fingerprint,result FROM requests WHERE session_id=? AND key=?", (sid, key)).fetchone()
            if old:
                if old[0] != fp:
                    raise ContractError("相同请求编号对应不同内容")
                return dict(json.loads(old[1]), duplicate_ignored=True)
            s = self._state(db, sid)
            if payload.get("expected_version") != s["version"] or type(payload.get("expected_version")) is not int:
                raise ContractError("快照版本已变化，请刷新后核对")
            change(s, db)
            s["version"] += 1
            validate(s)
            result = {"state": s, "duplicate_ignored": False}
            db.execute("UPDATE sessions SET state=? WHERE id=?", (canonical(s), sid))
            db.execute("INSERT INTO requests VALUES (?,?,?,?)", (sid, key, fp, canonical(result)))
            return result


def apply_delay(s):
    _, _, event = read_inputs()
    d = event["data"]
    if s["version"] != d["previous_version"] or s["plan"]["ready_minute"] != d["before"]:
        raise ContractError("唯一延期事件的版本或前值不符")
    if s["events"]:
        raise ContractError("本切片仅接收既有的一条外部延期事件")
    if (event["specversion"] != "1.0" or d["task_id"] != s["plan"]["id"]
            or d["store_id"] != s["store_id"] or d["sku_id"] != s["source_item_id"]):
        raise ContractError("延期事件引用不符")
    s["plan"]["ready_minute"] = d["after"]
    s["as_of_minute"] = d["recorded_minute"]
    s["events"].append(dict(event, recorded_at_utc=now()))


def decision(s, db, p):
    if p.get("role") != "制作岗位" or not isinstance(p.get("actor"), str) or not p["actor"].strip() or len(p["actor"]) > 60:
        raise ContractError("请填写操作者，并选择制作岗位")
    row = db.execute("SELECT record FROM runs WHERE id=? AND session_id=?", (p.get("run_id"), s["session_id"])).fetchone()
    if not row:
        raise ContractError("未找到当前AI调查")
    r = json.loads(row[0])
    if r["status"] != "completed" or r["snapshot_version"] != s["version"]:
        raise ContractError("AI调查未完成或已过期")
    rec = r["recommendation"]
    mode = p.get("decision")
    if mode not in ("adopt", "modify", "ignore"):
        raise ContractError("只允许采纳、改量或忽略")
    if mode != "ignore" and p.get("site_verified") is not True:
        raise ContractError("请先核对现场进度、规则、产能、数量与时间")
    if not isinstance(p.get("note"), str) or len(p["note"].strip()) < 2 or len(p["note"]) > 500:
        raise ContractError("请填写本次核对结果或处理理由")
    check = None
    if mode != "ignore":
        if rec["status"] != "adjust_existing":
            raise ContractError("本次AI没有可采纳调整；先核实缺失项")
        q, ready = p.get("quantity"), p.get("ready_minute")
        if mode == "adopt" and (q, ready) != (rec["quantity"], rec["ready_minute"]):
            raise ContractError("采纳数量与AI建议不符，修改请用改量操作")
        check = compare(s, q, ready)
        if not check["action_adoptable"]:
            raise ContractError("当前调整未通过规则检查")
        if mode == "modify" and (p.get("preview_sha256") != digest(check) or p.get("risk_acknowledged") is not True):
            raise ContractError("改量须先查看当前版本的重新校验结果，并确认影响")
        s["plan"].update(quantity=q, ready_minute=ready, status="accepted")
    s["human_reviews"].append({"at_utc": now(), "actor": p["actor"], "role": p["role"],
        "origin": "classroom_operator_record", "decision": mode, "note": p["note"], "site_verified": p.get("site_verified") is True,
        "reviewed_version": s["version"], "run_id": r["id"], "quantity": p.get("quantity") if check else None,
        "ready_minute": p.get("ready_minute") if check else None, "revalidation": check})


def complete(s, p):
    if p.get("role") != "制作岗位" or not isinstance(p.get("actor"), str) or not p["actor"].strip() or len(p["actor"]) > 60:
        raise ContractError("完成登记须填写制作岗位操作者")
    if s["plan"]["status"] != "accepted":
        raise ContractError("只能登记已确认任务，已完成或少完成不能重复入库")
    if s["prep_minutes"] is None:
        raise ContractError("缺制作规则，不能登记本切片的完成")
    if p.get("classroom_acknowledged") is not True:
        raise ContractError("请确认这是课堂模拟执行登记")
    q = integer(p.get("quantity"), "实际完成数量", 1, s["plan"]["quantity"])
    t = integer(p.get("completed_minute"), "实际完成时点", 5, 9)
    if t < s["as_of_minute"] + s["prep_minutes"]:
        raise ContractError("完成时点早于模拟制作条件")
    fulfilled = p.get("fulfilled_quantity")
    if fulfilled is not None:
        integer(fulfilled, "累计已履约量", 0, s["on_hand"] - s["reserved"] - s["blocked"])
    past = sum(d["quantity"] for d in s["demand_due"] if d["minute"] <= t)
    s["unreconciled_past_quantity"] = past if fulfilled is None else 0
    before = s["on_hand"]
    s["on_hand"] += q - (fulfilled or 0)
    s["actual_batches"].append({"id": "BATCH-TASK-8", "quantity": q, "deadline": t + s["new_hold_minutes"]})
    s["demand_due"] = [d for d in s["demand_due"] if d["minute"] > t]
    s["as_of_minute"] = t
    remaining = s["plan"]["quantity"] - q
    s["plan"].update(quantity=remaining, status="completed" if not remaining else "partial", ready_minute=None)
    s["execution"].append({"type": "classroom_completion_and_reconciliation", "at_utc": now(),
        "actor": p["actor"], "role": p["role"], "origin": "classroom_operator_record",
        "task_id": "TASK-8", "completed_quantity": q, "completed_minute": t,
        "cumulative_unreserved_fulfilled": fulfilled, "past_forecast_quantity": past,
        "on_hand_before": before, "on_hand_after": s["on_hand"], "remaining_task_quantity": remaining,
        "note": "课堂模拟登记，不是用户新确认或真实企业执行；未知履约不自动扣账"})
