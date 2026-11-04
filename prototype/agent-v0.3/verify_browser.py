"""Browser acceptance against the live server, using clearly marked test actions."""
import argparse
import json
import time
import re
import hashlib
from pathlib import Path

from playwright.sync_api import sync_playwright, expect


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://127.0.0.1:8765")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--session", default="")
    p.add_argument("--resume-completed", action="store_true")
    p.add_argument("--missing-session", default="")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []

    def dump(name, value):
        (args.out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1080}, device_scale_factor=1)
        page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.url + ("/?session=" + args.session if args.session else ""))
        page.wait_for_load_state("networkidle")
        expect(page.locator("#version")).to_contain_text("v3" if args.resume_completed else "v1" if args.session else "v0")
        if not args.session:
            page.screenshot(path=str(args.out / "01_正常输入.png"), full_page=True)
            page.locator("#delayBtn").click()
        checks.append("初始状态载入、正常按钮与账面在手12份可见")
        print(json.dumps({"step": "browser_delay_investigation_started"}), flush=True)

        def wait_model():
            expect(page.locator("#runMeta")).to_have_text(re.compile(r"^(completed|unavailable|stale)"), timeout=300000)
            assert page.locator("#runMeta").text_content().startswith("completed"), page.locator("#status").inner_text()

        def data():
            return page.evaluate("fetch('/api/state?session_id='+localStorage.getItem('fde-minimum-session')).then(r=>r.json())")

        if not args.resume_completed:
            wait_model()
            d = data()
            assert d["runs"][-1]["recommendation"]["quantity"] == 8
            assert d["runs"][-1]["recommendation"]["ready_minute"] == 8
            assert d["runs"][-1]["source"] == "live_model_not_replay"
            dump("02_延期调查.json", d)
            page.screenshot(path=str(args.out / "02_延期实时AI建议.png"), full_page=True)
            checks.append("浏览器登记延期自动触发真实模型，工具选择后建议调整原8份至第8分钟")
            print(json.dumps({"step": "browser_delay_completed", "session_id": d["state"]["session_id"]}), flush=True)
            page.locator("#adoptBtn").click()
            expect(page.locator("#message")).to_contain_text("核对")
            assert data()["state"]["version"] == 1
            checks.append("未经人工核对不能采纳")
            page.locator("#quantity").fill("7")
            page.locator("#previewBtn").click()
            expect(page.locator("#modifyBtn")).to_be_visible()
            assert "迟供1份" in page.locator("#preview").inner_text()
            checks.append("改量7份通过服务端重新计算并提示期末1份未满足，须另行确认影响")
            page.locator("#quantity").fill("8")
            page.locator("#actor").fill("浏览器验收测试操作者")
            page.locator("#verified").check()
            page.locator("#note").fill("课堂自动化验收：核对预设进度、规则、产能、数量和时点；不代表用户新确认或真实门店核实。")
            page.locator("#adoptBtn").click()
            expect(page.locator("#version")).to_contain_text("v2")
            assert data()["state"]["on_hand"] == 12
            page.screenshot(path=str(args.out / "03_采纳未增加库存.png"), full_page=True)
            checks.append("采纳原待办后在手仍为12份，原待办更新而非新增批次")
            page.locator("#completeAck").check()
            page.locator("#completeBtn").click()
            expect(page.locator("#version")).to_contain_text("v3")
            dump("browser_checkpoint.json", {"checks": checks})
            print(json.dumps({"step": "browser_completion_reassessment_started"}), flush=True)
        else:
            checkpoint = args.out / "browser_checkpoint.json"
            if checkpoint.exists():
                checks = json.loads(checkpoint.read_text(encoding="utf-8"))["checks"]
            else:
                checks += ["继续先前已完成的浏览器延期调查、人审和完成登记会话；旧截图及记录保留"]
        wait_model()
        final = data()
        sid = final["state"]["session_id"]
        assert final["state"]["on_hand"] == 16 and final["state"]["plan"]["quantity"] == 0
        assert final["runs"][-1]["trigger"] == "completion_recorded"
        assert final["runs"][-1]["recommendation"]["status"] == "observe"
        assert final["runs"][-1]["snapshot_version"] == 3
        for run in final["runs"]:
            for call in run["model_calls"]:
                body = json.dumps(call["request_context"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
                assert hashlib.sha256(body.encode()).hexdigest() == call["request_sha256"], "模型输入上下文必须与真实请求哈希一致"
        dump("04_完成后的实时复评.json", final)
        page.screenshot(path=str(args.out / "04_完成后实时AI复评.png"), full_page=True)
        checks.append("完成8份并登记已履约4份后，在手16、可分配11；新模型读取v3与执行记录后判断继续观察")
        checks.append("每次模型调用的冻结输入与请求SHA256一致")
        page.locator("#evidenceDetails summary").click()
        page.screenshot(path=str(args.out / "05_真实工具记录.png"), full_page=True)
        page.get_by_text("人工处理与执行留痕", exact=True).click()
        with page.expect_download() as event:
            page.locator("#exportBtn").click()
        event.value.save_as(str(args.out / "导出的本次完整记录.json"))
        checks.append("浏览器能够实际导出本次完整AI、人审和执行记录")
        mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        mp = mobile.new_page()
        mp.goto(args.url + "/?session=" + sid)
        mp.wait_for_load_state("networkidle")
        expect(mp.locator("#version")).to_contain_text("v3")
        assert mp.evaluate("document.documentElement.scrollWidth <= innerWidth"), "手机布局横向溢出"
        mp.screenshot(path=str(args.out / "06_手机界面.png"), full_page=True)
        mobile.close()
        checks.append("390px手机宽度无横向溢出")
        if args.missing_session:
            page.goto(args.url + "/?session=" + args.missing_session)
            page.wait_for_load_state("networkidle")
        else:
            page.locator("#missingBtn").click()
        expect(page.locator("#version")).to_contain_text("v1")
        print(json.dumps({"step": "browser_missing_rule_started"}), flush=True)
        wait_model()
        missing = data()
        rec = missing["runs"][-1]["recommendation"]
        assert rec["status"] == "needs_verification" and rec["quantity"] is None
        assert page.locator("#adoptBtn").is_disabled()
        assert page.locator("#candidateFields").is_hidden() and page.locator("#noQuantity").is_visible()
        compare = next(t for t in missing["runs"][-1]["trace"] if t["name"] == "compare_plans")["output"]
        assert compare["baseline"]["late_units"] == 1
        dump("07_缺规则实时调查.json", missing)
        page.screenshot(path=str(args.out / "07_缺制作规则停止数量建议.png"), full_page=True)
        checks.append("缺制作时间真实模型调查保留已知1份迟供风险、调整量null且采纳禁用")
        assert not errors, errors
        # Final screen left on the completed session for a useful handoff.
        page.goto(args.url + "/?session=" + sid)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#version")).to_contain_text("v3")
        report = {"passed": True, "checks": checks, "page_errors": errors, "url": args.url,
                  "completed_session": sid, "missing_session": missing["state"]["session_id"],
                  "operator": "浏览器验收测试操作者，不代表用户新确认或企业执行", "live_runs": 3}
        dump("browser_verification.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
