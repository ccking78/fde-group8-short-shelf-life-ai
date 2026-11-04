"""Create a separate submission-ready edition; retain historical evidence."""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.opc.constants import RELATIONSHIP_TYPE as RT

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "coursework-20261103"))
import build_docs as style

OLD = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103")
OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务提交准备版_20261103")
WORK = Path(r"F:\ChatGPT\work\FDE_数据补全与提交准备_20261103")
DATA = OUT / "附件_规范数据"

REPLACE = {
    "2026年11月3日优化版": "2026年11月3日提交准备版",
    "本轮只用1店1商品和1条延迟事件，正式增量规范等待后续安排。": "演示保留1店1商品与1条延期；补全和事件格式按课堂契约v1核验。",
    "正式增量规范和扩充等待用户指挥。": "补全采用课堂契约v1，批量扩展待安排。",
    "正式增量规范和扩充待用户指挥。": "补全采用课堂契约v1，批量扩展待安排。",
    "不制定正式增量规范或批量扩展。": "补全与事件按课堂契约v1，暂不批量扩展。",
    "没有批量扩展订单或制定正式增量标准。": "补全与事件按课堂契约v1核验，未批量扩展订单。",
    "正式增量规范等待后续安排。": "补全与事件格式按课堂契约v1核验。",
    "正式增量规范与批量扩充等待用户后续指挥。": "本课堂数据契约v1已核验，生产字段和批量扩展待后续指挥。",
    "正式字段标准、批量数据与其他异常情景等待用户后续指挥。": "本课堂数据契约v1已核验；生产字段、批量数据和新情景待后续指挥。",
    "正式增量规范和扩充等待用户后续指挥。": "课堂数据契约v1已核验，生产增量与批量扩展待后续指挥。",
    "正式增量事件结构、批量扩展和新异常情景均待用户指挥。": "本课堂事件结构已固定为v1；生产增量、批量扩展和新异常情景仍待用户指挥。",
    "正式增量规范与扩充等待用户指挥": "本课堂契约v1已核验，生产字段与批量扩充待安排",
    "动作产生的课堂留痕不构成正式增量规范。": "动作产生的课堂留痕与本次唯一外部模拟事件分别记录。",
    "本轮15次调用": "此前15次调用",
    "本次真实查证": "此前真实查证",
    "真实AI查证与人工核对": "历史AI查证与人工核对",
    "本轮当前对话AI真实调用15次工具。": "此前对话AI真实调用15次工具，本次补全未重新进行AI盲测。",
    "本轮未部署或提交学习台。": "此版本为提交准备稿，未部署。",
    "本轮没有企业试点、真实经营收益或学习台提交。": "本轮没有企业试点或实测经营收益，此版本为提交准备稿。",
}


def replace_text(text):
    for before, after in REPLACE.items():
        text = text.replace(before, after)
    return text


def paragraphs(doc):
    yield from doc.paragraphs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


def revise_docx(path):
    doc = Document(path)
    changed = 0
    for para in paragraphs(doc):
        before = para.text
        after = replace_text(before)
        if before == after:
            continue
        # These local replacements are within a single prose run in the originals.
        if any(k in run.text for run in para.runs for k in REPLACE):
            for run in para.runs:
                run.text = replace_text(run.text)
        else:
            first = para.runs[0]
            first.text = after
            for run in para.runs[1:]:run.text = ""
        changed += 1
    doc.core_properties.subject = "第8组提交准备版 数据契约v1"
    doc.save(path)
    return {"file": path.name, "paragraphs_locally_updated": changed}


def appendix(report):
    d = style.newdoc()
    d.core_properties.title = "第8组 数据补全规范与核验说明"
    style.title(d, "数据补全规范与核验说明", "第8组　傅浩诚 李启顺　2026年11月3日　课堂数据契约 v1.0.0")
    style.p(d, "我们已用数据质量与SimPy技能补全现有公开样本的可核验字段，并建立课堂事件契约。119条真实记录保留原值和来源，其中52条精确匹配菜单，67条未匹配并保留空值。本说明随周六实操、周一边界和周二D1一并准备提交。")
    style.h(d, "本次补全的范围")
    style.table(d, ["处理对象", "做法与结果"], [
        ["原始真实记录", "仅复用Scrapling采集的E1、E3各4MiB前缀和完整E4菜单。三份源文件SHA256与采集记录一致。"],
        ["可补字段", "按Receipt_ID和Inv_Num精确关联；补菜单类别、子类及菜单源行号，解析数量与布尔值，规范当地时间，派生小时与星期。"],
        ["不能补成事实的字段", "时区、厨房完成、顾客需用时点、库存、制作时长、产能、可售规则均为null。菜单缺配67条不猜测、不删除。"],
        ["小规模模拟", "保持1店1SKU与既有课堂假设，只封装1条延期事件。没有生成新模拟订单；缺制作时长测试副本继续为空。"],
        ["可追溯与可复算", f"{report['coverage']['lineage_fields']}个字段来源项；{report['coverage']['null_cells_explained']}个空值有原因。选列与派生可离线重算；原始大文件哈希在构建时核验。"],
    ], [1.12, 5.98], 10.5)
    style.h(d, "事实和课堂假设分别记录")
    style.p(d, "源商品1023 MINI TUNA来自公开交易；模拟店SIM-01和迷你三明治A是课堂映射。在手12、预留5、可分配7，原8份任务和第4、第12、第8分钟完成，以及4分钟制作时长、产能8、可售时长均为课堂假设。公开规范不提供这些经营参数。", 10.5)
    style.p(d, "两个前缀不是连续交易。字段补全不增加样本的时间覆盖，不能估真实高峰强度。交易结束不是厨房完成，迟供不是损失销量，可售截止排除不是实际报废。", 10.5)
    style.title(d, "规范应用与运行核验", "参考公开技术规范　课堂数据契约不等于生产制度或标准认证")
    d.paragraphs[-2].paragraph_format.page_break_before = True
    style.table(d, ["规范依据", "本次实现"], [
        ["W3C DWBP", "参考BP4至8、22、28、31、34至35：许可、来源、质量、版本历史、缺失原因、覆盖限制与衍生规则。"],
        ["JSON Schema 2020 12", "四份schema约束字段、类型、空值和额外字段。jsonschema 4.25.1实际验证，显式检查日历日期、当地时间和UTC登记时间。"],
        ["RFC 3339", "系统登记时间用带Z的UTC时间。源交易保留当地钟表值且时区未知，不假造UTC；模拟相对分钟不转成实际日期。"],
        ["CloudEvents v1.0.2", "封装id、source、specversion为1.0和type；source与id组合去重。同身份不同内容拒绝；版本与前值同时核验后再写入。只有相对分钟，省略time。"],
    ], [1.45, 5.65], 10.5)
    style.h(d, "业务核验与人工记录")
    style.p(d, "正常迟供0；原任务延期至第12分钟时，第10分钟有1份迟供，第12分钟补供。缺制作时长时保留风险提示，可采纳调整量为空。课堂产能假设下可将原8份任务调整至第8分钟完成，额外新增0；投影不写入实际库存。", 10.5)
    style.p(d, "沿用傅浩诚真实答复“核对无误，课堂模拟采纳调整原待办”。本次未新增人工审批，实际完成未登记。此前15次AI工具查证作为历史证据保留，未宣称对本次补全重新盲测。", 10.5)
    style.h(d, "复算与来源")
    style.p(d, "附件规范数据包含输入、逐字段来源、数据字典、schema、运行结果、固定依赖和重放脚本。验收答案单独存放，不进入智能体输入目录。已通过16项运行核验和37项单元测试。", 10)
    links=style.p(d,"规范原文  ",9)
    for label,url in [
        ("W3C DWBP", "https://www.w3.org/TR/dwbp/"),
        ("JSON Schema", "https://json-schema.org/draft/2020-12/json-schema-validation"),
        ("RFC 3339", "https://www.rfc-editor.org/rfc/rfc3339"),
        ("CloudEvents", "https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md"),
    ]:
        link=OxmlElement("w:hyperlink");link.set(qn("r:id"),d.part.relate_to(url,RT.HYPERLINK,is_external=True))
        run=OxmlElement("w:r");prop=OxmlElement("w:rPr")
        size=OxmlElement("w:sz");size.set(qn("w:val"),"18");prop.append(size)
        color=OxmlElement("w:color");color.set(qn("w:val"),"146654");prop.append(color);run.append(prop)
        text=OxmlElement("w:t");text.text=label;run.append(text);link.append(run);links._p.append(link)
        links.add_run("    ")
    style.p(d,"公开数据  Cazier, Spaulding, Hassler (2025), Sandwich Analytics, Mendeley Data V1，DOI 10.17632/9hntk3wbwc.1，CC BY 4.0。",9)
    footer = d.sections[0].footer.paragraphs[0]
    style.font(footer.add_run("第8组　课堂模拟　"), 9)
    field=OxmlElement("w:fldSimple");field.set(qn("w:instr"),"PAGE");footer._p.append(field)
    d.save(OUT / "04_数据补全规范与核验说明.docx")


def supporting_files(report):
    inputs = DATA / "01_输入_可供智能体"
    source = json.loads((inputs / "来源许可与版本.json").read_text(encoding="utf-8"))
    dictionary = ["# 数据字典与补全规则", "", "本文件描述课堂契约v1.0.0，不提供未观测经营参数。记录中的null必须有missing_reasons，不能解释为0。", "", "## 真实记录", "", "|字段组|内容|来源与处理|", "|---|---|---|"]
    dictionary += [
        "|observed|receipt_id store_id date start_time end_time item_id quantity_raw return_raw drive_thru_raw|保留E1/E3原值，见必要选列证据与逐字段来源|",
        "|menu|matched item_name category_id category_name subcategory_id subcategory_name|按Inv_Num匹配E4；未匹配时5个描述字段null并注明原因|",
        "|derived|quantity is_return drive_thru start_local_time end_local_time start_hour weekday_iso|数量与布尔解析；当地时间格式化；日期派生。不是厨房或顾客履约时间|",
        "|unknown|source_timezone kitchen_completed_at service_due_at actual_on_hand actual_prep_minutes actual_capacity_per_batch actual_sellable_minutes|全部保留null。公开文件无相应观测，不用课堂假设替代|",
        "|missing_reasons|JSON Pointer到code和reason的映射|每个null一一对应；not_in_source或no_menu_match|",
        "|record_id evidence_id contract_version|源记录身份、选列引用和版本|E3数据行序号稳定生成；不是模拟订单ID|",
        "", "## 课堂快照", "", "state保持已确认课堂切片；field_origins逐叶登记。只有source_item_id引用真实商品，其他状态、映射和规则均为课堂假设。相对分钟从课堂窗口0起算，单位为份与分钟。", "",
        "## 模拟增量", "", "唯一活动事件见05文件，CloudEvents结构化JSON。source+id是事件身份，主体TASK-8，data包含前值4、后值12、前版本0、后版本1。event_minute与recorded_minute为相对分钟1；未填写绝对time。规则为本课堂契约；不扩充事件种类。", "",
        "同source+id同内容忽略；同source+id不同内容拒绝；不同来源同id不当作重复，但不在本切片登记的来源不能写入。新事件须通过字段、实体引用、时间顺序、版本、前值及快照约束，全部成功才提交。", "",
        "## 缺规则测试", "", "06为故意缺制作时长的测试覆写，作用于事件后版本1，不是新业务增量。只把prep_minutes改为null；不能因补全动作将它恢复为4。", "",
        "## 来源与规范", "",
    ]
    dictionary += [f"- [{s['title']}]({s['url']})：{s['implementation']}" for s in source["standards"]]
    (DATA / "数据字典与补全规则.md").write_text("\n".join(dictionary)+"\n", encoding="utf-8")
    rules = """# 数据质量与适用范围

完整性：所有契约字段存在；1168个空值明确原因。这不表示真实经营信息已经完整。
唯一性：真实record_id与evidence_id唯一；收据和菜单关联主键无重复；事件按source与id组合去重。
有效性：JSON Schema 2020-12验证，应用显式检查日期、时间、有限正数量、引用和来源类型。
准确性：仅验证选列对原采集文件一致、衍生可重算；不能据此证明源企业记录无误。
一致性：快照、版本、前值、时序、数量守恒，以及缺规则阻断均核验。
时效性：保留历史交易日期与新的系统处理时刻，不把2004至2011等历史记录说成当前门店数据。

原始E1/E3仅4MiB前缀，E4完整；去掉截断尾行。119条是采集前缀内能关联、数量为正且非退货的商品记录；52条匹配菜单、67条未匹配保留。这不是随机样本或连续交易，不外推高峰强度。

补全策略只允许源值精确关联、确定性解析和明确标识的既有课堂假设。没有采用均值、前向填充、模型猜测或相似名称模糊匹配去填真实经营字段。

使用已安装data-quality-frameworks与SimPy技能；Scrapling只用于此前真实源文件采集，本次无新增爬取。质量检查使用jsonschema与本地业务校验，不声称运行Great Expectations或dbt。SimPy模型最多32个业务事件、256调度步，包含第20分钟；同刻先截止排除、再投影供给、再模拟需用。本轮确定性输入不随机抽样、不拟合分布，不报告置信区间或企业收益。

SimPy技能参考：Kassis, T.; Agarwal, V.; He, Y.; Patel, D.; Brueckner, A. M. (2026). Scientific Agent Skills A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065 。该论文不是本项目效果验证。
"""
    (DATA / "质量与适用范围.md").write_text(rules, encoding="utf-8")
    replay = """# 离线重放

本包运行输入在01目录，运行结果和验收答案在02目录。仅把01目录交给智能体查证。data_pipeline.py只复用其已验证的SimPy计算函数；旧build/replay命令属于历史管线，当前入口是data_completion.py。

当前Windows CPython 3.12独立环境已安装SimPy 4.1.2与jsonschema 4.25.1。其他同架构Windows CPython 3.12环境可从本包离线依赖安装：

```powershell
python -m pip install --no-index --find-links .\\离线依赖 --require-hashes -r .\\requirements.lock
python -B data_completion.py replay --inputs .\\01_输入_可供智能体 --output .\\重放结果
python -B -m unittest test_data_completion test_data_pipeline -v
```

本机环境可用 F:\\ChatGPT\\work\\runtimes\\fde-data-simulation\\.venv\\Scripts\\python.exe 替代python。replay只写新结果，不改变输入；跨机器可核对JSON结果和输入摘要。重新build需要本机Scrapling原始下载及上一版小样例包，不能用离线选列伪称重新采集。

rpds_py离线wheel适用于Windows x64 CPython3.12。其他平台需要按固定版本获取适配wheel并记录新hash。输入记录不含API密钥、员工姓名或联系方式。
"""
    (DATA / "重放说明.md").write_text(replay, encoding="utf-8")
    deps = []
    for folder in [Path(r"F:\ChatGPT\downloads\FDE_数据管线依赖_20261103"), Path(r"F:\ChatGPT\downloads\FDE_数据补全依赖_20261103")]:
        for wheel in sorted(folder.glob("*.whl")):
            target = DATA / "离线依赖" / wheel.name;target.parent.mkdir(exist_ok=True)
            shutil.copy2(wheel, target)
            name, version = wheel.name.split("-")[:2]
            deps.append({"name": name, "version": version, "wheel": wheel.name, "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()})
    (DATA / "requirements.lock").write_text("".join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}\n" for r in deps), encoding="utf-8")
    (DATA / "依赖与技能记录.json").write_text(json.dumps({"dependencies": deps,
        "runtime": report["runtime"], "skills": ["scrapling-official", "data-quality-frameworks", "simpy"],
        "new_skill_installations_this_round": 0, "quality_engine": "jsonschema and local domain constraints"}, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(Path(r"F:\ChatGPT\work\FDE_数据管线小样例_20261103\skill_installation_manifest.json"), DATA / "skill_installation_manifest.json")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    changes = []
    for source in OLD.iterdir():
        if source.name in ("文件校验_SHA256.txt", "交付验证记录.json"):
            dest = OUT / "历史版本核验" / source.name
        else:dest = OUT / source.name
        if source.is_dir():shutil.copytree(source, dest, dirs_exist_ok=True)
        else:dest.parent.mkdir(parents=True, exist_ok=True);shutil.copy2(source, dest)
    for path in sorted(OUT.glob("*.docx")):
        changes.append(revise_docx(path))
    for filename in ["可编辑作业正文.md", "本轮设计调整说明.md"]:
        target = OUT / filename
        target.write_text(replace_text(target.read_text(encoding="utf-8")) + "\n\n## 本次数据补全\n\n现按课堂数据契约v1补全119条真实记录，52条匹配菜单，67条保留缺失原因；演示仍使用1条源记录映射、1店1商品、1条模拟延期。源数据没有的经营字段保留null，模拟假设单列。见04数据补全说明及附件规范数据。此前AI工具查证与人工核对作为历史记录保留，未新建审批或实际完成。\n", encoding="utf-8")
    demo = OUT / "00_打开经营异常课堂演示.html"
    text = replace_text(demo.read_text(encoding="utf-8"))
    text = text.replace("<footer>", '<p class="small"><a href="附件_规范数据/00_打开数据补全报告.html">查看本次数据补全与规范核验</a></p><footer>', 1)
    demo.write_text(text, encoding="utf-8")
    report = json.loads((DATA / "02_运行与验收_不作为AI输入" / "数据补全与运行核验.json").read_text(encoding="utf-8"))
    appendix(report)
    supporting_files(report)
    (OUT / "先读_使用与提交说明.txt").write_text("""第8组三项任务提交准备版

周六：01一页六格、01b运行报告，以及附件中的提示词、AI历史查证、实际录屏与可运行HTML。
周一：02 AI任务边界与人工确认。
周二：03 D1任务清单与人工确认表。
本次补充：04 数据补全规范与核验说明；附件规范数据为当前可复算的数据契约v1。

先打开00_打开经营异常课堂演示.html；点击数据补全链接可逐条查看119条真实记录的来源、菜单关联和未知字段。HTML无需联网、无需密钥；AI结果为此前真实查证记录回放，不在线调用模型。

附件数据与来源、AI查证与录屏保留此前证据，原始内容不重新标为本次完成。历史版本核验目录只描述旧版本；当前校验见根目录交付验证记录和文件校验。

当前规范输入只在附件规范数据/01_输入_可供智能体。02运行与验收不作为AI输入。未知门店经营字段仍为null；课堂快照另有明确的模拟规则。生产增量规范、批量订单和新情景继续听后续安排。

原人工答复保持“核对无误，课堂模拟采纳调整原待办”；实际完成尚未登记。此次没有新增人工审批或企业效果证明。

上传准备：第3周D1一次提交4份主要PDF与本完整ZIP，共5附件，每份小于20MB；04补全说明在ZIP中。按群通知周六材料随D1提交。当前未上传、未暂存草稿、未生成回执。
""", encoding="utf-8")
    draft = """已准备第8组周六智能体初步搭建、周一AI任务边界与周二D1任务清单和人工确认表。主案例为AI经营异常提醒：发现已有备餐任务延期时，查进度、规则和供需时点，比较调整原任务并由制作岗位确认；正常已有计划不重复制作，缺制作时长时阻断可采纳调整。

数据仅复用Scrapling真实采集文件。已补全119条正数量非退货关联记录，其中52条匹配菜单，67条保留缺失原因。真实经营未知字段保留null；课堂模拟仅1店1商品和1条延期事件。字段来源、缺失解释、JSON Schema校验、CloudEvents事件及固定依赖随包提供，37项单测与16项运行核验通过。

附件包含一页六格、实操运行报告、AI边界、12步任务清单与8个人工确认点、数据补全说明、离线演示、此前真实AI查证和30秒录屏。AI调用为历史记录回放；本次未重新盲测。已保留傅浩诚“核对无误，课堂模拟采纳调整原待办”的真实课堂核对；实际完成未登记。完整在线AI、服务端权限与企业效果仍待开发验证。

按成果模块安排分工：傅浩诚牵头方案整合、数据来源与补全规范、可运行演示和课堂人工核对；李启顺牵头业务流程、AI任务边界、D1任务清单与人工确认表梳理；两人共同负责最终复核与汇报。对应材料已准备，材料整理、字段处理和程序核验由AI辅助完成。傅浩诚的课堂人工核对已有原话记录。
"""
    (WORK / "上传完成情况草稿.txt").write_text(draft, encoding="utf-8")
    checklist = """# 上传准备清单

目标：[学习台第3周D1](https://ai-native-talent-academy.coolai.tech/)。账号为傅浩诚，第8组；周六材料按群通知随本次D1提交。当前状态未提交。

## 计划上传的5个附件

1. 01_周六实操_一页六格说明.pdf
2. 01b_周六实操_运行报告与展示说明.pdf
3. 02_周一_AI任务边界.pdf
4. 03_周二_D1任务清单与人工确认表.pdf
5. 本完整提交准备版ZIP（内含04补全说明、可运行演示、规范数据、来源与历史证据）

平台限制：最多5个，每个不超过20MB，支持PDF与ZIP。未选文件、未暂存、未提交。

## 提交前最后确认

用户确认准备版与上传动作。分工已按用户授权的合理安排写入完成情况草稿：傅浩诚牵头方案、数据与演示，李启顺牵头流程、边界与人工确认表；两人共同负责最终复核与汇报，注明AI辅助整理和核验。上传后必须核对已提交版本和回执再报告成功。
"""
    (OUT / "00_上传准备清单.md").write_text(checklist, encoding="utf-8")
    (WORK / "文档局部修订记录.json").write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(OUT), "docx_files": len(list(OUT.glob('*.docx'))), "changes": changes}, ensure_ascii=False, indent=2))


if __name__ == "__main__":main()
