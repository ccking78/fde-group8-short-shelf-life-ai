"""Inspect public sample without printing employee names or unrelated fields."""
import csv
import io
import json
from collections import Counter
from pathlib import Path

DOWNLOADS = Path(r"F:\ChatGPT\downloads\FDE_经营异常优化_20261103")


def read(name, partial=False):
    body = (DOWNLOADS / name).read_bytes()
    if partial:
        body = body[:body.rfind(b"\n") + 1]
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
    return rows


def main():
    receipts = read("E1_Receipts_prefix_4MiB.csv", True)
    items = read("E3_Item_on_Receipt_prefix_4MiB.csv", True)
    menu = read("E4_Menu_Items.csv")
    rmap = {r["Receipt_ID"]: r for r in receipts}
    mmap = {r["Inv_Num"]: r for r in menu}
    joined = [(i, rmap[i["Receipt_ID"]]) for i in items if i["Receipt_ID"] in rmap]
    top = Counter(i["Inv_Num"] for i, r in joined if r.get("Return") == "False" and float(i["Count"]) > 0)
    print(json.dumps({
        "receipt_records": len(receipts), "item_records": len(items), "menu_records": len(menu),
        "joined_item_records": len(joined),
        "top_menu": [{"item": k, "n": v, "menu": mmap.get(k)} for k, v in top.most_common(12)],
        "date_min": min(r["Date"] for i, r in joined), "date_max": max(r["Date"] for i, r in joined),
        "safe_example": [{"date": r["Date"], "store": r["Store_Num"], "start": r["Start_Time"],
                          "end": r["End_Time"], "item": i["Inv_Num"], "qty": i["Count"]} for i, r in joined[:3]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
