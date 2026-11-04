"""Checks concrete corruption and missing-input risks in the classroom contract."""
import copy
import unittest
from pathlib import Path

import data_completion as c
import data_pipeline as p


class CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent
        cls.inputs = (root / c.INPUT_DIR) if (root / c.INPUT_DIR).exists() else c.OUT / c.INPUT_DIR
        cls.records = c.read_jsonl(cls.inputs / "01_真实关联记录_119条.jsonl")
        cls.evidence = c.read_jsonl(cls.inputs / "02_原始必要选列证据.jsonl")
        cls.origins = c.read_jsonl(cls.inputs / "04_逐字段来源.jsonl")
        cls.scenario = p.load(cls.inputs / "03_课堂基础快照.json")
        cls.event = c.read_jsonl(cls.inputs / "05_唯一延期事件_CloudEvents.jsonl")[0]

    def test_all_records_reconstruct(self):
        c.validate_records(self.records, self.evidence, self.origins, c.schemas())

    def test_unmatched_retained_as_unknown(self):
        row = next(r for r in self.records if not r["menu"]["matched"])
        self.assertIsNone(row["menu"]["item_name"])
        self.assertEqual(row["missing_reasons"]["/menu/item_name"]["code"], "no_menu_match")

    def test_source_inventory_cannot_be_filled_with_scenario(self):
        bad = copy.deepcopy(self.records[0]);bad["unknown"]["actual_on_hand"] = 12
        with self.assertRaises(p.DataContractError):c.validate("public-record", bad)

    def test_unknown_is_not_zero(self):
        self.assertTrue(all(r["unknown"]["actual_prep_minutes"] is None for r in self.records))

    def test_required_property_cannot_be_deleted(self):
        bad = copy.deepcopy(self.records[0]);del bad["unknown"]["actual_on_hand"]
        with self.assertRaises(p.DataContractError):c.validate("public-record", bad)

    def test_invalid_calendar_date_rejected(self):
        bad = copy.deepcopy(self.records[0]);bad["observed"]["date"] = "2011-02-30"
        with self.assertRaises(p.DataContractError):c.validate("public-record", bad)

    def test_invalid_normalized_time_rejected(self):
        bad = copy.deepcopy(self.records[0]);bad["derived"]["start_local_time"] = "25:01:00"
        with self.assertRaises(p.DataContractError):c.validate("public-record", bad)

    def test_system_utc_rejects_timezone_absent(self):
        self.assertFalse(c.valid_utc("2026-11-03T12:00:00"))
        self.assertFalse(c.valid_utc("2026-02-30T12:00:00Z"))
        self.assertTrue(c.valid_utc("2026-11-03T12:00:00Z"))

    def test_derived_weekday_cannot_be_fabricated(self):
        bad = copy.deepcopy(self.records);bad[0]["derived"]["weekday_iso"] = (bad[0]["derived"]["weekday_iso"] % 7) + 1
        with self.assertRaises(p.DataContractError):c.validate_records(bad, self.evidence, self.origins, c.schemas())

    def test_missing_reason_cannot_be_removed(self):
        bad = copy.deepcopy(self.records);del bad[0]["missing_reasons"]["/unknown/actual_on_hand"]
        with self.assertRaises(p.DataContractError):c.validate_records(bad, self.evidence, self.origins, c.schemas())

    def test_lineage_type_cannot_relabel_assumption_as_fact(self):
        bad = copy.deepcopy(self.origins);bad[0]["fields"][0]["kind"] = "scraped_fact"
        with self.assertRaises(p.DataContractError):c.validate_records(self.records, self.evidence, bad, c.schemas())

    def test_duplicate_record_is_not_silently_overwritten(self):
        bad = copy.deepcopy(self.records);bad[1]["record_id"] = bad[0]["record_id"]
        with self.assertRaises(p.DataContractError):c.validate_records(bad, self.evidence, self.origins, c.schemas())

    def test_source_plus_id_is_event_identity(self):
        index = c.EventIdentityIndex();index.commit(self.event)
        other = copy.deepcopy(self.event);other["source"] += ":other"
        self.assertEqual(index.classify(other), "new")
        self.assertEqual(index.classify(self.event), "duplicate_ignored")

    def test_same_identity_changed_content_is_rejected(self):
        ledger = c.ClassroomLedger(self.scenario["state"]);ledger.apply(self.event)
        before = p.digest(ledger.state)
        other = copy.deepcopy(self.event);other["data"]["after"] = 11
        with self.assertRaises(p.DataContractError):ledger.apply(other)
        self.assertEqual(p.digest(ledger.state), before)

    def test_replay_does_not_repeat_transition(self):
        ledger = c.ClassroomLedger(self.scenario["state"]);ledger.apply(self.event)
        before = p.digest(ledger.state);self.assertEqual(ledger.apply(self.event)["status"], "duplicate_ignored")
        self.assertEqual(before, p.digest(ledger.state));self.assertEqual(ledger.version, 1)

    def test_version_conflict_is_atomic(self):
        ledger = c.ClassroomLedger(self.scenario["state"])
        bad = copy.deepcopy(self.event);bad["data"]["previous_version"] = 1
        with self.assertRaises(p.DataContractError):ledger.apply(bad)
        self.assertEqual(ledger.version, 0);self.assertEqual(ledger.events, []);self.assertEqual(ledger.identity.fingerprints, {})

    def test_before_value_conflict_is_atomic(self):
        ledger = c.ClassroomLedger(self.scenario["state"])
        bad = copy.deepcopy(self.event);bad["data"]["before"] = 3
        with self.assertRaises(p.DataContractError):ledger.apply(bad)
        self.assertEqual(ledger.state, self.scenario["state"])

    def test_relative_event_does_not_invent_absolute_time(self):
        self.assertNotIn("time", self.event)
        bad = copy.deepcopy(self.event);bad["time"] = "2026-11-03T12:01:00Z"
        with self.assertRaises(p.DataContractError):c.validate("event", bad)

    def test_event_minute_cannot_follow_recording_minute(self):
        ledger = c.ClassroomLedger(self.scenario["state"])
        bad = copy.deepcopy(self.event);bad["data"]["event_minute"] = 2
        with self.assertRaises(p.DataContractError):ledger.apply(bad)

    def test_missing_overlay_does_not_restore_rule(self):
        ledger = c.ClassroomLedger(self.scenario["state"]);ledger.apply(self.event)
        case = copy.deepcopy(ledger.state);case["prep_minutes"] = None
        self.assertIsNone(p.check_adjustment(case)["quantity"])
        self.assertEqual(p.project(case)["late_units"], 1)


if __name__ == "__main__":unittest.main()
