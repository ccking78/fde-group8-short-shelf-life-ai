import hashlib
import json
import shutil
import zipfile
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=Path(r'F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103')
WORK=Path(r'F:\ChatGPT\work\FDE_经营异常优化_20261103')
DOWNLOADS=Path(r'F:\ChatGPT\downloads\FDE_经营异常优化_20261103')


def main():
    qa=json.loads((WORK/'document_render_qa.json').read_text(encoding='utf-8'))
    assert [x['pages'] for x in qa]==[1,3,2,4]
    for doc in qa:
        doc['visual_review']='passed_current_ai_viewed_every_page'
    (WORK/'document_render_qa.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    ui=json.loads((WORK/'ui_verification.json').read_text(encoding='utf-8'))
    assert ui['passed'] and not ui['page_errors']
    source=json.loads((OUT/'附件_数据与来源'/'数据清单.json').read_text(encoding='utf-8'))
    assert source['simulated_increment_rows']==1
    cases=json.loads((OUT/'附件_数据与来源'/'04_模拟情景.json').read_text(encoding='utf-8'))
    assert len(cases)==3
    normal,delay,missing=cases
    copy_delay=json.loads(json.dumps(delay));copy_missing=json.loads(json.dumps(missing))
    # Only the missing rule changes business inputs in the missing-information copy.
    for c in [copy_delay,copy_missing]:
        for k in ['id','name','description','snapshot_version','events']:
            c.pop(k,None)
    copy_missing['prep_minutes']=4
    assert copy_delay==copy_missing
    show=OUT/'附件_展示与实际检查';show.mkdir(exist_ok=True)
    for path in (WORK/'capture').glob('*'):
        if path.is_file():shutil.copy2(path,show/path.name)
    shutil.copy2(Path(ui['video']),show/'30秒真实浏览器操作.webm')
    shutil.copy2(WORK/'ui_verification.json',show/'浏览器检查记录.json')
    code=OUT/'附件_本轮源文件';code.mkdir(exist_ok=True)
    for path in ROOT.iterdir():
        if path.is_file():shutil.copy2(path,code/path.name)
    # Include the exact style helper used by the revised document builder.
    style_folder=code.parent/'coursework-20261103';style_folder.mkdir(exist_ok=True)
    shutil.copy2(ROOT.parent/'coursework-20261103'/'build_docs.py',style_folder/'build_docs.py')
    shutil.copy2(ROOT/'任务正文.md',OUT/'可编辑作业正文.md')
    shutil.copy2(ROOT/'开发设计补充.md',OUT/'本轮设计调整说明.md')
    data=OUT/'附件_数据与来源'
    shutil.copy2(DOWNLOADS/'acquisition_log.jsonl',data/'Scrapling采集日志.jsonl')
    (data/'来源与模拟说明.md').write_text('''# 数据来源与本轮小样例

公开来源：[Sandwich Analytics](https://data.mendeley.com/datasets/9hntk3wbwc/1)。署名：Cazier, Joseph; Spaulding, Trent; Hassler, Edgar (2025), Mendeley Data V1, DOI 10.17632/9hntk3wbwc.1。[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。本项目选列、精确关联、商品映射和模拟字段属于改动，不表示作者或源门店认可本项目。

本轮所有外部数据采集均用Scrapling。E1、E3各取4MiB前缀，删除截断尾行；E4完整下载且发布方SHA256一致。原始响应存于本机F盘downloads，交付包包含必要选列、源行号、采集范围和哈希。未导出员工姓名和收款字段。

公开数据历史覆盖较早，前缀记录分散，不构成连续交易；可关联正数量非退货行仅119条。不能用本样本估目标门店高峰强度、等待时长、厨房产能或报废。交易起止不是厨房完成或顾客等待。

仅商品名与源交易字段来自公开数据；演示店、SKU映射、当前数量、5个历史窗口、4个需用时点、待办、制作和可售规则均为模拟。源门店是否预制成品未知。时间规则不是门店真实规则或通用安全标准。

本轮仅1店1SKU、1条延迟增量（预计完成4改12）；正常作为对照，缺制作时间为删字段副本。没有批量新增订单。动作产生的课堂留痕不构成正式增量规范。正式字段标准、批量数据与其他异常情景等待用户后续指挥。

01是原始商品行必要选列，02是精确关联后的可用选列，03是菜单选列，04是小型模拟输入，05是唯一增量样例，06是模拟历史窗口，07是字段来源表。数据清单与采集日志列出原始响应范围、文件大小和SHA256。
''',encoding='utf-8')
    (OUT/'先读_使用与提交说明.txt').write_text('''第8组三项任务优化版

一、先打开演示
双击 00_打开经营异常课堂演示.html，在普通浏览器中运行；无需安装、联网或API密钥。也可从本机演示服务打开。页面是本地程序与真实AI查证回放，不是在线模型。

二、三项任务对应文件
周六：01 一页六格 + 01b 运行报告 + 提示词与AI记录 + 30秒实际录屏。
周一：02 AI任务边界。
周二：03 D1任务清单与人工确认表，12步、8个确认点。
Word为可编辑稿，PDF为已检查的排版稿，共10页。

三、展示顺序
正常计划→注入唯一制作延迟→核实进度与产能→调整原8份待办，额外新增0，采纳不入库→缺制作规则阻断。
可追加演示实际完成和跟踪。实际完成按钮会先推进模拟时钟，回放第2分钟5份已有订单和第5分钟4份需用，再入库；因此第8分钟完成8份后，在手是11，不是20。这些均是明确标注的模拟事件。

四、已保存人工核对
傅浩诚：“核对无误，课堂模拟采纳调整原待办”。核对的是提问所列数字与处理摘要；课堂假设原任务未开工且可第8分钟完成。原任务8份、额外新增0；实际完成未登记。自动化演示操作另存为演示操作者，不冒充用户决定。

五、数据范围
外部采集只用Scrapling；公开样本不是连续交易，不用来估高峰强度。经营状态、历史窗口和规则按字段标为模拟。本轮只保留1店1SKU、1条延迟事件及缺字段副本。正式增量规范与批量扩充等待用户后续指挥。

六、证据边界
本轮当前对话AI真实调用15次工具。P2整理于运行后，当前会话有上下文，非独立提示词对照；不声称正确率提升。历史P0/P1原样保留，但与新版输入不同。
附件展示有真实浏览器录屏（约30秒、无音轨）、截图和检查记录；完整在线AI、服务端权限及企业收益待验证。本包未部署、未向学习台提交。

七、源文件
附件本轮源文件可用于在当前机器上继续开发。脚本使用本机F盘路径；文档样式依赖同包coursework-20261103/build_docs.py。HTML为单文件独立演示，其他脚本不是跨机器一键重建包。
''',encoding='utf-8')
    verification={
        'verified_at_utc':datetime.now(timezone.utc).isoformat(),
        'documents':[{'file':x['file'],'pages':x['pages'],'visual_review':x['visual_review']} for x in qa],
        'total_pdf_pages':sum(x['pages'] for x in qa),
        'rendering':'render_docx.py缺LibreOffice；隐藏原生Word导出PDF，再Poppler 120dpi逐页PNG检查',
        'ui_checks':ui['checks'],'ui_page_errors':ui['page_errors'],
        'simulation_scope':source['simulation_scope'],'simulated_increment_rows':1,
        'human_review':'用户真实课堂核对已保存；实际完成未登记；自动化操作另列',
        'ai':'15次当前对话真实工具调用；非独立盲测；P2未在运行前冻结',
        'learning_platform_submission':False,'deployment':False,'enterprise_effect_validated':False,
    }
    (OUT/'交付验证记录.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
    # Remove only these task-created discovery temp files; raw evidence remains.
    for name in ['mendeley.md','mendeley_loaded.md','authors.md']:
        path=WORK/name
        if path.exists():path.unlink()
    checksum=OUT/'文件校验_SHA256.txt'
    files=sorted(p for p in OUT.rglob('*') if p.is_file() and p!=checksum and '__pycache__' not in p.parts)
    checksum.write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(OUT).as_posix() for p in files)+'\n',encoding='utf-8')
    archive=OUT.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in files+[checksum]:z.write(path,path.relative_to(OUT).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(files)+1
    result={'output':str(OUT),'zip':str(archive),'files':len(files)+1,'zip_bytes':archive.stat().st_size,
            'zip_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'pdf_pages':verification['total_pdf_pages'],
            'ui_checks_passed':len(ui['checks']),'simulated_increment_rows':1}
    (WORK/'final_package_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
