import json
import os
from pathlib import Path

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = r"F:\ChatGPT\work\runtimes\scrapling\browsers"
from playwright.sync_api import sync_playwright

OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务提交准备版_20261103")
WORK = Path(r"F:\ChatGPT\work\FDE_数据补全与提交准备_20261103")


def main():
    capture = WORK / "browser";capture.mkdir(parents=True, exist_ok=True)
    checks=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1440,"height":1040})
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto((OUT / "附件_规范数据" / "00_打开数据补全报告.html").as_uri());page.wait_for_load_state("networkidle")
        assert page.locator("#recordsCount").inner_text()=="119"
        assert page.locator("#matchedCount").inner_text()=="52"
        assert page.locator("#unmatchedCount").inner_text()=="67"
        assert page.locator("#record option").count()==119
        assert "35741" in page.locator("#recordDetail").inner_text()
        assert "MINI TUNA" in page.locator("#fieldBody").inner_text()
        checks.append("真实记录119、菜单匹配52、未匹配67，默认种子MINI TUNA")
        page.screenshot(path=str(capture / "01_补全报告_桌面.png"),full_page=True)
        page.screenshot(path=str(capture / "01_补全报告_预览.png"),clip={"x":0,"y":0,"width":1440,"height":1040})
        page.locator("#filter").select_option("unmatched")
        assert page.locator("#record option").count()==67
        assert "完整菜单无此Inv_Num" in page.locator("#fieldBody").inner_text() or "完整E4菜单无此Inv_Num" in page.locator("#fieldBody").inner_text()
        assert "null（未知）" in page.locator("#fieldBody").inner_text()
        checks.append("未匹配记录保留空值、原ID和明确缺失原因")
        page.locator("#filter").select_option("matched")
        assert page.locator("#record option").count()==52
        assert "源文件未提供制作时长" in page.locator("#fieldBody").inner_text()
        checks.append("菜单补全没有填入虚构制作时长")
        assert page.locator("#checks tr").count()==16
        assert page.locator("#standards li").count()==5
        checks.append("页面展示16项实际核验与5条规范依据")
        page.goto((OUT / "00_打开经营异常课堂演示.html").as_uri());page.wait_for_load_state("networkidle")
        assert "正常计划" in page.locator("#status").inner_text()
        page.locator("#delayBtn").click();assert page.evaluate("simulate(S.case).late_units")==1
        page.locator("#acceptBtn").click();assert not page.evaluate("S.accepted")
        page.locator("#verified").check();page.locator("#reason").fill("自动化课堂演示核验，不是用户新的人工确认")
        page.locator("#acceptBtn").click();assert page.evaluate("S.accepted && S.stock===12 && S.pending===8")
        checks.append("演示延期迟供1份；未核实不能采纳；采纳仅改原任务、库存不变")
        page.locator("#missingBtn").click();assert page.locator("#actionForm").is_hidden()
        assert page.evaluate("simulate(S.case,8,8).quantity") is None
        checks.append("演示缺制作时长仍阻断调整")
        page.locator('a[href="附件_规范数据/00_打开数据补全报告.html"]').click();page.wait_for_load_state("networkidle")
        assert page.locator("#recordsCount").inner_text()=="119"
        checks.append("经营演示可直接打开本次数据补全报告")
        page.set_viewport_size({"width":390,"height":844})
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.screenshot(path=str(capture / "02_补全报告_手机.png"),full_page=True)
        checks.append("390px页面无整体水平溢出，宽表可在容器内查看")
        assert not errors,errors
        browser.close()
    result={"passed":True,"checks":checks,"page_errors":errors,"scope":"真实本地浏览器；本轮未新录视频；旧录屏作历史证据保留"}
    (WORK / "浏览器核验.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
