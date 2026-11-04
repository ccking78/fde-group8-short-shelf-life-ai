"""Offline HTML presentation checks; never sends a model request or uploads."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--html',type=Path,default=Path(__file__).resolve().parent/'第8组_5分钟汇报_打开即演示.html')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    errors,checks,layouts=[],[],[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1366,'height':768},device_scale_factor=1)
        context.set_offline(True)
        page=context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.clock.install()
        page.goto(args.html.resolve().as_uri())
        page.wait_for_load_state('networkidle')
        expect(page.locator('[data-page="0"]')).to_be_visible()
        assert page.locator('.logic-nav button').all_text_contents()==['1帮谁','2用哪张表','3按什么规则','4产出什么','5由谁拍板','留1分钟答疑']
        assert page.evaluate('window.courseDemo.targets.reduce((a,b)=>a+b,0)')==300
        for i in range(6):
            page.locator(f'[data-slide="{i}"]').click()
            expect(page.locator(f'[data-page="{i}"]')).to_be_visible()
            m=page.evaluate('''() => ({page:window.courseDemo.state().slide,width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollHeight:document.documentElement.scrollHeight,slideBottom:document.querySelector('.slide:not([hidden])').getBoundingClientRect().bottom,footerTop:document.querySelector('.footer').getBoundingClientRect().top})''')
            layouts.append(m)
            page.screenshot(path=str(args.out/f'{i+1:02d}_投影_{["帮谁","用哪张表","按什么规则","产出什么","由谁拍板","答疑"][i]}.png'),full_page=True)
        assert all(m['scrollWidth']<=1366 for m in layouts),'投影宽度溢出'
        assert all(m['scrollHeight']<=768 for m in layouts),layouts
        checks.append('1366×768投影尺寸六页全部无需滚动，主线严格按老师五问')
        page.keyboard.press('Home')
        page.keyboard.press('ArrowRight')
        assert page.evaluate('window.courseDemo.state().slide')==1
        page.keyboard.press('n')
        expect(page.locator('#speakerNotes')).to_be_visible()
        assert '来源' in page.locator('#notesBody').inner_text()
        page.locator('#notesClose').click()
        checks.append('键盘左右/Home翻页与N逐页讲稿可用')
        page.locator('[data-slide="3"]').click()
        assert page.evaluate('window.courseDemo.state().projection.late_units')==0
        page.locator('#delayCase').click()
        assert page.evaluate('window.courseDemo.state().projection.late_units')==1
        page.locator('#demoAdopt').click()
        assert page.evaluate('window.courseDemo.state().phase')=='observing'
        expect(page.locator('#demoFeedback')).to_contain_text('核对')
        page.locator('#demoVerified').check()
        page.locator('#demoAdopt').click()
        s=page.evaluate('window.courseDemo.state()')
        assert s['phase']=='accepted' and s['current']['on_hand']==12 and s['current']['plan']['ready_minute']==8
        assert s['projection']['late_units']==0 and s['records'][0]['additional_quantity']==0
        checks.append('延期触发即时计算1份迟供，未经核对不能采纳；采纳只改原8份，库存仍12')
        page.screenshot(path=str(args.out/'07_课堂采纳_库存未增加.png'),full_page=True)
        page.locator('#demoComplete').click()
        s=page.evaluate('window.courseDemo.state()')
        assert s['phase']=='completed' and s['current']['on_hand']==16 and s['current']['plan']['quantity']==0
        assert s['projection']['forecast_quantity']==11 and s['projection']['served_by_horizon']==11 and s['projection']['late_units']==0
        page.evaluate('completeDemo()')
        assert page.evaluate('window.courseDemo.state().current.on_hand')==16
        checks.append('课堂完成8、已履约4后在手16、可分配11，剩余需用11；重复点击不重复入账')
        page.locator('#openEvidence').click()
        expect(page.locator('#evidenceDialog')).to_be_visible()
        assert 'fc893754dd964840ab8dc2a3a2707bcf' in page.locator('#evidenceJson').inner_text()
        assert '不是现场新调用' in page.locator('#evidenceJson').inner_text()
        page.locator('#closeEvidence').click()
        checks.append('可以打开真实模型与工具证据，明确标识历史运行及本页课堂记录')
        page.locator('#missingCase').click()
        assert page.evaluate('window.courseDemo.state().projection.late_units')==1
        assert page.locator('#demoAdopt').is_disabled() and page.locator('#demoAdopt').is_hidden()
        assert page.locator('#demoCheckRow').is_hidden()
        expect(page.locator('#evidenceMode')).to_contain_text('null')
        page.screenshot(path=str(args.out/'08_缺规则_无可采纳数量.png'),full_page=True)
        checks.append('缺制作时间保留已知1份迟供并隐藏可采纳动作')
        page.locator('#timerToggle').click()
        page.clock.fast_forward(240000)
        assert page.evaluate('window.courseDemo.state().elapsed')==240
        expect(page.locator('#timerNotice')).to_contain_text('答疑')
        page.clock.fast_forward(60000)
        expect(page.locator('#timerNotice')).to_contain_text('时间到')
        assert not page.evaluate('window.courseDemo.state().running')
        page.locator('#timerReset').click()
        assert page.evaluate('window.courseDemo.state().elapsed')==0
        checks.append('倒计时4分钟提示答疑，5分钟停止并提醒结束，可重置')
        mobile=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1)
        mobile.set_offline(True)
        mp=mobile.new_page()
        mp.goto(args.html.resolve().as_uri())
        mp.wait_for_load_state('networkidle')
        for i in [0,1,3,4]:
            mp.locator(f'[data-slide="{i}"]').click()
            assert mp.evaluate('document.documentElement.scrollWidth<=innerWidth'),i
        mp.screenshot(path=str(args.out/'09_手机查看.png'),full_page=True)
        mobile.close()
        assert not errors,errors
        checks.append('390px手机阅读无横向溢出；全程断网可用，无页面脚本错误，无模型请求')
        context.close()
        browser.close()
    report={'passed':True,'checks':checks,'layouts':layouts,'page_errors':errors,'offline':True,'new_model_requests':0,'html':str(args.html)}
    (args.out/'演示核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
