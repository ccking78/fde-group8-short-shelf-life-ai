'use strict';
const $=id=>document.getElementById(id),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let token='',data=null,busy=false,preview=null,pollTimer=null;
const labels={adjust_existing:'建议调整原待办',observe:'当前计划可覆盖，继续观察',needs_verification:'需要核实后继续'};
async function request(path,payload){const res=await fetch(path,payload?{method:'POST',headers:{'Content-Type':'application/json','X-FDE-Token':token},body:JSON.stringify(payload)}:{});const v=await res.json();if(!res.ok)throw new Error(v.error||'本地请求失败');return v;}
function base(){return{session_id:data.state.session_id,expected_version:data.state.version,request_id:crypto.randomUUID()};}
function currentRun(){return data?.runs.at(-1);}
function currentRec(){const r=currentRun();return r?.status==='completed'&&r.snapshot_version===data.state.version?r.recommendation:null;}
function working(){return ['queued','running'].includes(currentRun()?.status);}
function message(t){$('message').textContent=t;}
async function act(name,extra={}){if(busy)return;busy=true;message('');render();try{data=await request('/api/'+name,{...base(),...extra});preview=null;localStorage.setItem('fde-minimum-session',data.state.session_id);render();schedule();}catch(e){message(e.message);}finally{busy=false;render();}}
async function newCase(variant='normal',delay=false){if(busy)return;busy=true;message('');try{data=await request('/api/new',{variant});preview=null;localStorage.setItem('fde-minimum-session',data.state.session_id);$('verified').checked=false;$('completeAck').checked=false;$('note').value='';render();if(delay){data=await request('/api/delay',base());render();schedule();}}catch(e){message(e.message);}finally{busy=false;render();}}
function schedule(){clearTimeout(pollTimer);if(working())pollTimer=setTimeout(refresh,1200);}
async function refresh(){try{data=await request('/api/state?session_id='+encodeURIComponent(data.state.session_id));render();schedule();}catch(e){message(e.message+'，刷新页面可重新连接');}}
function comparison(){const r=currentRun();return r?.trace.filter(t=>t.name==='compare_plans'&&!t.output.error).at(-1)?.output;}
function timeline(s,c){const x=t=>58+t/20*540,task=s.plan.ready_minute,alt=c?.candidate?.ready_minute;let a='<line x1="58" y1="65" x2="598" y2="65" stroke="#b9cbc2" stroke-width="2"/>';
for(const d of s.demand_due)a+=`<circle cx="${x(d.minute)}" cy="65" r="7" fill="#1a6752"/><text x="${x(d.minute)}" y="98" text-anchor="middle">第${d.minute}分钟</text><text class="note" x="${x(d.minute)}" y="117" text-anchor="middle">需用${d.quantity}份</text>`;
if(task!==null&&task<=20)a+=`<line x1="${x(task)}" y1="28" x2="${x(task)}" y2="76" stroke="#a35019" stroke-width="2"/><text x="${x(task)}" y="19" text-anchor="middle">原任务第${task}分钟完成</text>`;
if(alt!==undefined&&alt!==null&&s.plan.status==='not_started')a+=`<line x1="${x(alt)}" y1="65" x2="${x(alt)}" y2="142" stroke="#1a6752" stroke-width="2" stroke-dasharray="4 3"/><text x="${x(alt)}" y="164" text-anchor="middle">候选调整至第${alt}分钟</text>`;
if(s.plan.status==='completed')a+=`<text x="58" y="155" class="note">第${s.as_of_minute}分钟已登记完成，以下为剩余模拟需用。</text>`;$('timeline').innerHTML=a;}
function render(){if(!data)return;const s=data.state,r=currentRun(),rec=currentRec(),c=comparison(),isCurrent=r?.snapshot_version===s.version,run=working();
let head='正常情景已载入',text='可分配7份，原8份待办预计第4分钟完成。可检查当前计划，或登记唯一延期。',warn=false;
if(s.events.length){head='延期已登记，等待调查';text='原任务预计完成时间由第4分钟改到第12分钟。';warn=true;}
if(rec){head=labels[rec.status];text=rec.summary;warn=rec.status!=='observe';}
if(s.plan.status==='accepted'){head='已采纳调整，等待实际完成';text=`原TASK-8改为${s.plan.quantity}份、第${s.plan.ready_minute}分钟完成；额外新增0份，采纳尚未增加库存。`;warn=false;}
if(s.plan.status==='completed'){head='完成已入账，等待AI复评';text='已登记模拟完成与履约，新批次入账一次。剩余需用仍是预测。';warn=false;}
if(s.plan.status==='partial'){head='少完成部分，剩余ETA待核实';text='已完成量入账，剩余任务时间未知，不能关闭风险。';warn=true;}
if(run){head=r.status==='queued'?'AI调查正在排队':'AI正在查询与比较';text=`已执行${r.trace.length}次业务工具，正在基于当前版本形成新建议。`;}
if(r?.status==='unavailable'){head='本次AI暂不可用';text=r.error+'。已确认待办与基础完成登记仍保留。';warn=true;}
if(rec&&s.plan.status==='completed'){head=labels[rec.status];text=rec.summary;warn=rec.status!=='observe';}
$('status').className='status'+(warn?' warn':'');$('status').innerHTML=`<h2>${esc(head)}</h2><p>${esc(text)}</p>`;
$('version').textContent=`${s.display_sku} / ${s.store_id}　快照 v${s.version}　当前第${s.as_of_minute}分钟　记录均为课堂模拟`;
$('stats').innerHTML=[['课堂账面在手',s.on_hand],['已预留',s.reserved],['账面可分配',s.on_hand-s.reserved-s.blocked],['未完成任务',s.plan.quantity]].map(([k,v])=>`<div class="stat"><b>${v}</b><span>${k}（份）</span></div>`).join('');
const stage=s.plan.status==='completed'||s.plan.status==='partial'?4:s.plan.status==='accepted'?3:r?.status==='completed'?2:s.events.length?1:0;
$('flow').innerHTML=['经营事件','模型查证','人员决定','实际登记','模型复评'].map((v,i)=>`<span class="${i<=stage?'done':''}">${i+1} ${v}</span>`).join('<span>›</span>');timeline(s,isCurrent?c:null);
if(c){const rows=[['现有计划',c.baseline],...(c.candidate?[['调整候选',c.candidate]]:[])];$('comparison').innerHTML=`<p class="small muted">${isCurrent?'当前版本计算':'历史调查计算（采纳后已过期）'} · 模拟预测</p><table><thead><tr><th>计划</th><th>迟供</th><th>期末未满足</th><th>模拟供给完成</th></tr></thead><tbody>${rows.map(([n,b])=>`<tr><td>${n}</td><td>${b.late_units??'待核实'}份</td><td>${b.backlog_end??'待核实'}份</td><td>${b.ready_minute===null?'无待入库任务':b.ready_minute===undefined?'时间未知':'第'+b.ready_minute+'分钟'}</td></tr>`).join('')}</tbody></table>`;}else $('comparison').innerHTML='';
$('aiAdvice').innerHTML=rec?`<h3>AI本次建议</h3><p>${esc(rec.explanation)}</p><p class="small muted">依据：${esc(rec.evidence_refs.join('、'))}。${rec.status==='adjust_existing'?'等待本轮人工核对。':''}</p>`:r?.recommendation?'<p class="small muted">上一版建议已过期，不可再次采纳。新事实需要重新调查。</p>':'<p class="small muted">收到经营事件后触发模型；不会以旧AI回放代替新调用。</p>';
$('toolCount').textContent=r?`（${r.trace.length}次）`:'';$('runMeta').textContent=r?`${r.status} / 快照v${r.snapshot_version} / ${r.model_calls.length}次真实模型调用 / ${r.id}`:'尚无模型运行';
$('toolList').innerHTML=(r?.model_calls||[]).map(m=>`<div class="tool"><b>模型第${m.round}轮</b><p>${esc(m.returned.reason)}</p><span class="small muted">${m.duration_seconds}秒 · ${esc(m.thread_id)}</span></div>`).join('');
$('rawTrace').textContent=r?JSON.stringify({trigger:r.trigger,source:r.source,tools:r.trace},null,2):'模型未运行。';
const editable=!!rec&&s.plan.status==='not_started';$('reviewForm').hidden=!editable;$('noReview').hidden=editable;
$('noReview').textContent=run?'模型正在调查，完成后显示可核对内容。':s.plan.status==='accepted'?'已留存本轮人审，可登记实际完成。':s.plan.status==='completed'?'已登记完成，查看最新AI复评及剩余需用。':'先调查当前版本，再根据建议处理。';
const canAdjust=rec?.status==='adjust_existing';$('candidateFields').hidden=!canAdjust;$('noQuantity').hidden=canAdjust;$('adoptBtn').hidden=!canAdjust;$('previewBtn').hidden=!canAdjust;
if(editable){$('checks').innerHTML=rec.checks.map(v=>`<li>${esc(v)}</li>`).join('');if(canAdjust){if(!$('quantity').matches(':focus'))$('quantity').value=preview?$('quantity').value:rec.quantity;if(!$('ready').matches(':focus'))$('ready').value=preview?$('ready').value:rec.ready_minute;}}
$('adoptBtn').disabled=busy||rec?.status!=='adjust_existing';$('previewBtn').disabled=busy||rec?.status!=='adjust_existing';$('ignoreBtn').disabled=busy;
$('riskRow').hidden=!preview;$('modifyBtn').hidden=!preview;$('modifyBtn').disabled=busy||!preview?.comparison.action_adoptable;
$('preview').textContent=preview?preview.comparison.action_adoptable?`当前改量：第${preview.comparison.candidate.first_late_minute??'—'}分钟首个迟供，迟供${preview.comparison.candidate.late_units}份、期末未满足${preview.comparison.candidate.backlog_end}份；额外新增0。`:'改量不满足规则，不能采纳。':'';
$('completeForm').hidden=s.plan.status!=='accepted';$('actualQty').max=s.plan.quantity;$('completeBtn').disabled=busy;
$('executionState').innerHTML=s.execution.length?`<b>模拟完成已记账</b><p>在手${s.execution.at(-1).on_hand_before} + 完成${s.execution.at(-1).completed_quantity} − 已履约${s.execution.at(-1).cumulative_unreserved_fulfilled??'未知'} = 账面${s.on_hand}份</p><p>剩余任务${s.plan.quantity}份；过去需用待核对${s.unreconciled_past_quantity}份。</p>`:s.human_reviews.length?'<b>已留存人工处理</b><p>采纳不改变在手库存。完成前仍须跟踪。</p>':'';
$('audit').innerHTML=[...s.human_reviews.map(v=>`<div class="audit-row">${esc(v.actor)} / ${esc(v.role)} / ${esc(v.decision)}<br>${esc(v.note)}<br><span class="muted small">${esc(v.at_utc)} · 核对v${v.reviewed_version}</span></div>`),...s.execution.map(v=>`<div class="audit-row">${esc(v.actor)}登记：第${v.completed_minute}分钟完成${v.completed_quantity}份，累计已履约${v.cumulative_unreserved_fulfilled??'未知'}份。<br><span class="small muted">${esc(v.note)}</span></div>`)].join('')||'<p class="small muted">本次尚无人工决定或完成登记。</p>';
for(const id of ['newBtn','missingBtn'])$(id).disabled=busy||run;$('delayBtn').disabled=busy||run||s.version!==0;$('runBtn').disabled=busy||run;$('runBtn').textContent=r?'重新调查当前版本':'检查当前计划';}
function reviewPayload(mode){return{run_id:currentRun().id,role:'制作岗位',actor:$('actor').value,site_verified:$('verified').checked,decision:mode,quantity:Number($('quantity').value),ready_minute:Number($('ready').value),note:$('note').value,preview_sha256:preview?.preview_sha256??null,risk_acknowledged:$('riskAck').checked};}
$('newBtn').addEventListener('click',()=>newCase());$('missingBtn').addEventListener('click',()=>newCase('missing',true));$('delayBtn').addEventListener('click',()=>act('delay'));$('runBtn').addEventListener('click',()=>act('investigate'));
$('adoptBtn').addEventListener('click',()=>act('decision',reviewPayload('adopt')));$('ignoreBtn').addEventListener('click',()=>act('decision',reviewPayload('ignore')));$('modifyBtn').addEventListener('click',()=>act('decision',reviewPayload('modify')));
$('previewBtn').addEventListener('click',async()=>{try{preview=await request('/api/preview',{...base(),quantity:Number($('quantity').value),ready_minute:Number($('ready').value)});$('riskAck').checked=false;render();}catch(e){message(e.message);}});
for(const id of ['quantity','ready'])$(id).addEventListener('input',()=>{preview=null;$('preview').textContent='数量或时间已改动，请重新校验。';$('riskRow').hidden=true;$('modifyBtn').hidden=true;});
$('completeBtn').addEventListener('click',()=>act('complete',{role:'制作岗位',actor:$('actor').value,quantity:Number($('actualQty').value),completed_minute:Number($('actualMinute').value),fulfilled_quantity:$('fulfilled').value===''?null:Number($('fulfilled').value),classroom_acknowledged:$('completeAck').checked}));
$('exportBtn').addEventListener('click',()=>{const a=document.createElement('a');const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.href=u;a.download='课堂运行-'+data.state.session_id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);});
(async()=>{try{const boot=await request('/api/bootstrap');token=boot.token;const sid=new URLSearchParams(location.search).get('session')||localStorage.getItem('fde-minimum-session');if(sid){try{data=await request('/api/state?session_id='+encodeURIComponent(sid));}catch{}}if(!data)await newCase();else{localStorage.setItem('fde-minimum-session',data.state.session_id);render();schedule();}}catch(e){message('本地服务未连接：'+e.message);}})();
