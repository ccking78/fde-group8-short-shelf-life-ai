import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader

OUT=Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务提交准备版_20261103")
WORK=Path(r"F:\ChatGPT\work\FDE_数据补全与提交准备_20261103")
POP=r"C:\Users\张楚岚\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"

def main():
    report=[];tiles=[]
    for pdf in sorted(OUT.glob("*.pdf")):
        folder=WORK / ("qa_"+pdf.stem.split("_")[0]);folder.mkdir(parents=True,exist_ok=True)
        existing=list(folder.glob("page-*.png"))
        if not existing or pdf.stat().st_mtime>min(p.stat().st_mtime for p in existing):
            assert folder.resolve().is_relative_to(WORK.resolve())
            for old in folder.glob("page-*.png"):old.unlink()
            proc=subprocess.run([POP,"-r","120","-png",str(pdf),str(folder / "page")],capture_output=True)
            assert proc.returncode==0,proc.stderr
        pages=sorted(folder.glob("page-*.png"));reader=PdfReader(pdf)
        assert len(pages)==len(reader.pages)
        assert all(len(page.extract_text().strip())>120 for page in reader.pages)
        report.append({"file":pdf.name,"pages":len(pages),"images":[str(p) for p in pages],"visual_review":"pending"})
        for path in pages:
            im=Image.open(path).convert("RGB");im.thumbnail((340,440))
            tile=Image.new("RGB",(360,478),"#e4e9e6");tile.paste(im,((360-im.width)//2,28))
            ImageDraw.Draw(tile).text((10,6),folder.name+" / "+path.stem,font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",13),fill="black")
            tiles.append(tile)
    contact=Image.new("RGB",(1080,478*((len(tiles)+2)//3)),"#cdd6d0")
    for n,tile in enumerate(tiles):contact.paste(tile,((n%3)*360,(n//3)*478))
    contact.save(WORK / "all_pages_contact.png")
    (WORK / "文档排版核验.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps([{"file":r["file"],"pages":r["pages"]} for r in report],ensure_ascii=False,indent=2))

if __name__=="__main__":main()
