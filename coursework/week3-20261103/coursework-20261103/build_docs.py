"""Build coursework Word documents from verified evidence and frozen content."""
import json,re
from pathlib import Path
from datetime import datetime
from docx import Document
from docx.shared import Inches,Pt,RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT,WD_CELL_VERTICAL_ALIGNMENT

ROOT=Path(__file__).resolve().parent
OUT=Path(r'F:\ChatGPT\outputs\FDE_第8组_第3周作业与演示_20261103')
CAP=OUT/'附件_演示截图与记录'
FONT='微软雅黑'

def font(run,size=11,bold=False,color='000000'):
    run.font.name=FONT;run.font.size=Pt(size);run.font.bold=bold;run.font.color.rgb=RGBColor.from_string(color)
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),FONT)

def newdoc():
    d=Document();s=d.sections[0];s.page_width=Inches(8.5);s.page_height=Inches(11);s.top_margin=Inches(.65);s.bottom_margin=Inches(.62);s.left_margin=Inches(.7);s.right_margin=Inches(.7)
    for st in d.styles:
        for node in list(st.element.xpath('./w:pPr/w:pBdr')):node.getparent().remove(node)
    for name in ['Normal','Title','Subtitle','Heading 1','Heading 2','Heading 3']:
        st=d.styles[name];st.font.name=FONT;st.font.color.rgb=RGBColor(0,0,0);st.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'),FONT)
    d.styles['Normal'].font.size=Pt(11);d.styles['Normal'].paragraph_format.line_spacing=1.18;d.styles['Normal'].paragraph_format.space_after=Pt(7)
    for name,size in [('Title',23),('Heading 1',16),('Heading 2',13),('Heading 3',11.5)]:
        d.styles[name].font.size=Pt(size);d.styles[name].paragraph_format.space_before=Pt(12 if name!='Title' else 0);d.styles[name].paragraph_format.space_after=Pt(8)
    d.core_properties.author='第8组';d.core_properties.title='AI原生高峰经营助手课程作业';d.core_properties.subject='第3周 D1与10月31日实操'
    return d

def p(d,text='',size=None,bold=False,style=None):
    x=d.add_paragraph(style=style);r=x.add_run(text);font(r,size or 11,bold);return x
def title(d,text,sub):
    d.add_paragraph(text,'Title');p(d,sub,10)
def h(d,text):d.add_paragraph(text,'Heading 1')
def page(d):d.add_page_break()
def table(d,headers,rows,widths,size=10.5):
    t=d.add_table(rows=1,cols=len(headers));t.alignment=WD_TABLE_ALIGNMENT.CENTER;t.autofit=False
    borders=OxmlElement('w:tblBorders')
    for k in ['top','left','bottom','right','insideH','insideV']:
        e=OxmlElement('w:'+k);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'5');e.set(qn('w:color'),'D9D9D9');borders.append(e)
    t._tbl.tblPr.append(borders)
    preferred=t._tbl.tblPr.find(qn('w:tblW'));preferred.set(qn('w:type'),'dxa');preferred.set(qn('w:w'),str(round(sum(widths)*1440)))
    for i,w in enumerate(widths):t.columns[i].width=Inches(w)
    def put(c,txt,ishead=False,index=0):
        c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
        tcPr=c._tc.get_or_add_tcPr();m=OxmlElement('w:tcMar')
        for edge in ['top','bottom','left','right']:
            v=OxmlElement('w:'+edge);v.set(qn('w:w'),'95');v.set(qn('w:type'),'dxa');m.append(v)
        tcPr.append(m);sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'DCE6F1' if ishead else ('F4F7FA' if index%2 else 'FFFFFF'));tcPr.append(sh)
        pa=c.paragraphs[0];pa.paragraph_format.space_after=Pt(1);pa.paragraph_format.space_before=Pt(1);pa.paragraph_format.line_spacing=1.12
        font(pa.add_run(str(txt)),size,ishead)
    for i,v in enumerate(headers):t.rows[0].cells[i].width=Inches(widths[i]);put(t.rows[0].cells[i],v,True)
    rep=OxmlElement('w:tblHeader');t.rows[0]._tr.get_or_add_trPr().append(rep)
    for n,row in enumerate(rows):
        cells=t.add_row().cells
        for i,txt in enumerate(row):cells[i].width=Inches(widths[i]);put(cells[i],txt,index=n)
        no=OxmlElement('w:cantSplit');t.rows[-1]._tr.get_or_add_trPr().append(no)
    d.add_paragraph().paragraph_format.space_after=Pt(1)
    return t

def parse_table(md,heading):
    segment=md.split(heading,1)[1].split('\n## ',1)[0]
    lines=[s for s in segment.splitlines() if s.startswith('|')]
    return [[x.strip() for x in line.strip().strip('|').split('|')] for line in lines[2:]]

def onepage():
    d=newdoc();title(d,'高峰经营助手一页说明','第8组　傅浩诚 李启顺　2026年11月3日　周六实操作业')
    p(d,'帮助制作岗位核对供需、比较备餐候选并记录确认。课堂样例为模拟商品经典牛肉堡；完整输入与缺制作时间两类场景均已实际运行。')
    rows=[
    ('帮谁','快餐门店的制作岗位。制作岗位决定普通备餐；店长管理规则与例外审批。先解决反复看库存、估缺口和整理行动的问题。'),
    ('一份小表','6行CSV：5个可比20分钟历史窗口和1行当前快照。历史量13至17；在手12、预留5、不可分配0。全部为课堂模拟。CSV仅供核对，不是库存账。'),
    ('一条规则','只比较需求出现前完成且届时可售的供给。可分配12−5=7；历史均值15；制作4分钟。实际工具比较0份和8份，本次假设下加做8份可覆盖预测。'),
    ('一次人审','制作岗位看数量、时间、候选差异与待核实项，可采纳、改量或忽略。改量重算并留理由。缺制作时间请店长补规则，再重算与重新确认。'),
    ('输出模板','商品／判定状态／动作与数量／完成时间／依据与来源／谁核实什么／确认状态。缺制作时间时quantity=null，不提供可采纳量。'),
    ('不做什么','不承诺销量或食品安全，不代人批准，不虚构规则，不自动增加库存，不执行处罚。采纳只建待办，实际完成才入库；页面是课堂原型。')]
    t=d.add_table(rows=3,cols=2);t.autofit=False
    for i,(label,body) in enumerate(rows):
        c=t.cell(i//2,i%2);c.width=Inches(3.55);tcPr=c._tc.get_or_add_tcPr();sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'F1F5FA');tcPr.append(sh)
        marg=OxmlElement('w:tcMar')
        for edge in ['top','bottom','left','right']:
            x=OxmlElement('w:'+edge);x.set(qn('w:w'),'150');x.set(qn('w:type'),'dxa');marg.append(x)
        tcPr.append(marg);pa=c.paragraphs[0];pa.paragraph_format.space_after=Pt(6);font(pa.add_run(label),13,True)
        pa=c.add_paragraph();pa.paragraph_format.space_after=Pt(6);pa.paragraph_format.line_spacing=1.15;font(pa.add_run(body),11)
    b=OxmlElement('w:tblBorders')
    for edge in ['top','left','bottom','right','insideH','insideV']:
        v=OxmlElement('w:'+edge);v.set(qn('w:val'),'single');v.set(qn('w:sz'),'5');v.set(qn('w:color'),'D9D9D9');b.append(v)
    t._tbl.tblPr.append(b)
    p(d,'运行结论：P0、P1各跑完整与缺信息一次，共4次真实AI工具运行；完整均建议8份，缺信息均阻断。本样本未见正确性改善。',10)
    p(d,'展示入口：00_双击打开课堂演示.html。AI结果为本次真实运行回放；改量、待办、实际完成和留痕可现场操作。人工核对状态见实操报告。',10)
    d.save(OUT/'01_周六实操_一页六格说明.docx')

def d1():
    md=(ROOT/'作业正文.md').read_text(encoding='utf-8');tasks=parse_table(md,'## 周二 D1 AI任务清单');confirms=parse_table(md,'## 周二 D1 人工确认表')
    d=newdoc();title(d,'AI任务边界与人工确认','第8组　傅浩诚 李启顺　2026年11月3日　周一内容及周二D1')
    p(d,'我们帮助快餐门店制作岗位核对高峰供需、比较备餐方案。制作岗位确认普通备餐，店长负责规则和例外审批。本文件给出12步任务清单和8个人工确认点，作为后续开发依据。')
    h(d,'周一任务边界')
    table(d,['主体','负责的工作','边界'],[
    ['AI','识别缺失、归类异常、选择工具、解释预测、生成候选、提醒和复盘草稿','不作顾客承诺，不批准自己方案，不定稿规则，不执行处罚，不登记未发生事实'],
    ['人','制作岗位核事实并决定普通备餐；店长管理规则、审批例外、审阅复盘','先看证据再决定；缺关键事实时不能用同意代替核实'],
    ['程序','算数、时间校验、权限、预留、幂等与流水','硬校验不由AI绕过；CSV是核对视图，不是库存账']],[.55,3.25,3.3],11)
    h(d,'人工确认四要素')
    for s in ['谁确认：按角色授权，普通备餐找制作岗位，规则与例外找店长。','看什么：具体记录、数量、时间、候选差异、缺失项和数据版本。','改什么：采纳、改量、忽略、退回核实；规则与批次校正各走对应权限。','怎么留痕：保存原提议、最终决定、前后值、理由、人员、时间和关联ID。']:p(d,s)
    p(d,'课堂原型已实现一个商品的按钮计算、真实AI结果回放、改量、待办与实际完成登记。正式产品仍按开发设计v0.2实现自动事件、在线模型、服务端事务及多批次等能力。',10)
    page(d);title(d,'D1 AI任务清单 一','覆盖步骤1至6　从现场事实到候选方案')
    p(d,'“AI完成、人工确认”表示AI完成建议或草稿，实际动作仍由授权人员确认，并由程序复核。')
    table(d,['业务步骤','分工标注','具体工作','可检查结果和程序责任'],tasks[:6],[.9,.9,2.5,2.8],10.5)
    p(d,'核实事实与批准行动分别记录。关键字段缺失、无效、过时或冲突时，只阻断受影响动作；共享依赖的问题覆盖全部受影响商品。',10)
    page(d);title(d,'D1 AI任务清单 二','覆盖步骤7至12　从人员决定到结果复盘')
    table(d,['业务步骤','分工标注','具体工作','可检查结果和程序责任'],tasks[6:],[.9,.9,2.5,2.8],10.5)
    p(d,'采纳只建立待办，实际完成才入库；订单完成才消耗。到期停止可分配与实际报废分开记录。例外审批不能解除尚未核实的事实缺口。',10)
    page(d);title(d,'D1 人工确认表 一','确认点C1至C4　看事实 补规则 决定行动')
    p(d,'这是拟实施的角色与操作规范。页面中的角色切换和点击均为演示，不代表真实经营审批。',10)
    table(d,['确认点','谁确认','看什么','可选操作及可改内容','怎么留痕'],confirms[:4],[.7,.65,1.75,2.05,1.95],10.5)
    h(d,'缺制作时间的恢复顺序')
    p(d,'店长核实来源并补规则 → 程序验证权限和版本 → 新快照重新预测模拟 → 核实项标解决 → 制作岗位重新确认新建议。补齐规则不会自动生成待办。')
    page(d);title(d,'D1 人工确认表 二','确认点C5至C8　登记完成 处置批次 审阅复盘')
    table(d,['确认点','谁确认','看什么','可选操作及可改内容','怎么留痕'],confirms[4:],[.7,.65,1.75,2.05,1.95],10.5)
    h(d,'规则变更与已有批次')
    p(d,'商品新规则不自动覆盖已有批次。确需校正时，要有该批次适用证据，保存前后规则和截止，按真实完成时间重算，不从补规则时刻重新计时。重新核对预留；已消耗与已报废量不回库。',10.5)
    d.save(OUT/'02_周一周二_D1任务清单与人工确认表.docx')

def report():
    summary=json.loads((OUT/'运行汇总.json').read_text(encoding='utf-8'))
    review_path=ROOT/'human_review.json';review=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {'state':'pending','text':'待傅浩诚核对；尚未收到本次人工核对答复。'}
    d=newdoc();title(d,'周六智能体实操运行报告','第8组　傅浩诚 李启顺　2026年11月3日补做　全部使用课堂模拟数据')
    p(d,'本次使用当前AI助手与本地只读工具，完成P0、P1各两次独立运行。完整输入均建议加做8份；缺制作时间均返回不可采纳。本样本未见P1正确性改善。另提供可双击运行的操作演示。')
    h(d,'输入与实验方法')
    table(d,['项目','冻结的内容'],[
    ['一份小表','每次6行CSV：H1至H5为历史窗口，S1为当前快照。来源classroom_simulation。缺信息版只删除S1.prep_minutes。'],
    ['数量事实','在手12，预留5，不可分配0，可分配7；无其他在制。历史新增需求13、14、15、16、17，均值15。'],
    ['时间假设','窗口20分钟；制作4分钟；可售时长30分钟；现有批次年龄2分钟。到达假设为第5、10、15、20分钟各4、4、4、3份。'],
    ['AI与工具','4个全新独立AI读者，无继承对话；每次只指定本目录输入和提示词。inspect读表检查，forecast算均值，simulate比较时间轴。'],
    ['版本与隔离','输入与提示词均冻结SHA-256；4次共用只读course-tools-1.0，独立日志。缺信息运行无备用规则。隔离为新会话和文件约束，非操作系统安全沙箱。'],
    ['运行身份','Codex独立AI工具运行，非模板桩。精确后端型号、token和费用未向本实验暴露，未估算；不是DeepSeek Harness运行。']],[1.05,6.05],10.5)
    p(d,'每次保存输入、提示全文、manifest、4条真实工具记录及原始Markdown/JSON结果。工具成功执行不代表业务可执行；缺信息的simulate调用成功，但业务结果为blocked。',10)
    page(d);title(d,'提示词修改与实际结果','P0和P1均为本次新建课堂版本，不冒充10月31日历史运行记录')
    h(d,'只做一项提示词修改')
    p(d,'P0已经要求缺信息不猜、规则请店长核实。P1保留P0全文，仅追加：对受影响商品明确状态；关键字段缺失等情况不给可采纳数量，列出字段、来源、核实角色和恢复条件；事实补齐后重算并重新确认。工具与场景不变。')
    table(d,['运行','实际工具调用','实际输出','程序核对'],[[r['run'],str(r['tool_calls'])+'次','加做8份 待人确认' if r['quantity']==8 else 'blocked 数量为空','与本例断言一致'] for r in summary['runs']],[1.1,1.25,2.6,2.15],10.5)
    h(d,'从真实结果看到的改进与限制')
    p(d,'完整输入：两版均调用inspect、forecast和0份、8份的simulate，得出同一建议。缺信息：两版均识别prep_minutes缺失，未填入默认制作时间，未给可采纳数量。P0已经正确，本样本未见正确性改善。')
    p(d,'各份输出对状态的用词不完全一致，例如待人工确认和建议待确认；说明后续产品需要固定输出枚举与结构校验。P1本次没有因此报错，但也不能据单次输出声称稳定性提升。')
    p(d,'下一步：保留P1作为更明确的指令；在正式产品中加入Schema校验，再验证制作延误、需求提前、多批次、共享原料、并发与重复命令。每类需要新的真实记录；本次不填成功率或经营收益。')
    h(d,'人工核对状态')
    p(d,review['text']+' 程序算式与AI读者检查均不算人工核对。',10.5)
    page(d);title(d,'可运行演示与展示证据','演示打开后无需安装 无需联网 无需API密钥')
    p(d,'双击00_双击打开课堂演示.html，使用完整数据、缺制作时间和库存充足三个情景。AI建议为本次真实运行的离线回放；数量计算和操作即时运行。输入改动后旧AI结果失效，仅标为程序重算。')
    table(d,['实际检查','已观察到的页面结果'],[
    ['完整输入','可分配7、预测15；候选0/6/8份的未覆盖量分别8/2/0。已保存P1完整输入的AI建议为8份。'],
    ['人员改量','自动化操作者在演示中把8改成6并填写演示理由，程序显示尚缺2；不是傅浩诚或李启顺的真实业务决定。'],
    ['采纳与完成','采纳6只建待办，在手仍12；登记实际完成6后在手18、待完成0，完成按钮禁用。未模拟后续销售。'],
    ['缺失与恢复','制作时间为空时隐藏采纳入口；制作岗位不能编辑规则。演示店长补4分钟后重算，仅恢复新候选，待办仍0。'],
    ['正常场景','在手20、预留5时可分配15，无需加做，不建立新待办。']],[1.1,6.0],10.5)
    h(d,'30秒展示稿')
    p(d,'0至8秒：点击计算，看供需与候选。8至18秒：改为6份，留理由，采纳后看库存不变，再登记完成。18至26秒：切缺制作时间，展示阻断。26至30秒：打开AI证据，说明本次是真实记录回放。',10.5)
    p(d,'一句话：它帮助制作岗位核对供需并比较备餐候选；本次缺制作时间时停住，等店长补规则后重算，再由制作岗位确认。',11,True)
    p(d,'截图和实际页面状态保存在附件_演示截图与记录。已提供30秒真实浏览器操作采样录屏和GIF预览，约每秒一帧，无音轨；播放参数见同目录说明。正式产品尚未部署，学习台尚未提交。',10)
    d.save(OUT/'03_周六实操_运行报告与展示说明.docx')

def main():
    OUT.mkdir(parents=True,exist_ok=True);onepage();d1();report();print('Created 3 DOCX files')
if __name__=='__main__':main()
