from pathlib import Path
import json
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.pdfgen import canvas
from pypdf import PdfReader

OUT_DIR = Path(r'F:\ChatGPT\outputs\FDE_第8组_第3周D2_20261106')
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / '第8组_第3周D2_AI方案草图_一页.pdf'
GITHUB = 'https://github.com/ccking78/fde-group8-short-shelf-life-ai/tree/coursework/week3-20261103/coursework/week3/d2-20261106'
GUIDE = 'https://camp.coolai.tech/#g8'

pdfmetrics.registerFont(TTFont('Deng', r'C:\Windows\Fonts\Deng.ttf'))
pdfmetrics.registerFont(TTFont('DengBold', r'C:\Windows\Fonts\Dengb.ttf'))
pdfmetrics.registerFontFamily('Deng', normal='Deng', bold='DengBold', italic='Deng', boldItalic='DengBold')

INK = colors.HexColor('#183A31')
GREEN = colors.HexColor('#1A6752')
MUTED = colors.HexColor('#51685F')
LINE = colors.HexColor('#CEDBD3')
PALE = colors.HexColor('#F3F7F4')
ORANGE = colors.HexColor('#985017')
styles = {
    'body': ParagraphStyle('body', fontName='Deng', fontSize=10, leading=13.6, textColor=INK, wordWrap='CJK', spaceAfter=5),
    'small': ParagraphStyle('small', fontName='Deng', fontSize=8.7, leading=12.2, textColor=MUTED, wordWrap='CJK'),
    'table': ParagraphStyle('table', fontName='Deng', fontSize=9.6, leading=13.2, textColor=INK, wordWrap='CJK'),
    'label': ParagraphStyle('label', fontName='DengBold', fontSize=9.6, leading=13.2, textColor=GREEN, wordWrap='CJK'),
    'exception': ParagraphStyle('exception', fontName='Deng', fontSize=8.6, leading=11.7, textColor=INK, wordWrap='CJK'),
}

W, H = landscape(A4)
c = canvas.Canvas(str(OUT), pagesize=(W,H), pageCompression=1)
c.setTitle('第8组 第3周D2 AI方案草图 - 标准化快餐门店薯条岗')
c.setAuthor('第8组 傅浩诚 李启顺')

def para(text, x, top, width, kind='body'):
    p = Paragraph(text, styles[kind])
    _, height = p.wrap(width, H)
    p.drawOn(c,x,top-height)
    return top-height

def block(title, x, top, width, height, lines=None):
    c.setFillColor(colors.white)
    c.setStrokeColor(LINE)
    c.setLineWidth(.7)
    c.roundRect(x,top-height,width,height,7,stroke=1,fill=1)
    c.setFillColor(GREEN)
    c.setFont('DengBold',12.2)
    c.drawString(x+12,top-21,title)
    cursor=top-35
    if lines:
        for text in lines:
            cursor=para(text,x+12,cursor,width-24)
            cursor-=2
        if cursor<top-height+8:
            raise ValueError(f'Card overflow: {title}, bottom={cursor}')
    return cursor

c.setFillColor(GREEN)
c.setFont('DengBold',9)
c.drawString(24,H-26,'第8组  /  第3周D2  /  2026.11.06')
c.setFont('Deng',9)
c.setFillColor(MUTED)
c.drawRightString(W-24,H-26,'傅浩诚 · 李启顺  |  方案草图')
c.setFillColor(INK)
c.setFont('DengBold',19)
c.drawString(24,H-52,'AI经营异常提醒：薯条岗分时备餐与迟供预警')
para('帮助麦当劳这类标准化快餐门店的<b>薯条岗</b>，把分时需求与有效供给对齐，形成可核对的备餐候选；<b>制作岗决定日常调整，缺料上报店长。</b>',24,H-64,W-48,'small')

flow_y=H-108
c.setFillColor(PALE)
c.roundRect(24,flow_y,W-48,22,4,stroke=0,fill=1)
c.setFont('DengBold',10)
c.setFillColor(GREEN)
c.drawCentredString(W/2,flow_y+7,'输入快照  →  AI查证与程序计算  →  人工核查并决定  →  备餐待办、执行记录与复评')

margin=24
gap=14
card_w=(W-2*margin-gap)/2
card_h=175
top1=H-120
top2=top1-card_h-12

input_lines=[
    '<b>输入表：</b>分时需求、熟制批次、已有任务、工序与资源规则。已接订单量与尚未下单的预测新增量分开。',
    '<b>关键字段：</b>商品规格、时点/数量、批次有效截止、任务状态/预计可供、制作时长、单批上限、设备占用；另列成本、客位。',
    '<b>课堂输入：</b>快照11:55；工序3+1分钟；初始可用6等价份，12:01截止。5个需用时点合计40份。',
    '<b>数据性质：</b>本页经营数值全为模拟；单位成本1.80元、客位24个。客位不直接限制全渠道需求。',
]
output_lines=[
    '<b>AI输出：</b>分批备餐候选卡、异常预警及待核实项；附依据、需谁确认。AI选工具、比较并解释，程序算数量与时间。',
    '<b>判定规则：</b>先核已有任务和到点仍有效的供给，再算缺口；最晚开工＝需用时点－必需工序时长，还须满足资源约束。',
    '<b>核对例：</b>12:04需12份，最晚12:00开工；多等2分钟后12:06可供。连同后续任务，整窗预计迟供32份。',
    '<b>候选比较：</b>假设原等待可消除，预计迟供降至0；须核实现场可行性，不能缩短工艺。迟供不等于丢单。',
]
block('01  输入内容',margin,top1,card_w,card_h,input_lines)
block('02  AI输出结果与计算规则',margin+card_w+gap,top1,card_w,card_h,output_lines)
block('03  修改后的人工核查表',margin,top2,card_w,card_h)

review_rows=[
    ('谁确认','制作岗处理普通备餐建议；缺料由店长处置并查看计划。'),
    ('看什么','订单与预测口径、批次余量/有效期、已有任务、实际进度、设备与原料。'),
    ('改什么','采纳／调整后重算／忽略并写理由；缺信息先核实，不能直接批准解除。'),
    ('怎么留痕','人员、时间、决定、理由、原建议及输入/规则版本；计划、完成和消耗分别记录。'),
]
cells=[[Paragraph(a,styles['label']),Paragraph(b,styles['table'])] for a,b in review_rows]
t=Table(cells,colWidths=[62,card_w-86])
t.setStyle(TableStyle([
    ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),5),
    ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),3),
    ('LINEBELOW',(0,0),(-1,-2),.35,LINE),
]))
_,th=t.wrap(card_w-24,card_h-43)
if th>card_h-43: raise ValueError('Human review table overflow')
t.drawOn(c,margin+12,top2-35-th)

final_lines=[
    '<b>业务成果：</b>①经人确认的分批备餐待办；②迟供/缺料/待核实事项；③人审与执行台账；④新事实触发的复评结果。',
    '<b>执行闭环：</b>确认后改计划；实际完成记产出；配餐另记消耗。预测不扣库存，采纳不入库。',
    '<b>D2交付：</b>本页草图＋五行模拟Excel公式试算，规则/例外及人审四要素已整合。',
    '<b>当前进展：</b>公式与4个只读业务工具已核对；原Harness接入、真实模型联调及门店验证待完成。',
]
block('04  最终交付成果（方案目标）',margin+card_w+gap,top2,card_w,card_h,final_lines)

exceptions_y=top2-card_h-12
c.setFillColor(PALE)
c.roundRect(24,exceptions_y-48,W-48,48,4,stroke=0,fill=1)
exceptions=[
    '<b>正常：</b>已有计划可覆盖时维持计划，避免重复加做。',
    '<b>缺规则：</b>暂停受影响候选；已核实的独立事实仍可显示。',
    '<b>缺料/超产能：</b>缺料报店长；超单批上限先拆批，不假设扩产。',
    '<b>AI不可用：</b>保留已确认计划与人工登记，明确提示不可用。',
]
ew=(W-72)/4
for i,text in enumerate(exceptions):
    para(text,33+i*(ew+2),exceptions_y-8,ew-10,'exception')

c.setFillColor(MUTED)
c.setFont('Deng',8)
c.drawString(24,25,'说明：既有公开三明治底稿仅供清洗参考；本页不是麦当劳实测或已验证经营收益。')
c.drawRightString(W-24,25,'1 / 1')
c.setFillColor(GREEN)
c.setFont('Deng',8)
c.drawString(24,12,'作品及源文件：GitHub / 第3周D2')
c.linkURL(GITHUB,(24,9,203,21),relative=0,thickness=0)
c.drawString(226,12,'依据：11/6群通知、技术指南第8组卡片')
c.linkURL(GUIDE,(226,9,450,21),relative=0,thickness=0)
c.showPage()
c.save()

reader=PdfReader(str(OUT))
assert len(reader.pages)==1
text=reader.pages[0].extract_text()
for required in ['输入内容','AI输出结果','人工核查表','最终交付成果','模拟','缺料','怎么留痕']:
    assert required in text,required
print(json.dumps({'pdf':str(OUT),'pages':1,'bytes':OUT.stat().st_size,'github':GITHUB},ensure_ascii=False))
