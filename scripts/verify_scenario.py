# D1 scenario parameters and arithmetic only; no real-store optimization claim.
from fractions import Fraction as F
import json
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description='Verify the D1 illustrative scenario; this is not a store performance test.')
parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'work'/'scenario'/'calculation_check.json')
args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)

def simulate(n,frontloaded=False):
    # Minutes from 10:00. Known stock and committed work are independent of choices.
    batches=[{'name':'existing','ready':0,'expire':60,'qty':F(5)}, {'name':'wip','ready':15,'expire':135,'qty':F(10)}]
    batches += [{'name':f'new{i+1}','ready':60+45*i,'expire':180+45*i,'qty':F(12)} for i in range(n)]
    stock=[]; sold=F(0); shortage=F(0); expired=F(0); intervals=[]
    bounds=sorted(set([0,15,60,105,120,135,150,180]+[b['ready'] for b in batches]+[b['expire'] for b in batches if b['expire']<=180]))
    for left,right in zip(bounds,bounds[1:]):
        if left>=180: break
        for b in list(stock):
            if b['expire']<=left:
                expired += b['left']; stock.remove(b)
        for b in batches:
            if b['ready']==left:
                stock.append(dict(b,left=b['qty']))
        rate=F(0) if left<60 else F(2,5) if left<120 else (F(8,15) if frontloaded and left<150 else F(0) if frontloaded else F(4,15))
        need=rate*(right-left); remaining=need; sold_now=F(0)
        for b in sorted(stock,key=lambda x:(x['expire'],x['ready'])):
            used=min(b['left'],remaining); b['left']-=used; remaining-=used; sold_now+=used
        sold+=sold_now; shortage+=remaining
        intervals.append({'from_min':left,'to_min':right,'demand':str(need),'sold':str(sold_now),'shortage':str(remaining),'end_stock':str(sum(x['left'] for x in stock))})
    # Remove expiry at terminal time first; any other residual is scenario clearance.
    terminal_expiry=sum(b['left'] for b in stock if b['expire']<=180)
    clearance=sum(b['left'] for b in stock if b['expire']>180)
    score=shortage*F(1402,100)+(terminal_expiry+clearance)*F(998,100)
    # Common 5 portions expired at 11:00 are reported separately, not silently lost.
    assert F(15+12*n)==sold+expired+terminal_expiry+clearance
    assert sold+shortage==40
    return {'new_batches':n,'lunch_sales':float(sold),'shortage':float(shortage),'existing_expired':float(expired),'terminal_expired':float(terminal_expiry),'clearance_residual':float(clearance),'comparison_loss_yuan':float(score),'intervals':intervals}

uniform=[simulate(n) for n in range(4)]
front=[simulate(n,True) for n in (2,3)]
expected=[(10,30,0,420.60),(22,18,0,252.36),(34,6,0,84.12),(40,0,6,59.88)]
for r,e in zip(uniform,expected):
    got=(r['lunch_sales'],r['shortage'],r['clearance_residual'],r['comparison_loss_yuan'])
    assert got==e,(got,e)
assert front[0]['comparison_loss_yuan']==84.12
assert front[1]['comparison_loss_yuan']==203.88
# Independent hand-ledger for 2/3 choices, without reusing simulator allocation logic.
ledger=[{'interval':'11:00–11:45','demand':18,'two_end':4,'three_end':4}, {'interval':'11:45–12:00','demand':6,'two_end':10,'three_end':10}, {'interval':'12:00–12:30','demand':8,'two_end':2,'three_end':2}, {'interval':'12:30–13:00','demand':8,'two_end':0,'two_short':6,'three_end':6}]
for n in (2,3):
    for step,t in zip(ledger,[105,120,150,180]):
        r=next(x for x in uniform[n]['intervals'] if x['to_min']==t)
        assert F(r['end_stock'])==step['two_end' if n==2 else 'three_end']
report={'assumptions':{'demand_10_11':0,'demand_11_12':24,'demand_12_13':16,'within_hour':'uniform fluid demand','batch_size':12,'processing_minutes':45,'available_at_equals_ready':True,'sale_expiry_minutes_after_ready':120,'clearance_at':'13:00','residual_value':0,'costs_are_scenario_values':True},'uniform':uniform,'frontloaded_12_13_demand':front,'independent_ledger':ledger,'quantity_conservation_checked':True,'cost_precision':'exact Fraction; formatted to 0.01 yuan','scope':'material calculation only, no prototype or store performance test'}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'uniform':[{k:v for k,v in r.items() if k!='intervals'} for r in uniform],'frontloaded':[{k:v for k,v in r.items() if k!='intervals'} for r in front],'status':'passed'},ensure_ascii=False))
