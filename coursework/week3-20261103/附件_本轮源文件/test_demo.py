"""Meaningful local UI checks and a real 30-second browser recording."""
import json
import os
import sys
import time
from pathlib import Path

os.environ["PLAYWRIGHT_BROWSERS_PATH"] = r"F:\ChatGPT\work\runtimes\scrapling\browsers"
from playwright.sync_api import sync_playwright
from anomaly_tools import simulate

OUT=Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103")
WORK=Path(r"F:\ChatGPT\work\FDE_经营异常优化_20261103")
CAP=WORK/'capture'
URL='http://127.0.0.1:8771/00_打开经营异常课堂演示.html'


def state(page):
    return page.evaluate('JSON.parse(JSON.stringify(S))')


def main():
    CAP.mkdir(parents=True,exist_ok=True)
    checks=[];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={"width":1440,"height":1080},device_scale_factor=1)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(URL);page.wait_for_load_state('networkidle')
        assert '正常计划' in page.locator('#status').inner_text()
        assert page.locator('#actionForm').is_hidden()
        page.screenshot(path=str(CAP/'01_正常不报警.png'),full_page=True)
        checks.append('正常计划不发起新增制作')
        for case in ['normal','delay','missing']:
            page.locator('#'+case+'Btn').click()
            current=state(page)['case'];actual=page.evaluate('simulate(S.case)');expected=simulate(current)
            for key in ['late_units','first_late_minute','backlog_end','delay_unit_minutes','served_by_horizon','remaining_available','expired_unavailable']:
                assert actual[key]==expected[key],(case,key,actual,expected)
        checks.append('JS与Python在三个输入上的迟供、补供、余量和截止口径一致')
        page.locator('#delayBtn').click()
        assert page.evaluate('simulate(S.case).late_units')==1
        page.screenshot(path=str(CAP/'02_制作延迟_实际浏览器.png'),full_page=True)
        page.screenshot(path=str(CAP/'02_制作延迟_报告用.png'),clip={"x":120,"y":0,"width":1200,"height":1000})
        page.locator('#acceptBtn').click()
        assert not state(page)['accepted'] and state(page)['stock']==12
        checks.append('未核事实与理由时不能采纳')
        page.locator('#taskQty').fill('6')
        assert page.locator('#riskAckRow').is_visible()
        page.locator('#verified').check();page.locator('#reason').fill('自动化课堂演示核实，不是傅浩诚新的经营审批')
        page.locator('#acceptBtn').click();assert not state(page)['accepted']
        checks.append('改量后未覆盖需用须单独核对风险')
        page.locator('#taskQty').fill('8');page.locator('#acceptBtn').click()
        s=state(page);assert s['accepted'] and s['stock']==12 and s['pending']==8
        page.evaluate('acceptAdjustment()');assert state(page)['stock']==12
        page.screenshot(path=str(CAP/'03_采纳只改原待办.png'),full_page=True)
        checks.append('采纳调整原待办，新增0；在手仍12；重复采纳不加库存')
        page.locator('#completeBtn').click()
        s=state(page);assert s['stock']==11 and s['pending']==0 and s['actualQuantity']==8
        assert page.locator('#completeBtn').is_disabled()
        page.evaluate('recordCompletion()');assert state(page)['stock']==11
        page.screenshot(path=str(CAP/'04_实际完成与模拟订单.png'),full_page=True)
        page.locator('#followBtn').click();s=state(page)
        assert s['stock']==0 and s['endBacklog']==0 and s['observedLate']==0
        checks.append('先回放2分钟5份和5分钟4份履约，再入库8；重复完成无重复入库；20分钟全部覆盖')
        page.screenshot(path=str(CAP/'05_跟踪回看.png'),full_page=True)
        (CAP/'已完成回放状态.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
        page.locator('#delayBtn').click();page.locator('#verified').check();page.locator('#reason').fill('课堂少完成测试')
        page.locator('#acceptBtn').click();page.locator('#actualQty').fill('6');page.locator('#completeBtn').click()
        assert state(page)['pending']==2 and page.locator('#followBtn').is_disabled()
        assert '待核实' in page.locator('#status').inner_text()
        checks.append('实际只完成6时保留剩余2与待核实状态，不关闭风险')
        page.locator('#missingBtn').click()
        assert page.locator('#actionForm').is_hidden() and page.locator('#completeBtn').is_disabled()
        assert page.evaluate('simulate(S.case,8,8).quantity') is None
        page.screenshot(path=str(CAP/'06_缺规则阻断.png'),full_page=True)
        page.locator('#ruleSource').fill('课堂提供的模拟制作规则')
        page.locator('#restoreRule').click();assert state(page)['case']['prep_minutes'] is None
        page.locator('#role').select_option('manager');page.locator('#restoreRule').click()
        assert state(page)['case']['prep_minutes']==4 and not state(page)['accepted'] and state(page)['stock']==12
        checks.append('缺制作时间保留已知风险且阻断调整；演示店长补规则后不自动采纳')
        with page.expect_download() as download:
            page.get_by_role('button',name='导出本轮留痕').click()
        download.value.save_as(str(CAP/'实际导出留痕.json'))
        exported=json.loads((CAP/'实际导出留痕.json').read_text(encoding='utf-8'))
        assert exported['kind']=='classroom_operator_demo'
        checks.append('留痕JSON可实际下载，操作者记录与用户真实核对分开')
        mobile=browser.new_context(viewport={"width":390,"height":844},device_scale_factor=1)
        mp=mobile.new_page();mp.goto(URL);mp.wait_for_load_state('networkidle')
        mp.locator('#delayBtn').click();assert mp.evaluate('document.documentElement.scrollWidth<=innerWidth')
        mp.screenshot(path=str(CAP/'07_手机宽度.png'),full_page=True);mobile.close()
        checks.append('390px宽度无水平溢出')
        assert not errors,errors
        context.close()
        # A real recording of browser actions; the wait budget totals 30 seconds.
        video_context=browser.new_context(viewport={"width":1280,"height":960},record_video_dir=str(CAP/'video'),record_video_size={"width":1280,"height":960})
        vp=video_context.new_page();vp.goto(URL);vp.wait_for_load_state('networkidle');start=time.monotonic()
        def until(seconds):
            left=start+seconds-time.monotonic()
            if left>0:vp.wait_for_timeout(left*1000)
        until(6);vp.locator('#delayBtn').click()
        until(14);vp.locator('#verified').check();vp.locator('#reason').fill('录屏演示：课堂核实后调整原待办，新增0')
        until(18);vp.locator('#acceptBtn').click()
        until(23);vp.locator('#missingBtn').click()
        until(30);video=vp.video;video_context.close();video_path=video.path()
        browser.close()
    report={"url":URL,"checks":checks,"page_errors":errors,"passed":True,"video":video_path,
            "video_note":"实际Playwright浏览器操作录屏，约30秒，无音轨；不是生成视频", "source":"测试操作均为演示操作者，不新增傅浩诚的真实经营决定"}
    (WORK/'ui_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
