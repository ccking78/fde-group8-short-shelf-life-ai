from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import csv, json, math, hashlib, shutil
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--raw-dir',type=Path,default=Path(__file__).resolve().parent.parent/'原始来源')
parser.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent.parent/'复算输出')
args=parser.parse_args()
RAW=args.raw_dir
OUT=args.output_dir
OUT.mkdir(parents=True,exist_ok=True)
DATA=OUT/'数据'; DATA.mkdir(exist_ok=True)
SNAP=OUT/'原始来源'; SNAP.mkdir(exist_ok=True)
def readcsv(path):
 with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def writecsv(name,rows,fields=None):
 path=DATA/name
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0])); w.writeheader(); w.writerows(rows)
 return path
fetched=[]
for off in [0,100,200]:
 j=json.loads((RAW/f'fresh_rows_{off}.json').read_text(encoding='utf-8'))
 assert j['num_rows_total']==4500000
 assert not any(x['truncated_cells'] for x in j['rows'])
 fetched.extend(j['rows'])
series=defaultdict(list)
for x in fetched:series[(x['row']['store_id'],x['row']['product_id'])].append(x)
selected=list(series)[:3]
assert all(len(series[k])==90 for k in selected)
daily=[]; hourly=[]; noon=[]; issues=[]
for key in selected:
 s=series[key]
 dates=sorted(x['row']['dt'] for x in s)
 assert len(set(dates))==90
 assert dates==[(datetime.fromisoformat(dates[0])+timedelta(days=i)).date().isoformat() for i in range(90)]
 for x in s:
  r=x['row']; rowid=f"fresh:train:{x['row_idx']}"
  assert len(r['hours_sale'])==len(r['hours_stock_status'])==24
  assert all(v>=0 for v in r['hours_sale'])
  assert set(r['hours_stock_status'])<={0,1}
  if abs(math.fsum(r['hours_sale'])-r['sale_amount'])>1e-8:issues.append({'id':rowid,'issue':'daily_hour_sum_difference'})
  if sum(r['hours_stock_status'][6:22])!=r['stock_hour6_22_cnt']:issues.append({'id':rowid,'issue':'source_stock_count_differs_from_6_22_slice'})
  dr={'source_record_id':rowid,'source_row_idx':x['row_idx']}
  dr.update({k:json.dumps(v,separators=(',',':')) if isinstance(v,list) else v for k,v in r.items()})
  daily.append(dr)
  for h in range(24):
   hourly.append({'source_record_id':rowid,'source_row_idx':x['row_idx'],'store_id':r['store_id'],'product_id':r['product_id'],'date':r['dt'],'hour_start':f'{h:02}:00','hour_end':f'{h+1:02}:00' if h<23 else '24:00','hour_index':h,'sales_normalized':r['hours_sale'][h],'stockout_flag':r['hours_stock_status'][h],'observation_status':'stockout_censored' if r['hours_stock_status'][h]==1 else 'no_stockout_flag','official_baseline_hour':int(6<=h<22)})
  noon.append({'source_record_id':rowid,'store_id':r['store_id'],'product_id':r['product_id'],'date':r['dt'],'sales_10_11_norm':r['hours_sale'][10],'sales_11_12_norm':r['hours_sale'][11],'sales_12_13_norm':r['hours_sale'][12],'sales_11_13_norm':math.fsum(r['hours_sale'][11:13]),'stockout_11_flag':r['hours_stock_status'][11],'stockout_12_flag':r['hours_stock_status'][12],'lunch_stockout_bins':sum(r['hours_stock_status'][11:13]),'can_use_for_uncensored_sales_comparison':int(not any(r['hours_stock_status'][11:13])),'daily_sales_norm':r['sale_amount']})
assert len(daily)==270 and len(hourly)==6480
assert len({(r['store_id'],r['product_id'],r['date'],r['hour_index']) for r in hourly})==len(hourly)
writecsv('01_Fresh_门店商品日原字段_270条.csv',daily)
writecsv('02_Fresh_逐小时销量与缺货_6480条.csv',hourly)
writecsv('03_Fresh_午段销量核对_270条.csv',noon)
train=readcsv(RAW/'green_train.csv'); test=readcsv(RAW/'green_test.csv'); truth=readcsv(RAW/'green_truth.csv')
assert len({(r['date'],r['store']) for r in train})==len(train)
complete=[r for r in train if r['ordered']!='' and r['unsold']!='']
residuals=[float(r['ordered'])-float(r['sales'])-float(r['unsold']) for r in complete]
trainout=[{'source_record_id':f'green:train:{i}','source_data_row_1based':i+1,**r} for i,r in enumerate(train)]
writecsv('04_Green_连锁烘焙训练日记录_5142条.csv',trainout)
truth_by_id={r['row_id']:r for r in truth}
assert len(truth_by_id)==len(truth)==len(test)
assert set(truth_by_id)=={r['row_id'] for r in test}
held=[{'source_record_id':f"green:test:{r['row_id']}",**r,'sales':truth_by_id[r['row_id']]['sales'],'evaluation_role':'holdout_truth_do_not_use_as_future_input'} for r in test]
assert max(r['date'] for r in train)<min(r['date'] for r in held)
writecsv('05_Green_留后验证日记录_1575条.csv',held)
cases=[]
def add_case(label,rows,predicate,expected):
 for r in rows:
  if predicate(r):
   cases.append({'case_id':f'CASE{len(cases)+1:02}','case_type':label,'source_record_id':r['source_record_id'],'store_id':r.get('store_id',r.get('store','')),'product_id':r.get('product_id',''),'date':r.get('date',''),'hour_start':r.get('hour_start',''),'sales_normalized':r.get('sales_normalized',r.get('sales','')),'stockout_flag':r.get('stockout_flag',''),'unsold_normalized':r.get('unsold',''),'ordered_normalized':r.get('ordered',''),'expected_review':expected,'case_selection':'first_matching_record_in_delivered_order; illustrative_not_performance_sample'})
   return
add_case('缺货标记且零销售',hourly,lambda r:r['official_baseline_hour'] and r['stockout_flag']==1 and r['sales_normalized']==0,'提示销售受缺货影响；不能据零销售判需求为零')
add_case('未标缺货且零销售',hourly,lambda r:r['official_baseline_hour'] and r['stockout_flag']==0 and r['sales_normalized']==0,'保留零销售；不能仅凭销量自行添加缺货标签')
add_case('午段存在缺货标记',hourly,lambda r:r['hour_index'] in [11,12] and r['stockout_flag']==1,'午段销量不能直接充当未受缺货影响的需求真值')
add_case('小时缺货标记且仍有销售',hourly,lambda r:r['official_baseline_hour'] and r['stockout_flag']==1 and r['sales_normalized']>0,'保留原销量和标记；小时标记不能改写成整小时完全无货')
add_case('真实余货字段缺失',trainout,lambda r:r['unsold']=='','显示余货未提供；缺失不填零，不能宣称没有余货')
add_case('销售订货余货字段齐备',trainout,lambda r:r['unsold']!='' and r['ordered']!='','保留各自缩放值；未确认共同尺度前不构造实物守恒和报损率')
writecsv('06_真实记录验收示例.csv',cases)
dictionary=[]
def field(ds,name,meaning,unit,origin,limit):dictionary.append({'dataset':ds,'field':name,'meaning_zh':meaning,'unit_or_values':unit,'origin':origin,'usage_limit':limit})
for name,meaning in [('city_id','匿名城市编号'),('store_id','匿名门店编号'),('product_id','匿名商品编号'),('management_group_id','管理组编号'),('first_category_id','一级品类编号'),('second_category_id','二级品类编号'),('third_category_id','三级品类编号')]:field('Fresh',name,meaning,'标识符','原字段','不能映射为目标企业门店或鸡腿饭；不能跨数据集连接')
field('Fresh','dt','原记录日期','YYYY-MM-DD','原字段','不做时区换算；公开数据无时间戳时区声明')
field('Fresh','sale_amount','日销售量','归一化销售量','原字段','字段名不表示人民币金额；不能还原真实份数')
field('Fresh','hours_sale','0至23点24格小时销量','24元素数组；归一化销售量','原字段','不能拆成真实15分钟流水；含缺货时销售不等于潜在需求')
field('Fresh','hours_stock_status','0至23点缺货标记','1=缺货，0=未标缺货','原字段及官方源码解释','不是库存数量；1不代表该小时内每分钟均无货')
field('Fresh','stock_hour6_22_cnt','06至22点前缺货标记小时格数','小时格数；6:22切片共16格','原字段','不换算成精确缺货分钟')
for name,meaning,unit in [('discount','原记录折扣字段','数值'),('holiday_flag','原记录假日标记','0/1'),('activity_flag','原记录活动标记','0/1'),('precpt','原记录降水字段','按原数据卡'),('avg_temperature','原记录平均温度','按原数据卡'),('avg_humidity','原记录平均湿度','按原数据卡'),('avg_wind_level','原记录平均风级','按原数据卡')]:field('Fresh',name,meaning,unit,'原字段','当日结束后汇总的实际天气不可假装10点已知；建模时确认可获得时点')
for name,meaning in [('sales_normalized','小时销售量'),('stockout_flag','小时缺货标记'),('hour_index','数组索引0至23')]:field('Fresh展开表',name,meaning,'与原数组一致','按索引展开','没有生成新销量或插值')
field('Fresh午段表','lunch_stockout_bins','11点和12点两个小时格中的缺货标记数','0/1/2','原数组求和','两个格不等于精确缺货时长')
field('Fresh午段表','can_use_for_uncensored_sales_comparison','午段未出现缺货标记','0/1','项目筛选标记','只说明这两个小时没有缺货标记，不是真实需求已完全观测的保证')
for name,meaning in [('sales','日销售'),('unsold','日未售出'),('ordered','日订货')]:field('Green',name,meaning,'发布方缩放数值','原字段','三列不能默认共同尺度；unsold不是报废；ordered不是生产批次')
field('Green','store','匿名门店标识','store_0等','原字段','不还原为真实分店，不连接Fresh门店编号')
field('Green','date','记录日期','YYYY-MM-DD','原字段','日数据不能验证11:45出炉与即时库存')
field('Green','is_state_holiday/is_school_holiday/is_special_day','假期及特殊日分类','保留原分类','原字段','日历类字段可预知，需匹配预测时点')
field('Green','temperature_max/min/mean;sunshine_sum;precipitation_sum','天气字段','保留原单位和数值','原字段','当天实际天气不是事前天气预报')
field('全部派生表','source_record_id','可回到原始快照的行标识','数据集:分割:行号或row_id','本次新增','不是发布方的真实门店订单号')
writecsv('07_字段字典与使用限制.csv',dictionary)
checks={
 'fresh':{'api_rows_downloaded':len(fetched),'daily_rows_selected':len(daily),'hourly_rows':len(hourly),'selection':'API顺序前3条完整门店商品序列；未按异常或销量筛选；排除第四条不完整的30日','series':[{'store_id':k[0],'product_id':k[1],'days':len(series[k])} for k in selected],'start':min(r['dt'] for r in daily),'end':max(r['dt'] for r in daily),'nulls':{k:sum(r[k] is None for r in daily) for k in fetched[0]['row']},'duplicate_daily_keys':len(daily)-len({(r['store_id'],r['product_id'],r['dt']) for r in daily}),'stockout_hour_bins_6_22':sum(r['stockout_flag'] for r in hourly if r['official_baseline_hour']),'lunch_days_with_stockout':sum(r['lunch_stockout_bins']>0 for r in noon),'lunch_days_without_stockout_flag':sum(r['can_use_for_uncensored_sales_comparison'] for r in noon),'quality_exceptions':issues},
 'green':{'train_rows':len(train),'stores':len({r['store'] for r in train}),'train_start':min(r['date'] for r in train),'train_end':max(r['date'] for r in train),'rows_with_sales_ordered_unsold':len(complete),'missing_unsold':sum(r['unsold']=='' for r in train),'missing_ordered':sum(r['ordered']=='' for r in train),'nulls':{k:sum(r[k]=='' for r in train) for k in train[0]},'duplicate_store_date':len(train)-len({(r['store'],r['date']) for r in train}),'ordered_minus_sales_minus_unsold_nonzero_rows':sum(abs(x)>1e-6 for x in residuals),'residual_min':min(residuals),'residual_max':max(residuals),'interpretation':'不能假定三列共同尺度；不把差值解释为漏损或业务错误','test_rows':len(test),'truth_rows':len(truth),'joined_one_to_one':True,'test_start':min(r['date'] for r in test),'test_end':max(r['date'] for r in test)},
 'case_count':len(cases),'case_status':'真实记录与预期审核行为；未声称系统已实现或测试通过',
 'not_collected':['真实15分钟销售流水','批次开工和出炉','10点有效库存数量','单品保鲜及温控SOP','单品食材成本和直接变动成本','13点后销售规则'],
 'candidate_not_redistributed':{'name':'French bakery daily sales','reason':'原始发布API元数据 licenseName 为 Data files © Original Authors，本包主数据采用许可明确的两套数据；候选原文件保留于本地下载目录，不在交付包分发'}
}
(OUT/'数据质量核查.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
for name in ['fresh_rows_0.json','fresh_rows_100.json','fresh_rows_200.json','fresh_repo_metadata.json','green_readme.md','green_license.txt','green_train.csv','green_test.csv','green_truth.csv']:
 shutil.copy2(RAW/name,SNAP/name)
(SNAP/'Fresh_许可及出处.txt').write_text('FreshRetailNet-50K\n发布者 Dingdong-Inc\n数据许可 CC BY 4.0\nhttps://creativecommons.org/licenses/by/4.0/\nhttps://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K\n原始数值保持不变，派生表将数组按小时展开并汇总11至13点销售与缺货标记。\n',encoding='utf-8')
shutil.copy2(RAW/'collection_manifest_v1.json',OUT/'采集来源与校验记录.json')
print(json.dumps(checks,ensure_ascii=False,indent=2))
