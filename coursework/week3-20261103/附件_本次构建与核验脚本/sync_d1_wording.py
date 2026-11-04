"""Apply the remaining local wording correction to the D1 submission copy."""
from pathlib import Path
from docx import Document

OUT = Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务提交准备版_20261103")
BEFORE = "正式增量规范与扩充等待用户指挥"
AFTER = "本课堂契约v1已核验，生产字段与批量扩充待安排"


def main():
    path = OUT / "03_周二_D1任务清单与人工确认表.docx"
    doc = Document(path)
    count = 0
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if BEFORE not in paragraph.text:
                        continue
                    if any(BEFORE in run.text for run in paragraph.runs):
                        for run in paragraph.runs:
                            run.text = run.text.replace(BEFORE, AFTER)
                    else:
                        text = paragraph.text.replace(BEFORE, AFTER)
                        paragraph.runs[0].text = text
                        for run in paragraph.runs[1:]:run.text = ""
                    count += 1
    assert count == 1, f"Expected one D1 correction, found {count}"
    doc.save(path)
    textpath = OUT / "可编辑作业正文.md"
    text = textpath.read_text(encoding="utf-8")
    textpath.write_text(text.replace(BEFORE, AFTER), encoding="utf-8")
    print(f"Corrected {count} D1 paragraph and synchronized editable text")


if __name__ == "__main__":main()
