"""Specific ledger and forecast risks introduced by the runtime loop."""
import copy
import tempfile
import unittest
import os
from pathlib import Path

from domain import Store, apply_delay, complete, decision, now
from projection import ContractError, compare, project
from runtime import Agent, ModelError, validate_recommendation


class Unavailable:
    def decide(self, context):
        raise ModelError("测试模型不可用")


class Boundaries(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("FDE_TEST_WORK", str(Path(tempfile.gettempdir()) / "FDEGroup8-tests")))
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.store = Store(Path(self.tmp.name) / "test.sqlite3")
        self.s = self.store.create()
        self.sid = self.s["session_id"]

    def tearDown(self):
        self.tmp.cleanup()

    def delayed(self):
        return self.store.mutate(self.sid, "eta", {"expected_version": 0}, lambda s, db: apply_delay(s))["state"]

    def accepted(self, q=8):
        s = self.delayed()
        s["plan"].update(quantity=q, ready_minute=8, status="accepted")
        s["version"] = 2
        return s

    def test_normal_and_delay_time_axis_includes_horizon(self):
        r = project(self.s)
        self.assertEqual((r["late_units"], r["served_by_horizon"]), (0, 15))
        d = project(self.delayed())
        self.assertEqual((d["late_units"], d["first_late_minute"], d["backlog_end"], d["delay_unit_minutes"]), (1, 10, 0, 2))

    def test_missing_rule_keeps_observation_but_blocks_action(self):
        s = self.delayed()
        s["prep_minutes"] = None
        r = compare(s, 8, 8)
        self.assertEqual(r["baseline"]["late_units"], 1)
        self.assertFalse(r["action_adoptable"])
        self.assertIsNone(r["quantity"])
        missing = self.store.create("missing")
        sid = missing["session_id"]
        self.store.mutate(sid, "delay", {"expected_version": 0}, lambda s, db: apply_delay(s))
        self.store.save_run({"id": "test-missing", "session_id": sid, "snapshot_version": 1, "status": "completed",
                             "recommendation": {"status": "needs_verification", "quantity": None, "ready_minute": None}})
        p = {"expected_version": 1, "actor": "测试操作者", "role": "制作岗位", "site_verified": False,
             "decision": "ignore", "run_id": "test-missing", "note": "已查看缺规则与风险，本轮仅测试记录忽略原因"}
        ignored = self.store.mutate(sid, "ignore", p, lambda s, db: decision(s, db, p))["state"]
        self.assertFalse(ignored["human_reviews"][-1]["site_verified"])
        self.assertEqual(ignored["on_hand"], 12)

    def test_model_quantity_bool_negative_and_excess_rejected(self):
        s = self.delayed()
        for q in (True, -1, 9, 8.0):
            with self.subTest(q=q), self.assertRaises(ContractError):
                compare(s, q, 8)

    def test_event_replay_ignored_conflict_and_stale_rejected(self):
        p = {"expected_version": 0}
        self.store.mutate(self.sid, "eta", p, lambda s, db: apply_delay(s))
        dup = self.store.mutate(self.sid, "eta", p, lambda s, db: self.fail("不能重复执行"))
        self.assertTrue(dup["duplicate_ignored"])
        with self.assertRaises(ContractError):
            self.store.mutate(self.sid, "eta", {"expected_version": 1}, lambda s, db: None)
        with self.assertRaises(ContractError):
            self.store.mutate(self.sid, "other", p, lambda s, db: None)

    def test_completion_conservation_no_double_projected_supply(self):
        s = self.accepted()
        complete(s, {"actor": "测试操作者", "role": "制作岗位", "classroom_acknowledged": True,
                     "quantity": 8, "completed_minute": 8, "fulfilled_quantity": 4})
        r = project(s)
        self.assertEqual((s["on_hand"], r["available_initial"], r["forecast_quantity"], r["served_by_horizon"]), (16, 11, 11, 11))
        self.assertEqual(r["quantity"], 0)
        self.assertEqual(s["actual_batches"][0]["deadline"], 38)
        with self.assertRaises(ContractError):
            complete(s, {"actor": "测试", "role": "制作岗位"})

    def test_unknown_fulfillment_and_partial_cannot_close_risk(self):
        s = self.accepted()
        complete(s, {"actor": "测试操作者", "role": "制作岗位", "classroom_acknowledged": True,
                     "quantity": 7, "completed_minute": 8, "fulfilled_quantity": None})
        self.assertEqual(s["unreconciled_past_quantity"], 4)
        self.assertEqual(s["plan"]["quantity"], 1)
        self.assertEqual(project(s)["status"], "blocked")
        self.assertEqual(s["on_hand"], 19)

    def test_latest_version_and_human_checks_required(self):
        s = self.delayed()
        run = {"id": "test-run", "session_id": self.sid, "snapshot_version": 1, "status": "completed",
               "recommendation": {"status": "adjust_existing", "quantity": 8, "ready_minute": 8}}
        self.store.save_run(run)
        p = {"expected_version": 1, "actor": "测试操作者", "role": "制作岗位", "site_verified": False,
             "decision": "adopt", "run_id": run["id"], "quantity": 8, "ready_minute": 8, "note": "测试核对"}
        with self.assertRaises(ContractError):
            self.store.mutate(self.sid, "bad-review", p, lambda s, db: decision(s, db, p))
        p["site_verified"] = True
        after = self.store.mutate(self.sid, "good-review", p, lambda s, db: decision(s, db, p))["state"]
        self.assertEqual(after["on_hand"], 12)
        self.assertEqual(after["plan"]["status"], "accepted")
        with self.assertRaises(ContractError):
            self.store.mutate(self.sid, "stale-review", p, lambda s, db: decision(s, db, p))

    def test_modify_requires_preview_and_impact_acknowledgment(self):
        self.delayed()
        self.store.save_run({"id": "test-modify", "session_id": self.sid, "snapshot_version": 1, "status": "completed",
                             "recommendation": {"status": "adjust_existing", "quantity": 8, "ready_minute": 8}})
        p = {"expected_version": 1, "actor": "测试操作者", "role": "制作岗位", "site_verified": True,
             "decision": "modify", "run_id": "test-modify", "quantity": 7, "ready_minute": 8, "note": "测试改量"}
        with self.assertRaises(ContractError):
            self.store.mutate(self.sid, "modify", p, lambda s, db: decision(s, db, p))

    def test_missing_or_fabricated_evidence_never_adoptable(self):
        s = self.delayed()
        rec = {"status": "adjust_existing", "quantity": 8, "ready_minute": 8, "additional_quantity": 0,
               "evidence_refs": ["fabricated"], "summary": "测试建议调整原待办", "explanation": "测试", "checks": ["规则", "产能"]}
        with self.assertRaises(ContractError):
            validate_recommendation(s, "eta_changed", rec, [])

    def test_model_unavailable_has_no_replay_or_mutation(self):
        agent = Agent(self.store, Path(self.tmp.name) / "runs", adapter=Unavailable())
        before = copy.deepcopy(self.store.state(self.sid))
        r = agent.start(self.sid, "manual_review", async_run=False)
        self.assertEqual(r["status"], "unavailable")
        self.assertIsNone(r["recommendation"])
        self.assertEqual(self.store.state(self.sid), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
