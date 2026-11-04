"""Bounded real-model acceptance. Actions are by a test operator, not the user."""
import argparse
import json
from pathlib import Path

from domain import Store, apply_delay, complete, decision, now
from runtime import Agent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--work", type=Path, required=True)
    args = p.parse_args()
    store = Store(args.work / "ledger.sqlite3")
    agent = Agent(store, args.work / "runs")
    s = store.create()
    sid = s["session_id"]
    store.mutate(sid, "delay-1", {"expected_version": 0}, lambda s, db: apply_delay(s))
    print(json.dumps({"step": "delay_started", "session_id": sid}), flush=True)
    r = agent.start(sid, "eta_changed", async_run=False)
    print(json.dumps({"step": "delay_model", "status": r["status"], "error": r["error"], "recommendation": r["recommendation"]}, ensure_ascii=False), flush=True)
    assert r["status"] == "completed" and r["recommendation"]["status"] == "adjust_existing", "真实延期调查未通过"
    rec = r["recommendation"]
    assert (rec["quantity"], rec["ready_minute"], rec["additional_quantity"]) == (8, 8, 0)
    review = {"expected_version": 1, "run_id": r["id"], "role": "制作岗位", "actor": "自动验收测试操作者",
              "site_verified": True, "decision": "adopt", "quantity": rec["quantity"], "ready_minute": rec["ready_minute"],
              "note": "课堂自动验收：按预设条件核对并测试采纳，不代表用户新确认或真实现场核实"}
    store.mutate(sid, "adopt-1", review, lambda s, db: decision(s, db, review))
    assert store.state(sid)["on_hand"] == 12
    execute = {"expected_version": 2, "role": "制作岗位", "actor": "自动验收测试操作者", "classroom_acknowledged": True,
               "quantity": 8, "completed_minute": 8, "fulfilled_quantity": 4}
    store.mutate(sid, "complete-1", execute, lambda s, db: complete(s, execute))
    duplicate = store.mutate(sid, "complete-1", execute, lambda s, db: complete(s, execute))
    assert duplicate["duplicate_ignored"] and store.state(sid)["on_hand"] == 16
    print(json.dumps({"step": "completion_started", "on_hand": 16, "available": 11, "version": 3}), flush=True)
    r2 = agent.start(sid, "completion_recorded", async_run=False)
    print(json.dumps({"step": "completion_model", "status": r2["status"], "error": r2["error"], "recommendation": r2["recommendation"]}, ensure_ascii=False), flush=True)
    assert r2["status"] == "completed" and r2["recommendation"]["status"] == "observe", "实际登记后的真实复评未通过"
    report = {"verified_at_utc": now(), "live_model": True, "session_id": sid, "state": store.state(sid),
              "runs": store.runs(sid), "assertions": {"model_selected_tools": True, "live_recommendation": True,
              "adoption_did_not_add_inventory": True, "duplicate_completion_did_not_add_inventory": True,
              "completed_batch_not_projected_twice": True, "new_fact_triggered_new_model_assessment": True},
              "warning": "两次真实模型运行；人审与完成为自动验收测试操作者的课堂动作，不冒充用户或企业执行"}
    (args.work / "live_acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"step": "passed", "session_id": sid, "live_runs": 2}), flush=True)


if __name__ == "__main__":
    main()
