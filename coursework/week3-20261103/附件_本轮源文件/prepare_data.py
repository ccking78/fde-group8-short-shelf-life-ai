"""Create a traceable public-data base and explicitly simulated increments."""
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from inspect_source_sample import DOWNLOADS, read

ROOT = Path(__file__).resolve().parent
OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103")
DATA = OUT / "附件_数据与来源"
SOURCE = "https://data.mendeley.com/datasets/9hntk3wbwc/1"


def write_csv(name, fields, rows):
    with (DATA / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    raw_r = read("E1_Receipts_prefix_4MiB.csv", True)
    raw_i = read("E3_Item_on_Receipt_prefix_4MiB.csv", True)
    menu = read("E4_Menu_Items.csv")
    receipts = {r["Receipt_ID"]: (n, r) for n, r in enumerate(raw_r, 1)}
    menus = {r["Inv_Num"]: r for r in menu}
    public_rows = []
    item_rows = []
    rejected = Counter()
    for n, item in enumerate(raw_i, 1):
        try:
            qty = float(item["Count"])
        except (TypeError, ValueError):
            rejected["invalid_quantity"] += 1
            continue
        item_rows.append({"source_row": n, "receipt_id": item["Receipt_ID"],
                          "source_item_id": item["Inv_Num"], "source_count": item["Count"],
                          "origin": "scraped_fact", "source_file": "E3_Item_on_Receipt.csv"})
        if item["Receipt_ID"] not in receipts:
            rejected["receipt_not_in_bounded_sample"] += 1
            continue
        rn, receipt = receipts[item["Receipt_ID"]]
        if receipt.get("Return") != "False" or qty <= 0 or not qty.is_integer():
            rejected["return_or_nonpositive_or_fractional"] += 1
            continue
        mapped = menus.get(item["Inv_Num"])
        public_rows.append({
            "source_item_row": n, "source_receipt_row": rn, "receipt_id": item["Receipt_ID"],
            "source_store": receipt["Store_Num"], "source_date": receipt["Date"],
            "source_start_time": receipt["Start_Time"], "source_end_time": receipt["End_Time"],
            "source_item_id": item["Inv_Num"], "source_item_name": mapped["Item_Description"] if mapped else "",
            "source_count": int(qty), "menu_match": bool(mapped), "origin": "scraped_fact",
        })
    write_csv("01_原始商品行选列.csv", list(item_rows[0]), item_rows)
    write_csv("02_可关联交易选列.csv", list(public_rows[0]), public_rows)
    write_csv("03_原始菜单选列.csv", ["Inv_Num", "Item_Description", "Cat_Description", "Sub_Cat_Description"],
              [{k: r[k] for k in ["Inv_Num", "Item_Description", "Cat_Description", "Sub_Cat_Description"]} for r in menu])

    seed = next(r for r in public_rows if r["source_item_id"] == "1023" and r["source_count"] == 1)
    base = {
        "display_sku": "迷你三明治 A", "source_item_id": "1023", "source_item_name": menus["1023"]["Item_Description"],
        "seed_source_item_row": seed["source_item_row"], "seed_source_receipt_row": seed["source_receipt_row"],
        "source_url": SOURCE, "store_id": "SIM-01", "window_minutes": 20,
        "on_hand": 12, "reserved": 5, "blocked": 0,
        "old_sellable_until": 28, "new_hold_minutes": 30, "prep_minutes": 4,
        "plan": {"id": "TASK-8", "quantity": 8, "status": "not_started", "ready_minute": 4,
                 "alternative_ready_minute": 8, "alternative_capacity": 8},
        "demand_due": [{"minute": m, "quantity": q} for m, q in zip([5, 10, 15, 20], [4, 4, 4, 3])],
        "actual_discard_recorded": 0, "history_quantities": [13, 14, 15, 16, 17],
        "origins": {
            "source_item_id": "scraped_fact", "source_item_name": "scraped_fact", "source_*": "scraped_fact",
            "display_sku": "simulated_mapping", "store_id": "simulated", "on_hand": "simulated",
            "reserved": "simulated", "blocked": "simulated", "plan": "simulated",
            "demand_due": "simulated_forecast_schedule", "history_quantities": "simulated_history",
            "prep_minutes": "simulated_rule", "old_sellable_until": "simulated_rule",
            "new_hold_minutes": "simulated_rule", "actual_discard_recorded": "simulated_event_ledger",
        },
        "limitations": [
            "公开文件的两个4MiB前缀不是连续交易序列，不能估计某店高峰订单强度。",
            "历史窗口、分钟到单、当前库存、在制、制作规则与可售规则均为课堂模拟。",
            "源门店是否提前备成品未知；模拟映射不代表源门店实际采用该流程。",
            "交易起止时间不是厨房完成时间或顾客等待时间。",
            "到可售截止的排除量不等于实际已报废量。",
        ],
    }
    cases = []
    for key, name, desc in [
        ("normal", "正常计划", "现有8份待办第4分钟完成，及时覆盖，无需新增制作。"),
        ("delay", "制作延迟", "同一待办改为第12分钟完成；核实排队与可调整时点，比较保持和调整原待办。"),
        ("missing", "缺制作时间副本", "从延迟案例仅删除制作时间；保留已知预计完成时点，停给可采纳调整量。"),
    ]:
        case = json.loads(json.dumps(base))
        case.update(id=key, name=name, description=desc, snapshot_version=f"SIM-{key}-v1", as_of_minute=0)
        if key == "delay":
            case["plan"]["ready_minute"] = 12
        if key == "missing":
            case["plan"]["ready_minute"] = 12
            case["prep_minutes"] = None
        case["events"] = [
            {"id": "E0", "minute": 0, "type": "snapshot", "origin": "simulated"},
            {"id": "E1", "minute": 1, "type": {"normal": "scheduled_review", "delay": "task_eta_changed",
                                                    "missing": "missing_task_evidence"}[key],
             "origin": "simulated_increment"},
        ]
        cases.append(case)
    (DATA / "04_模拟情景.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    increments = [{"example_id": "INC-01", "simulated_store": "SIM-01", "simulated_sku": base["display_sku"],
                   "minute": 1, "task_id": "TASK-8", "field": "ready_minute", "before": 4, "after": 12,
                   "origin": "simulated_increment", "schema_status": "课堂临时样例 待用户指导正式增量规范",
                   "note": "只注入这一条制作延迟事件，不生成批量订单"}]
    write_csv("05_模拟事件样例.csv", list(increments[0]), increments)
    # This exact draft file was produced by this script earlier in this task.
    # Replace the abandoned draft with the small increment requested by the user.
    abandoned = DATA / "05_模拟新增订单.csv"
    if abandoned.exists():
        abandoned.unlink()
    hist = [{"window_id": f"H{i}", "minutes": 20, "quantity": q, "origin": "simulated_history",
             "method": "预设课堂窗口，不从不完整公开样本估计到单强度"} for i, q in enumerate(base["history_quantities"], 1)]
    write_csv("06_模拟历史窗口.csv", list(hist[0]), hist)
    lineage = [
        ("source_item_id / source_item_name", "爬取事实", "E4原字段；不改为目标门店事实"),
        ("source_count / receipt_id", "爬取事实", "E3原字段；保留源记录序号"),
        ("source_store / date / start / end", "爬取事实", "仅保留E1可精确关联行；交易起止不当等待或制作时间"),
        ("menu_match / joined_record", "派生", "按原始Receipt_ID和Inv_Num精确关联；缺失不猜配"),
        ("display_sku / SIM-01", "模拟映射", "源商品映射为课堂SKU；不是原门店现状"),
        ("history_quantities", "模拟", "固定13、14、15、16、17；不当作真实历史销量"),
        ("forecast_qty", "派生自模拟", "五个模拟窗口均值15；不是由公开样本估计的真实预测"),
        ("demand_due / minute", "模拟假设", "四个预设需用时点，不生成批量增量订单"),
        ("INC-01 ready_minute", "模拟增量", "唯一事件为4改12；字段仅为课堂临时样例，正式规范待用户指导"),
        ("on_hand / reserved / blocked", "模拟", "12、5、0；程序派生可分配7"),
        ("plan / quantity / ready / alternative", "模拟", "预设8份待办和可调整产能；事实须由制作岗位核实"),
        ("prep_minutes / hold / sellable_until", "模拟规则", "仅用于课堂校验；不构成真实门店规则或食品安全标准"),
        ("late_units / unit_minutes / remaining", "派生自模拟", "按供给与需用时点模拟；不是实测等待、损耗或收益"),
        ("expired_unavailable", "派生自模拟", "到截止排除；实际报废另记"),
        ("human decision / actual completion", "课堂操作", "浏览器操作者的演示记录；不冒充真实经营审批"),
    ]
    write_csv("07_字段来源表.csv", ["field", "origin", "rule"], [dict(zip(["field", "origin", "rule"], r)) for r in lineage])
    manifest = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(), "acquisition_tool": "Scrapling 0.4.15",
        "source_url": SOURCE, "doi": "10.17632/9hntk3wbwc.1", "license": "CC BY 4.0",
        "attribution": "Cazier, Joseph; Spaulding, Trent; Hassler, Edgar (2025), Sandwich Analytics, Mendeley Data V1",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "sample_strategy": "E1和E3各取bytes 0-4194303，丢弃末尾不完整记录；E4完整下载并核对发布方SHA256",
        "receipt_rows": len(raw_r), "item_rows": len(raw_i), "menu_rows": len(menu),
        "joined_positive_rows": len(public_rows), "menu_matched_joined_rows": sum(r["menu_match"] for r in public_rows),
        "selected_source_row": seed, "simulated_increment_rows": len(increments),
        "simulation_scope": "1店1SKU；正常、延迟两个对照；缺制作时间为延迟输入的删字段副本",
        "increment_schema_status": "课堂临时样例；未制定正式增量规范；待用户后续指挥",
        "rejections": dict(rejected), "source_date_min": min(r["source_date"] for r in public_rows),
        "source_date_max": max(r["source_date"] for r in public_rows),
        "privacy_transform": "公开样本导出仅保留关联与数量时间字段，不导出员工姓名及收款信息",
        "limitations": base["limitations"],
        "source_acquisitions": [json.loads(s) for s in (DOWNLOADS / "acquisition_log.jsonl").read_text(encoding="utf-8").splitlines()],
    }
    (DATA / "数据清单.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ["receipt_rows", "item_rows", "menu_rows", "joined_positive_rows", "menu_matched_joined_rows", "simulated_increment_rows", "simulation_scope"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
