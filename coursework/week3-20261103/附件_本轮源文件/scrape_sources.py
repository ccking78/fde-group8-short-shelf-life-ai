"""Public source acquisition. All HTTP requests use the user's Scrapling runtime."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scrapling.fetchers import Fetcher

WORK = Path(r"F:\ChatGPT\work\FDE_经营异常优化_20261103")
DOWNLOADS = Path(r"F:\ChatGPT\downloads\FDE_经营异常优化_20261103")
SOURCE_URL = "https://data.mendeley.com/datasets/9hntk3wbwc/1"


def get(url, name, **kwargs):
    response = Fetcher.get(url, timeout=45, **kwargs)
    body = bytes(response.body)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    dest = DOWNLOADS / name
    dest.write_bytes(body)
    record = {
        "url": url, "final_url": str(response.url), "http_status": response.status,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "acquisition": "Scrapling Fetcher.get", "file": name,
        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        "requested_range": kwargs.get("headers", {}).get("Range"),
        "content_range": dict(response.headers).get("content-range"),
    }
    with (DOWNLOADS / "acquisition_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if response.status not in (200, 206):
        raise RuntimeError(record)
    return response, body, record


def discover():
    page, body, record = get(SOURCE_URL, "dataset_landing.html")
    print(json.dumps(record, ensure_ascii=False))
    for s in page.css('script[type="application/ld+json"]::text').getall():
        print(s[:6000])
    print("LINKS", json.dumps(page.css("a::attr(href)").getall(), ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["discover", "get", "samples"])
    p.add_argument("--url")
    p.add_argument("--name")
    a = p.parse_args()
    if a.stage == "discover":
        discover()
    elif a.stage == "samples":
        files = json.loads((DOWNLOADS / "files_index.json").read_text(encoding="utf-8"))
        for name in ["E4_Menu_Items.csv", "E1_Receipts.csv", "E3_Item_on_Receipt.csv"]:
            file = next(x for x in files if x["filename"] == name)
            partial = file["size"] > 1000000
            headers = {"Range": "bytes=0-4194303"} if partial else {}
            saved = name.replace(".csv", "_prefix_4MiB.csv") if partial else name
            _, body, rec = get(file["content_details"]["download_url"], saved, headers=headers)
            if partial and len(body) > 5000000:
                raise RuntimeError("Server did not honor bounded range")
            if not partial:
                assert rec["sha256"] == file["content_details"]["sha256_hash"]
            print(json.dumps(rec, ensure_ascii=False))
            print("FIRST LINES", body.decode("utf-8-sig", errors="replace").splitlines()[:4])
    else:
        _, body, rec = get(a.url, a.name)
        print(json.dumps(rec, ensure_ascii=False))
        if len(body) < 80000:
            print(body.decode("utf-8", errors="replace")[:18000])


if __name__ == "__main__":
    main()
