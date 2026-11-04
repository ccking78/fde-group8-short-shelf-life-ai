"""Bounded classroom data enrichment. No network calls and no statistical imputation.

Only the existing Scrapling downloads are read. Unknown operational observations
stay null; the independently labelled classroom scenario is not a source of facts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

import data_pipeline as pilot

ROOT = Path(__file__).resolve().parent
VERSION = "fde-classroom-contract-1.0.0"
SOURCE_URI = "urn:fde:group8:classroom:PILOT-01"
EVENT_TYPE = "cn.fde.group8.task.eta.changed.v1"
INPUT_DIR = "01_输入_可供智能体"
REPORT_DIR = "02_运行与验收_不作为AI输入"
SCHEMA_DIR = "schema"
OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务提交准备版_20261103\附件_规范数据")
OLD = Path(r"F:\ChatGPT\outputs\FDE_数据管线小样例_20261103")
DOWNLOADS = Path(r"F:\ChatGPT\downloads\FDE_经营异常优化_20261103")
CHECKER = FormatChecker()

GAPS = {
    "source_timezone": "源文件未提供交易地点的时区，不能推断UTC时间。",
    "kitchen_completed_at": "源文件未提供厨房完成时刻，交易结束不能替代。",
    "service_due_at": "源文件未提供顾客需用时刻，不能从收据时间推断。",
    "actual_on_hand": "源文件未提供门店在手数量。",
    "actual_prep_minutes": "源文件未提供制作时长。",
    "actual_capacity_per_batch": "源文件未提供班次和岗位产能。",
    "actual_sellable_minutes": "源文件未提供适用于该商品批次的可售规则。",
}
MENU = {
    "item_name": "Item_Description", "category_id": "Cat_ID",
    "category_name": "Cat_Description", "subcategory_id": "Sub_Cat_ID",
    "subcategory_name": "Sub_Cat_Description",
}
OBSERVED = {
    "receipt_id": ("receipt", "Receipt_ID"), "store_id": ("receipt", "Store_Num"),
    "date": ("receipt", "Date"), "start_time": ("receipt", "Start_Time"),
    "end_time": ("receipt", "End_Time"), "item_id": ("item", "Inv_Num"),
    "quantity_raw": ("item", "Count"), "return_raw": ("receipt", "Return"),
    "drive_thru_raw": ("receipt", "Drive_Thru"),
}
STANDARDS = [
    {"id": "W3C-DWBP", "title": "W3C Data on the Web Best Practices",
     "url": "https://www.w3.org/TR/dwbp/",
     "clauses": "BP4至8、22、28、31、34至35",
     "implementation": "许可、逐字段来源、质量报告、版本与修改历史、缺失原因、覆盖限制和衍生规则。"},
    {"id": "JSON-SCHEMA", "title": "JSON Schema Validation Draft 2020-12",
     "url": "https://json-schema.org/draft/2020-12/json-schema-validation",
     "clauses": "type、required、const、additionalProperties及format的应用校验",
     "implementation": "使用Draft202012Validator；显式启用本契约的日期、当地时间及UTC登记时间检查。"},
    {"id": "RFC3339", "title": "RFC 3339 Internet Timestamps",
     "url": "https://www.rfc-editor.org/rfc/rfc3339",
     "clauses": "4.4、5.6、5.7",
     "implementation": "系统登记时间用带Z的UTC格式；原交易只有当地钟表时间，保留原值且时区为空。"},
    {"id": "CLOUDEVENTS", "title": "CloudEvents Specification v1.0.2",
     "url": "https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md",
     "clauses": "Required Attributes及time",
     "implementation": "事件携带id、source、specversion=1.0和type；source与id组合去重；只有相对分钟时省略time。"},
    {"id": "JSONSCHEMA-IMPL", "title": "python-jsonschema 4.25.1 validation documentation",
     "url": "https://python-jsonschema.readthedocs.io/en/v4.25.1/validate/",
     "clauses": "Draft202012Validator及format_checker",
     "implementation": "固定依赖版本；本地schema检查和离线重放，不联网解析远程schema。"},
]


@CHECKER.checks("date")
def valid_date(value):
    if not isinstance(value, str):
        return True
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and date.fromisoformat(value) is not None
    except ValueError:
        return False


@CHECKER.checks("local-time")
def valid_local_time(value):
    if not isinstance(value, str):
        return True
    try:
        return bool(re.fullmatch(r"\d{2}:\d{2}:\d{2}", value)) and datetime.strptime(value, "%H:%M:%S") is not None
    except ValueError:
        return False


@CHECKER.checks("date-time")
def valid_utc(value):
    """This contract deliberately permits only UTC Z, a RFC3339 subset."""
    if not isinstance(value, str):
        return True
    try:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value)) and datetime.fromisoformat(value) is not None
    except ValueError:
        return False


def object_schema(properties, **kw):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False, **kw}


def string(**kw):
    return {"type": "string", "minLength": 1, **kw}


def integer(low=0, high=10000, **kw):
    return {"type": "integer", "minimum": low, "maximum": high, **kw}


def schemas():
    menu_props = {"matched": {"type": "boolean"}, **{k: {"type": ["string", "null"], "minLength": 1} for k in MENU}}
    record = object_schema({
        "contract_version": {"const": VERSION}, "record_id": string(), "evidence_id": string(),
        "observed": object_schema({k: string(**({"format": "date"} if k == "date" else {})) for k in OBSERVED}),
        "menu": object_schema(menu_props),
        "derived": object_schema({
            "quantity": {"type": "number", "exclusiveMinimum": 0, "maximum": 10000},
            "is_return": {"const": False}, "drive_thru": {"type": "boolean"},
            "start_local_time": string(format="local-time"), "end_local_time": string(format="local-time"),
            "start_hour": integer(0, 23), "weekday_iso": integer(1, 7)}),
        "unknown": object_schema({k: {"const": None} for k in GAPS}),
        "missing_reasons": {"type": "object", "minProperties": len(GAPS),
                            "additionalProperties": object_schema({"code": {"enum": ["not_in_source", "no_menu_match"]}, "reason": string()})},
    })
    state = object_schema({
        "display_sku": string(), "source_item_id": string(), "store_id": {"const": "SIM-01"},
        "window_minutes": integer(1, 1440), "on_hand": integer(), "reserved": integer(), "blocked": integer(),
        "old_sellable_until": integer(1, 1440), "new_hold_minutes": integer(1, 1440),
        "prep_minutes": integer(1, 1440),
        "plan": object_schema({"id": {"const": "TASK-8"}, "quantity": integer(),
                               "status": {"enum": ["not_started", "in_progress"]},
                               "ready_minute": integer(0, 1440), "alternative_ready_minute": integer(0, 1440),
                               "alternative_capacity": integer()}),
        "demand_due": {"type": "array", "minItems": 1, "maxItems": 8,
                       "items": object_schema({"minute": integer(0, 1440), "quantity": integer(1)})},
        "actual_discard_recorded": integer(), "as_of_minute": integer(0, 1440), "id": {"const": "PILOT-01"},
    })
    scenario = object_schema({
        "contract_version": {"const": VERSION}, "seed_record_id": string(),
        "origin": {"const": "classroom_assumption"}, "time_unit": {"const": "minute"},
        "state": state,
        "field_origins": {"type": "array", "minItems": 1,
                          "items": object_schema({"field": string(), "value": {},
                                                  "kind": {"enum": ["classroom_assumption", "source_reference"]}, "basis": string()})},
    })
    event = object_schema({
        "specversion": {"const": "1.0"}, "id": string(maxLength=80),
        "source": string(pattern=r"^urn:fde:[A-Za-z0-9:._-]+$"), "type": {"const": EVENT_TYPE},
        "subject": {"const": "SIM-01/TASK-8"}, "datacontenttype": {"const": "application/json"},
        "data": object_schema({
            "contract_version": {"const": VERSION}, "origin": {"const": "simulated_increment"},
            "scenario_id": {"const": "PILOT-01"}, "store_id": {"const": "SIM-01"}, "sku_id": string(),
            "task_id": {"const": "TASK-8"}, "event_minute": integer(0, 20), "recorded_minute": integer(0, 20),
            "previous_version": integer(0, 1), "new_version": integer(1, 1),
            "changed_field": {"const": "plan.ready_minute"}, "before": integer(0, 1440), "after": integer(0, 1440),
        }),
    })
    overlay = object_schema({
        "contract_version": {"const": VERSION}, "origin": {"const": "intentional_missing_test"},
        "applies_after_version": {"const": 1}, "override": object_schema({"prep_minutes": {"const": None}}),
        "missing_reason": string(),
    })
    result = {"public-record": record, "scenario": scenario, "event": event, "missing-overlay": overlay}
    for name, schema in result.items():
        schema.update({"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"urn:fde:schema:{name}:1.0.0"})
    return result


def validate(kind, value, schema_map=None):
    schema = (schema_map or schemas())[kind]
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema, format_checker=CHECKER).iter_errors(value), key=lambda e: str(e.path))
    if errors:
        error = errors[0]
        raise pilot.DataContractError(f"{kind} {'/'.join(map(str, error.path))}: {error.message}")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(pilot.canonical(row) + "\n" for row in rows), encoding="utf-8")


def pointers(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from pointers(child, prefix + "/" + escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from pointers(child, prefix + "/" + str(index))
    else:
        yield prefix, value


def normalized_time(raw):
    fmt = "%H:%M:%S" if raw.count(":") == 2 else "%H:%M"
    return datetime.strptime(raw, fmt).strftime("%H:%M:%S")


def normalize(evidence):
    observed = {name: evidence[section][column] for name, (section, column) in OBSERVED.items()}
    amount = Decimal(observed["quantity_raw"])
    if not amount.is_finite() or amount <= 0:
        raise pilot.DataContractError("源数量不是有限正数")
    quantity = int(amount) if amount == amount.to_integral_value() else float(amount)
    if observed["return_raw"] != "False" or observed["drive_thru_raw"] not in ("False", "True"):
        raise pilot.DataContractError("仅接收非退货及明确渠道标识")
    menu = {"matched": evidence["menu"] is not None}
    menu.update({k: evidence["menu"][col] if evidence["menu"] else None for k, col in MENU.items()})
    missing = {f"/unknown/{k}": {"code": "not_in_source", "reason": reason} for k, reason in GAPS.items()}
    if not menu["matched"]:
        missing.update({f"/menu/{k}": {"code": "no_menu_match", "reason": "完整E4菜单无此Inv_Num，保留空值，不按名称猜配。"} for k in MENU})
    return {
        "contract_version": VERSION, "record_id": f"urn:fde:mendeley:9hntk3wbwc:1:E3:{evidence['item_row']}",
        "evidence_id": evidence["evidence_id"], "observed": observed, "menu": menu,
        "derived": {"quantity": quantity, "is_return": False, "drive_thru": observed["drive_thru_raw"] == "True",
                    "start_local_time": normalized_time(observed["start_time"]),
                    "end_local_time": normalized_time(observed["end_time"]),
                    "start_hour": int(observed["start_time"].split(":")[0]),
                    "weekday_iso": date.fromisoformat(observed["date"]).isoweekday()},
        "unknown": {k: None for k in GAPS}, "missing_reasons": missing,
    }


def lineage(record, evidence):
    rows = []
    for path, value in pointers(record):
        parts = path.split("/")
        group = parts[1]
        kind, basis, source_ref = "processing_metadata", "本契约的登记或缺失说明", None
        if group == "observed":
            section, column = OBSERVED[parts[2]]
            kind, basis, source_ref = "scraped_fact", "保留源值；按Receipt_ID精确关联", f"{evidence['evidence_id']}/{section}/{column}"
        elif group == "menu" and parts[2] != "matched":
            if evidence["menu"]:
                kind, basis, source_ref = "scraped_fact", "按Inv_Num精确关联完整菜单", f"{evidence['evidence_id']}/menu/{MENU[parts[2]]}"
            else:
                kind, basis = "unknown", "完整菜单无对应Inv_Num；不猜测"
        elif group == "derived" or path == "/menu/matched":
            kind, basis = "deterministic_derivation", "确定性类型解析、时间规范化、日期派生或ID精确关联；不填入经营假设"
            source_ref = evidence["evidence_id"]
        elif group == "unknown":
            kind, basis = "unknown", GAPS[parts[2]]
        rows.append({"field": path, "value": value, "kind": kind, "basis": basis, "source_ref": source_ref})
    rows.sort(key=lambda row: row["field"])
    return {"record_id": record["record_id"], "evidence_id": evidence["evidence_id"], "fields": rows}


class EventIdentityIndex:
    """CloudEvents identity is (source, id), independent of entity version."""
    def __init__(self):
        self.fingerprints = {}

    def classify(self, event):
        key = (event["source"], event["id"])
        if key not in self.fingerprints:
            return "new"
        if self.fingerprints[key] != pilot.digest(event):
            raise pilot.DataContractError("相同source和id对应不同内容")
        return "duplicate_ignored"

    def commit(self, event):
        self.fingerprints[(event["source"], event["id"])] = pilot.digest(event)


class ClassroomLedger:
    """One admitted classroom ETA event; validate everything before committing."""
    def __init__(self, state):
        pilot.validate_snapshot(state)
        self.state = copy.deepcopy(state)
        self.version = 0
        self.identity = EventIdentityIndex()
        self.events = []

    def apply(self, event):
        validate("event", event)
        if event["source"] != SOURCE_URI:
            raise pilot.DataContractError("事件来源不在本课堂切片的登记范围")
        status = self.identity.classify(event)
        if status == "duplicate_ignored":
            return {"status": status, "version": self.version}
        if self.events:
            raise pilot.DataContractError("本轮只接收1条外部模拟增量")
        data = event["data"]
        if data["sku_id"] != self.state["source_item_id"]:
            raise pilot.DataContractError("商品引用不匹配")
        if data["previous_version"] != self.version or data["new_version"] != self.version + 1:
            raise pilot.DataContractError("状态版本冲突")
        if not self.state["as_of_minute"] <= data["event_minute"] <= data["recorded_minute"] <= self.state["window_minutes"]:
            raise pilot.DataContractError("事件分钟或登记分钟逆序")
        if data["before"] != self.state["plan"]["ready_minute"]:
            raise pilot.DataContractError("修改前值不等于当前状态")
        updated = copy.deepcopy(self.state)
        updated["plan"]["ready_minute"] = data["after"]
        updated["as_of_minute"] = data["recorded_minute"]
        pilot.validate_snapshot(updated)
        self.state = updated
        self.version = data["new_version"]
        self.events.append(copy.deepcopy(event))
        self.identity.commit(event)
        return {"status": "applied", "version": self.version}


def build_inputs(old, downloads, out):
    manifest = pilot.load(old / INPUT_DIR / "来源与规则.json")
    for file in manifest["source_files"]:
        if hashlib.sha256((downloads / file["file"]).read_bytes()).hexdigest() != file["sha256"]:
            raise pilot.DataContractError("源文件与已有Scrapling采集哈希不符")
    receipts = pilot.read_source_csv(downloads, "E1_Receipts_prefix_4MiB.csv", True)
    items = pilot.read_source_csv(downloads, "E3_Item_on_Receipt_prefix_4MiB.csv", True)
    menu = pilot.read_source_csv(downloads, "E4_Menu_Items.csv")
    if len({r["Receipt_ID"] for r in receipts}) != len(receipts) or len({r["Inv_Num"] for r in menu}) != len(menu):
        raise pilot.DataContractError("关联主键重复，不能按字典静默覆盖")
    rmap = {r["Receipt_ID"]: (n, r) for n, r in enumerate(receipts, 1)}
    mmap = {r["Inv_Num"]: (n, r) for n, r in enumerate(menu, 1)}
    evidence = []
    for n, item in enumerate(items, 1):
        receipt_entry = rmap.get(item["Receipt_ID"])
        if not receipt_entry:
            continue
        receipt_row, receipt = receipt_entry
        amount = Decimal(item["Count"])
        if receipt["Return"] != "False" or not amount.is_finite() or amount <= 0:
            continue
        menu_entry = mmap.get(item["Inv_Num"])
        evidence.append({
            "evidence_id": f"E3:{n}", "item_row": n, "receipt_row": receipt_row,
            "menu_row": menu_entry[0] if menu_entry else None,
            "receipt": {col: receipt[col] for sec, col in OBSERVED.values() if sec == "receipt"},
            "item": {"Receipt_ID": item["Receipt_ID"], "Inv_Num": item["Inv_Num"], "Count": item["Count"]},
            "menu": menu_entry[1] if menu_entry else None,
        })
    records = [normalize(row) for row in evidence]
    seed = next(r for r in records if r["evidence_id"] == "E3:35741")
    base = pilot.load(old / INPUT_DIR / "03_课堂基础快照.json")
    scenario = {"contract_version": VERSION, "seed_record_id": seed["record_id"], "origin": "classroom_assumption",
                "time_unit": "minute", "state": base,
                "field_origins": [{"field": path, "value": value,
                                   "kind": "source_reference" if path == "/source_item_id" else "classroom_assumption",
                                   "basis": "引用真实源商品ID；本案例状态仍为课堂模拟" if path == "/source_item_id"
                                   else "沿用已确认课堂切片；不是实测门店数据或通用安全标准"}
                                  for path, value in pointers(base)]}
    event = {"specversion": "1.0", "id": "SIM-INC-01", "source": SOURCE_URI, "type": EVENT_TYPE,
             "subject": "SIM-01/TASK-8", "datacontenttype": "application/json",
             "data": {"contract_version": VERSION, "origin": "simulated_increment", "scenario_id": "PILOT-01",
                      "store_id": "SIM-01", "sku_id": base["source_item_id"], "task_id": "TASK-8",
                      "event_minute": 1, "recorded_minute": 1, "previous_version": 0, "new_version": 1,
                      "changed_field": "plan.ready_minute", "before": 4, "after": 12}}
    overlay = {"contract_version": VERSION, "origin": "intentional_missing_test", "applies_after_version": 1,
               "override": {"prep_minutes": None}, "missing_reason": "故意删除课堂制作时长以验证行动阻断；未补回、未新增业务事件。"}
    inputs = out / INPUT_DIR
    write_jsonl(inputs / "01_真实关联记录_119条.jsonl", records)
    write_jsonl(inputs / "02_原始必要选列证据.jsonl", evidence)
    write_jsonl(inputs / "04_逐字段来源.jsonl", [lineage(r, e) for r, e in zip(records, evidence)])
    pilot.save(inputs / "03_课堂基础快照.json", scenario)
    write_jsonl(inputs / "05_唯一延期事件_CloudEvents.jsonl", [event])
    pilot.save(inputs / "06_缺规则测试覆写.json", overlay)
    for name, schema in schemas().items():
        pilot.save(inputs / SCHEMA_DIR / (name + ".schema.json"), schema)
    updated = {key: manifest[key] for key in ("source_url", "doi", "license", "attribution", "license_url", "limitations", "source_files")}
    updated.update({
        "contract_version": VERSION, "prepared_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "new_scraping_performed": False, "acquisition_method": "仅复用Scrapling已采集文件",
        "source_rows": {"receipts": len(receipts), "items": len(items), "menu": len(menu)},
        "selected_positive_nonreturn_rows": len(records), "menu_matched": sum(r["menu"]["matched"] for r in records),
        "menu_unmatched_retained": sum(not r["menu"]["matched"] for r in records),
        "seed_record_id": seed["record_id"], "sample_contiguous": False,
        "event_limit": 1, "simulated_new_order_count": 0, "source_identity": SOURCE_URI,
        "source_line_numbering": "1起算的数据记录序号，不含表头；E1与E3丢弃前缀的截断尾行",
        "standards": STANDARDS, "rules": pilot.RULES,
        "contract_status": "本课堂切片v1.0.0；生产增量字段、批量订单及新情景仍待后续指挥",
        "version_history": [{"from": "classroom-data-pilot-0.1", "to": VERSION,
                             "changes": "扩展真实关联选列至119条；补菜单与确定性派生；缺失显式化；事件改用CloudEvents封装；业务假设与人工记录不变"}],
        "ai_input_boundary": "本目录提供输入；本目录以外的运行结果和验收答案不得作为智能体输入",
    })
    pilot.save(inputs / "来源许可与版本.json", updated)
    shutil.copy2(old / "历史人工核对_沿用原记录.json", out / "历史人工核对_沿用原记录.json")
    return updated


def validate_records(records, evidence, origins, schema_map):
    if len(records) != len(evidence) or len(records) != len(origins) or not 1 <= len(records) <= 200:
        raise pilot.DataContractError("真实记录、选列证据及字段来源数量不一致或越界")
    if len({r["record_id"] for r in records}) != len(records) or len({e["evidence_id"] for e in evidence}) != len(evidence):
        raise pilot.DataContractError("真实记录身份重复")
    evidence_map = {e["evidence_id"]: e for e in evidence}
    origins_map = {o["record_id"]: o for o in origins}
    if len(origins_map) != len(origins):
        raise pilot.DataContractError("来源登记重复")
    for record in records:
        validate("public-record", record, schema_map)
        raw = evidence_map.get(record["evidence_id"])
        if raw is None or raw["receipt"]["Receipt_ID"] != raw["item"]["Receipt_ID"]:
            raise pilot.DataContractError("收据与商品关联证据不一致")
        if raw["menu"] and raw["menu"]["Inv_Num"] != raw["item"]["Inv_Num"]:
            raise pilot.DataContractError("菜单关联证据不一致")
        if pilot.canonical(record) != pilot.canonical(normalize(raw)):
            raise pilot.DataContractError("补全值不能从选列证据重算")
        if pilot.canonical(origins_map.get(record["record_id"])) != pilot.canonical(lineage(record, raw)):
            raise pilot.DataContractError("逐字段来源存在遗漏、错误值或错误来源类型")
        null_paths = {path for path, value in pointers(record) if value is None and not path.startswith("/missing_reasons/")}
        if null_paths != set(record["missing_reasons"]):
            raise pilot.DataContractError("空值与缺失原因不能逐一对应")


def run(inputs):
    inputs = Path(inputs)
    records = read_jsonl(inputs / "01_真实关联记录_119条.jsonl")
    evidence = read_jsonl(inputs / "02_原始必要选列证据.jsonl")
    origins = read_jsonl(inputs / "04_逐字段来源.jsonl")
    scenario = pilot.load(inputs / "03_课堂基础快照.json")
    events = read_jsonl(inputs / "05_唯一延期事件_CloudEvents.jsonl")
    overlay = pilot.load(inputs / "06_缺规则测试覆写.json")
    manifest = pilot.load(inputs / "来源许可与版本.json")
    schema_map = {name: pilot.load(inputs / SCHEMA_DIR / (name + ".schema.json")) for name in schemas()}
    if pilot.canonical(schema_map) != pilot.canonical(schemas()):
        raise pilot.DataContractError("schema与本程序契约版本不一致")
    validate_records(records, evidence, origins, schema_map)
    validate("scenario", scenario, schema_map)
    validate("missing-overlay", overlay, schema_map)
    if len(events) != 1:
        raise pilot.DataContractError("只保留1条外部增量")
    seed = next((r for r in records if r["record_id"] == scenario["seed_record_id"]), None)
    if not seed or not seed["menu"]["matched"] or seed["observed"]["item_id"] != scenario["state"]["source_item_id"]:
        raise pilot.DataContractError("课堂种子引用不一致")
    listed = scenario["field_origins"]
    actual = dict(pointers(scenario["state"]))
    if len(listed) != len(actual) or {r["field"] for r in listed} != set(actual):
        raise pilot.DataContractError("课堂字段来源覆盖不完整")
    for row in listed:
        wanted_kind = "source_reference" if row["field"] == "/source_item_id" else "classroom_assumption"
        if row["value"] != actual[row["field"]] or row["kind"] != wanted_kind:
            raise pilot.DataContractError("课堂假设与真实字段引用混淆")
    if not valid_utc(manifest["prepared_at_utc"]):
        raise pilot.DataContractError("系统登记时间无有效UTC时区")
    if (manifest["contract_version"] != VERSION or manifest["sample_contiguous"] is not False
            or manifest["selected_positive_nonreturn_rows"] != len(records)
            or manifest["menu_matched"] != sum(r["menu"]["matched"] for r in records)
            or manifest["menu_unmatched_retained"] != sum(not r["menu"]["matched"] for r in records)
            or manifest["simulated_new_order_count"] != 0 or manifest["event_limit"] != len(events)
            or manifest["source_identity"] != SOURCE_URI or manifest["seed_record_id"] != seed["record_id"]):
        raise pilot.DataContractError("来源版本或覆盖范围登记与输入不一致")
    frozen = pilot.digest(scenario)
    ledger = ClassroomLedger(scenario["state"])
    applied = ledger.apply(events[0])
    duplicated = ledger.apply(events[0])
    missing = copy.deepcopy(ledger.state)
    missing.update(overlay["override"])
    cases = {"normal": scenario["state"], "delay": ledger.state, "missing": missing}
    results = {key: {"projection": pilot.project(value), "adjustment_check": pilot.check_adjustment(value)} for key, value in cases.items()}
    results["normal"]["adjustment_check"] = {"not_requested": True, "reason": "已有计划及时覆盖，维持计划"}
    checks = []
    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
    check("结构和格式校验", True, f"{len(records)}条真实记录及课堂快照、事件、缺规则覆写通过Draft202012Validator及本地format检查")
    check("真实来源与字段来源覆盖", True, "每个真实选列与衍生值均能从必要选列证据重算；原始大文件哈希在构建时核验")
    check("未知字段保留空值与原因", True, "每个null均有缺失原因；未填0、未用课堂假设替代真实观测")
    check("样本覆盖如实登记", True, "119条正数量非退货；52匹配菜单，67未匹配保留；不是连续交易")
    check("事件组合身份去重", duplicated["status"] == "duplicate_ignored" and len(ledger.events) == 1, "相同source和id同内容重放忽略；修改前值及版本原子校验")
    for key, result in results.items():
        projection = result["projection"]
        check(f"{key}数量守恒", projection["conservation_pass"], "逐事件核对期初可分配+投影供给=履约+剩余+截止排除")
    check("正常不重复制作", results["normal"]["projection"]["late_units"] == 0, "已有8份第4分钟完成")
    check("延迟时点风险", results["delay"]["projection"]["late_units"] == 1
          and results["delay"]["projection"]["first_late_minute"] == 10
          and results["delay"]["projection"]["delay_unit_minutes"] == 2, "第10分钟迟供1份，第12分钟补供；不是损失销量")
    check("缺规则阻断行动", results["missing"]["adjustment_check"]["quantity"] is None
          and results["missing"]["projection"]["late_units"] == 1, "保留由ETA支持的风险；不生成可采纳调整量")
    check("预设调整可行性", results["delay"]["adjustment_check"]["action_adoptable"], "课堂产能假设下原8份第8分钟完成；不新增审批或实际完成记录")
    check("快照不受投影写入影响", pilot.digest(scenario) == frozen and ledger.state["on_hand"] == 12, "模拟供给不是实际入库")
    from anomaly_tools import simulate
    comparison = ("late_units", "first_late_minute", "backlog_end", "delay_unit_minutes", "served_by_horizon", "remaining_available", "expired_unavailable")
    for key, case in cases.items():
        independent = simulate(case)
        check(f"{key}与既有算法核对", all(results[key]["projection"][k] == independent[k] for k in comparison), list(comparison))
    if not all(row["passed"] for row in checks):
        raise pilot.DataContractError("数据补全运行核验失败")
    input_hashes = {p.relative_to(inputs).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs.rglob("*")) if p.is_file()}
    return {"contract_version": VERSION, "input_sha256": pilot.digest(input_hashes), "checks": checks, "passed": True,
            "coverage": {"real_records": len(records), "menu_matched": manifest["menu_matched"], "menu_unmatched_retained": manifest["menu_unmatched_retained"],
                         "null_cells_explained": sum(len(r["missing_reasons"]) for r in records),
                         "lineage_fields": sum(len(o["fields"]) for o in origins), "source_records_used_in_simulation": 1, "simulated_increments": len(events), "new_simulated_orders": 0},
            "seed": seed, "results": results, "ingestion": {"first": applied, "second": duplicated, "events_applied": len(ledger.events)},
            "actual_completion_recorded": False, "rules": pilot.RULES,
            "runtime": {"python": sys.version.split()[0],
                        "simpy": importlib.metadata.version("simpy"), "jsonschema": importlib.metadata.version("jsonschema")}}


def write_outputs(out, report):
    out.mkdir(parents=True, exist_ok=True)
    pilot.save(out / REPORT_DIR / "数据补全与运行核验.json", report)
    pilot.save(out / REPORT_DIR / "验收答案_不得作为AI输入.json", {
        "normal_late_units": 0, "delay_late_units": 1, "first_late_minute": 10,
        "missing_action_quantity": None, "adjust_existing_quantity": 8, "additional_quantity": 0,
        "actual_completion_recorded": False})
    template = (ROOT / "completion_report.html").read_text(encoding="utf-8")
    data = {"report": report, "records": read_jsonl(out / INPUT_DIR / "01_真实关联记录_119条.jsonl"), "standards": STANDARDS}
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    (out / "00_打开数据补全报告.html").write_text(template.replace("__COMPLETION_JSON__", payload), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "replay"))
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--old-pilot", type=Path, default=OLD)
    parser.add_argument("--downloads", type=Path, default=DOWNLOADS)
    args = parser.parse_args()
    if args.mode == "build":
        build_inputs(args.old_pilot, args.downloads, args.output)
    inputs = args.inputs or args.output / INPUT_DIR
    report = run(inputs)
    pilot.save(args.output / REPORT_DIR / "数据补全与运行核验.json", report)
    if args.mode == "build":
        write_outputs(args.output, report)
        for name in ("data_completion.py", "data_pipeline.py", "anomaly_tools.py", "completion_report.html", "test_data_completion.py", "test_data_pipeline.py"):
            shutil.copy2(ROOT / name, args.output / name)
    print(json.dumps({"output": str(args.output), "passed": report["passed"], "checks": len(report["checks"]),
                      "coverage": report["coverage"], "input_sha256": report["input_sha256"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
