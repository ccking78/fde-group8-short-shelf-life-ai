import json
import subprocess
from pathlib import Path
from pypdf import PdfReader
from PIL import Image,ImageDraw,ImageFont

OUT=Path(r'F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103')
WORK=Path(r'F:\ChatGPT\work\FDE_经营异常优化_20261103')
POP=Path(r'C:\Users\张楚岚\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe')


def main():
    report=[];tiles=[]
    for pdf in sorted(OUT.glob('*.pdf')):
        folder=WORK/('qa_'+pdf.stem.split('_')[0]);folder.mkdir(parents=True,exist_ok=True)
        result=subprocess.run([str(POP),'-r','120','-png',str(pdf),str(folder/'page')],capture_output=True)
        assert result.returncode==0,result.stderr
        images=sorted(folder.glob('page-*.png'))
        reader=PdfReader(pdf);assert len(reader.pages)==len(images)
        report.append({'file':pdf.name,'pages':len(images),'images':[str(p) for p in images],
                       'starts':[p.extract_text()[:55] for p in reader.pages], 'visual_review':'pending'})
        for path in images:
            im=Image.open(path).convert('RGB');im.thumbnail((340,440))
            tile=Image.new('RGB',(360,478),'#e4e9e6');tile.paste(im,((360-im.width)//2,28))
            ImageDraw.Draw(tile).text((12,6),folder.name+' / '+path.stem,font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',13),fill='black');tiles.append(tile)
    contact=Image.new('RGB',(360*3,478*((len(tiles)+2)//3)),'#cdd6d0')
    for n,tile in enumerate(tiles):contact.paste(tile,((n%3)*360,(n//3)*478))
    contact.save(WORK/'all_pages_contact.png')
    (WORK/'document_render_qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
