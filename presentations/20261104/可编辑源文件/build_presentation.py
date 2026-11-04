from pathlib import Path
import json
import hashlib

ROOT=Path(__file__).resolve().parent
SOURCE=Path(r'F:\ChatGPT\outputs\FDE_第8组_最小AI运行闭环_v0.3_20261103')

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def main():
    final=load(SOURCE/'evidence'/'04_完成后的实时复评.json')
    missing=load(SOURCE/'evidence'/'07_缺规则实时调查.json')
    runs=final['runs']+missing['runs']
    assert len(runs)==3 and all(r['status']=='completed' for r in runs)
    minimal=[]
    for r in runs:
        minimal.append({k:r[k] for k in ('id','trigger','recommendation','trace','finished_at_utc')})
        minimal[-1].update(version=r['snapshot_version'],model_requests=len(r['model_calls']),
                          duration_seconds=round(sum(c['duration_seconds'] for c in r['model_calls']),2))
    data={'base':load(SOURCE/'inputs'/'03_课堂基础快照.json')['state'],
          'delayed':runs[0]['snapshot'],'completed':final['state'],'missing':runs[2]['snapshot'],
          'runs':minimal,'source_url':'https://data.mendeley.com/datasets/9hntk3wbwc/1'}
    notes=load(ROOT/'notes.json')
    def embedded(x):
        return json.dumps(x,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    body=(ROOT/'presentation_template.html').read_text(encoding='utf-8').replace('__EVIDENCE_JSON__',embedded(data)).replace('__NOTES_JSON__',embedded(notes))
    path=ROOT/'第8组_5分钟汇报_打开即演示.html'
    path.write_text(body,encoding='utf-8')
    script='# 第8组｜4分钟讲述与展示 + 1分钟答疑\n\n主线严格按老师的五问展开。主讲按页面顺序说，每页带操作时间；备答按追问选用，不全部朗读。\n\n'
    for i,n in enumerate(notes,1):
        script+=f"## {i} {n['title']}\n\n{n['speech']}\n\n**操作与时间**：{n['action']}\n\n"
    (ROOT/'逐页讲稿与答疑备答.md').write_text(script,encoding='utf-8')
    print(json.dumps({'html':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                      'main_script_characters':sum(len(n['speech']) for n in notes[:5]),'slides':6,'main_seconds':240,'qa_seconds':60},ensure_ascii=False))

if __name__=='__main__':main()
