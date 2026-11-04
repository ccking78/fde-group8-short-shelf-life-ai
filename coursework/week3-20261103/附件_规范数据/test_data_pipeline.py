"""Domain checks for event replay, time boundaries, and source separation."""
import copy
import unittest

from data_pipeline import DataContractError, EventLedger, check_adjustment, create_delay_event, digest, project


def fixture():
    return {
        "id": "PILOT-01", "display_sku": "迷你三明治 A", "source_item_id": "1023",
        "store_id": "SIM-01", "as_of_minute": 0, "window_minutes": 20,
        "on_hand": 12, "reserved": 5, "blocked": 0, "actual_discard_recorded": 0,
        "old_sellable_until": 28, "new_hold_minutes": 30, "prep_minutes": 4,
        "plan": {"id": "TASK-8", "quantity": 8, "ready_minute": 4, "status": "not_started",
                 "alternative_ready_minute": 8, "alternative_capacity": 8},
        "demand_due": [{"minute": m, "quantity": q} for m, q in ((5, 4), (10, 4), (15, 4), (20, 3))],
    }


class PilotTests(unittest.TestCase):
    def test_normal_plan_covers_all_fifteen_units(self):
        result = project(fixture())
        self.assertEqual((result["late_units"], result["served_by_horizon"], result["backlog_end"]), (0, 15, 0))

    def test_delayed_plan_misses_one_need_but_fulfills_it_later(self):
        ledger = EventLedger(fixture())
        ledger.apply(create_delay_event(fixture()))
        result = project(ledger.snapshot)
        self.assertEqual((result["first_late_minute"], result["late_units"], result["backlog_end"]), (10, 1, 0))
        self.assertEqual(result["delay_unit_minutes"], 2)
        self.assertTrue(all(step["conservation_pass"] for step in result["trace"]))

    def test_projection_does_not_change_stock_or_input(self):
        case = fixture()
        before = copy.deepcopy(case)
        project(case)
        check_adjustment(case)
        self.assertEqual(case, before)
        self.assertEqual((case["on_hand"], case["reserved"]), (12, 5))

    def test_known_eta_retains_risk_when_prep_rule_is_missing(self):
        case = fixture()
        case["plan"]["ready_minute"] = 12
        case["prep_minutes"] = None
        self.assertEqual(project(case)["late_units"], 1)
        self.assertIsNone(check_adjustment(case)["quantity"])
        self.assertFalse(check_adjustment(case)["action_adoptable"])

    def test_adjusting_existing_task_removes_lateness_without_extra_batch(self):
        case = fixture()
        case["plan"]["ready_minute"] = 12
        decision = check_adjustment(case)
        self.assertEqual(decision["additional_quantity"], 0)
        self.assertEqual(decision["projection"]["late_units"], 0)
        self.assertTrue(decision["requires_human_confirmation"])

    def test_same_event_is_idempotent(self):
        ledger = EventLedger(fixture())
        event = create_delay_event(fixture())
        ledger.apply(event)
        before = copy.deepcopy(ledger.snapshot)
        self.assertEqual(ledger.apply(event)["status"], "duplicate_ignored")
        self.assertEqual(ledger.snapshot, before)
        self.assertEqual((ledger.version, len(ledger.events)), (1, 1))

    def test_same_id_with_different_payload_is_rejected(self):
        ledger = EventLedger(fixture())
        event = create_delay_event(fixture())
        ledger.apply(event)
        event["payload"]["after"] = 13
        before = copy.deepcopy(ledger.snapshot)
        with self.assertRaisesRegex(DataContractError, "相同事件编号"):
            ledger.apply(event)
        self.assertEqual(ledger.snapshot, before)

    def test_stale_version_is_rejected_without_mutation(self):
        ledger = EventLedger(fixture())
        event = create_delay_event(fixture())
        event["previous_version"] = 1
        before = copy.deepcopy(ledger.snapshot)
        with self.assertRaisesRegex(DataContractError, "版本冲突"):
            ledger.apply(event)
        self.assertEqual((ledger.snapshot, ledger.version, ledger.events), (before, 0, []))

    def test_wrong_sku_reference_is_rejected(self):
        ledger = EventLedger(fixture())
        event = create_delay_event(fixture())
        event["sku_id"] = "OTHER"
        with self.assertRaisesRegex(DataContractError, "引用不匹配"):
            ledger.apply(event)

    def test_before_value_must_match_snapshot(self):
        ledger = EventLedger(fixture())
        event = create_delay_event(fixture())
        event["payload"]["before"] = 3
        with self.assertRaisesRegex(DataContractError, "修改前值"):
            ledger.apply(event)

    def test_eta_before_current_time_is_rejected_atomically(self):
        ledger = EventLedger(fixture())
        event = create_delay_event(fixture())
        event["payload"]["after"] = 0
        with self.assertRaises(DataContractError):
            ledger.apply(event)
        self.assertEqual(ledger.version, 0)

    def test_numeric_bool_is_rejected(self):
        case = fixture()
        case["on_hand"] = True
        with self.assertRaises(DataContractError):
            project(case)

    def test_reservation_cannot_exceed_stock(self):
        case = fixture()
        case["reserved"] = 13
        with self.assertRaises(DataContractError):
            project(case)

    def test_supply_and_demand_at_horizon_are_included(self):
        case = fixture()
        case.update(on_hand=0, reserved=0)
        case["plan"].update(quantity=1, ready_minute=20)
        case["demand_due"] = [{"minute": 20, "quantity": 1}]
        result = project(case)
        self.assertEqual((result["served_by_horizon"], result["late_units"]), (1, 0))
        self.assertEqual(result["trace"][-1]["minute"], 20)

    def test_expiry_at_need_time_excludes_supply_first(self):
        case = fixture()
        case.update(on_hand=1, reserved=0, old_sellable_until=5)
        case["plan"]["quantity"] = 0
        case["demand_due"] = [{"minute": 5, "quantity": 1}]
        result = project(case)
        self.assertEqual((result["expired_unavailable"], result["late_units"], result["backlog_end"]), (1, 1, 1))
        self.assertTrue(result["conservation_pass"])

    def test_deterministic_replay_has_identical_digest(self):
        self.assertEqual(digest(project(fixture())), digest(project(fixture())))

    def test_capacity_blocks_infeasible_adjustment(self):
        case = fixture()
        case["plan"]["alternative_capacity"] = 7
        self.assertFalse(check_adjustment(case)["action_adoptable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
