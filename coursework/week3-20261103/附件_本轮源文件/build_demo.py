import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=Path(r"F:\ChatGPT\outputs\FDE_第8组_三项任务优化版_20261103")


def main():
    payload={"cases":json.loads((OUT/'附件_数据与来源'/'04_模拟情景.json').read_text(encoding='utf-8')),
             "source":json.loads((OUT/'附件_数据与来源'/'数据清单.json').read_text(encoding='utf-8')),
             "review":json.loads((OUT/'新版人工核对记录.json').read_text(encoding='utf-8')),"runs":{}}
    for case in ['normal','delay','missing']:
        folder=OUT/'附件_AI查证记录'/('P2_'+case)
        payload['runs'][case]={"result":json.loads((folder/'result.json').read_text(encoding='utf-8')),
                              "trace":[json.loads(s) for s in (folder/'tool_trace.jsonl').read_text(encoding='utf-8').splitlines()]}
    text=(ROOT/'demo_template.html').read_text(encoding='utf-8')
    text=text.replace('__PAYLOAD_JSON__',json.dumps(payload,ensure_ascii=False).replace('</','<\\/'))
    target=OUT/'00_打开经营异常课堂演示.html'
    target.write_text(text,encoding='utf-8')
    print(json.dumps({'file':str(target),'bytes':target.stat().st_size},ensure_ascii=False))


if __name__=='__main__':main()
