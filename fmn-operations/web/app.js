'use strict';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=0)=>v==null?'Unknown':Number(v).toLocaleString('en-GB',{maximumFractionDigits:d});
const pct=(v,d=1)=>v==null?'Not estimable':num(v*100,d)+'%';
let data,status,page=location.pathname.slice(1)||'supply',selected,selectionVersion=0,replay='',latestMachines;
const flagClass=f=>['Shortage','Inspect now','Failure recorded'].includes(f)?'danger':['Reorder soon','Excess stock','Check stock'].includes(f)?'warning':'neutral';
const badge=f=>`<span class="badge ${flagClass(f)}">${esc(f)}</span>`;
const metric=(label,value,hint,cls='')=>`<div class="metric"><div class="label">${label}</div><div class="value ${cls}">${value}</div><div class="hint">${hint}</div></div>`;
const fact=(label,value)=>`<div class="fact"><label>${label}</label><strong>${value}</strong></div>`;
const isSupply=()=>page==='supply';

async function post(url,payload){
 const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':status.csrf_token},body:JSON.stringify(payload)});
 const j=await r.json();if(!r.ok)throw new Error(j.error||'Request failed.');return j;
}
function chart(series,{threshold=null,label='Chart',band=null}={}){
 const w=530,h=155,L=39,R=13,T=13,B=24;
 const values=series.flatMap(s=>s.values).filter(v=>v!=null&&Number.isFinite(v));
 if(band)values.push(...band.upper);
 if(threshold!==null)values.push(threshold);
 const max=Math.max(...values,1)*1.12,min=Math.min(0,...values),range=max-min;
 const n=Math.max(...series.map(s=>s.values.length));
 const x=i=>L+i/Math.max(n-1,1)*(w-L-R),y=v=>T+(max-v)/range*(h-T-B);
 let svg=`<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}">`;
 for(let i=0;i<3;i++){let v=min+range*i/2;svg+=`<line x1="${L}" x2="${w-R}" y1="${y(v)}" y2="${y(v)}" stroke="#e7ede8"/><text x="${L-7}" y="${y(v)+3}" text-anchor="end">${num(v,max<2?2:0)}</text>`;}
 if(band){const hi=band.upper.map((v,i)=>`${x(i)},${y(v)}`).join(' ');const lo=band.lower.map((v,i)=>`${x(i)},${y(v)}`).reverse().join(' ');svg+=`<polygon points="${hi} ${lo}" fill="#dcece3" opacity=".75"/>`;}
 if(threshold!==null)svg+=`<line x1="${L}" x2="${w-R}" y1="${y(threshold)}" y2="${y(threshold)}" stroke="#b98a42" stroke-dasharray="5 4"/>`;
 series.forEach(s=>{let path='',pen=false;s.values.forEach((v,i)=>{if(v==null||!Number.isFinite(v)){pen=false;return;}path+=`${pen?'L':'M'}${x(i).toFixed(1)},${y(v).toFixed(1)} `;pen=true;});svg+=`<path d="${path}" fill="none" stroke="${s.color||'#197b72'}" stroke-width="2.3" ${s.dash?'stroke-dasharray="5 3"':''}/>`;});
 const labels=series[0].labels||[];
 [0,Math.floor((n-1)/2),n-1].forEach(i=>{if(labels[i])svg+=`<text x="${x(i)}" y="${h-4}" text-anchor="${i===0?'start':i===n-1?'end':'middle'}">${esc(labels[i])}</text>`;});
 return svg+'</svg>';
}
function renderPage(){
 document.querySelectorAll('[data-page]').forEach(a=>a.classList.toggle('active',a.dataset.page===page));
 $('#breadcrumb').textContent=page==='validation'?'MODEL & DATA REVIEW':isSupply()?'SUPPLY CHAIN':'MANUFACTURING';
 if(page==='validation')return renderValidation();
 const supply=isSupply(),rows=data[page],q=data.data_quality[page],asof=replay||q.end;selected=rows[0].id;
 const need=rows.filter(r=>supply?r.flag!=='Healthy':['Inspect now','Failure recorded'].includes(r.flag)).length;
 const cards=supply?
 metric('SKUs in view',rows.length,'25 established · 3 recent launches')+
 metric('Need attention',need,'Shortage, reserve or excess cover','warn')+
 metric('Expected sales · next 14 days',num(rows.reduce((s,r)=>s+r.demand_14d,0)),'Units across the full SKU portfolio','teal')+
 metric('Held-out forecast error',pct(data.evaluation.supply.test[data.evaluation.supply.selected].wape),'WAPE · 3 chronological test windows'):
 metric('Machines in view',rows.length,replay?'Machines commissioned by replay time':'15 established · 2 newly commissioned')+
 metric('Above action threshold',need,'Suggested inspection within this shift','warn')+
 metric('Risk horizon','24 hours','Scores use the latest available reading','teal')+
 (replay?metric('March average precision',num(data.evaluation.manufacturing.validation.average_precision,3),'Validation completed before this replay'):metric('Failures detected in test',`${data.evaluation.manufacturing.event_test.detected_events} / ${data.evaluation.manufacturing.event_test.eligible_events}`,'Events with a complete warning window'));
 const groups=[...new Set(rows.map(r=>supply?r.category:r.line))].sort();
 $('#app').innerHTML=`<div class="page-head"><div><h1>${supply?'Supply chain outlook':'Plant health outlook'}</h1><p class="subtitle">${supply?'See expected sales, spot inventory pressure and decide which SKUs need action.':'Review machines that need attention, inspect the evidence and follow the risk trend.'}</p></div><div class="asof">DATA THROUGH<strong>${esc(asof.slice(0,10))}${supply?'':' · '+esc(asof.slice(11,16))}</strong>${supply?'':`<select id="replay" aria-label="Historical replay"><option value="">Latest snapshot</option>${Object.keys(data.manufacturing_replays).map(t=>`<option value="${t}" ${replay===t?'selected':''}>Replay ${t.slice(5,16)}</option>`).join('')}</select>`}</div></div>
 <div class="snapshot-note">Historical ${replay?'replay':'snapshot'}. ${supply?'Inventory projections assume no future receipts.':`Next 24 hours after ${esc(asof)}. A model score is not a calibrated failure probability.`}</div>
 <section class="metrics" aria-label="Overview">${cards}</section>
 <div class="workspace"><section class="panel"><div class="panel-head"><div><h2>${supply?'SKU attention list':'Machine attention list'}</h2><div class="small">${supply?'Priority order, then stock cover':'Sorted by model risk score'}</div></div><a class="button" href="/api/export?kind=${page}&as_of=${encodeURIComponent(replay)}">Export CSV</a></div>
 <div class="filters"><input id="search" aria-label="Search ID" placeholder="Search ${supply?'SKU':'machine'} ID…"><select id="group" aria-label="Filter category or line"><option value="">All ${supply?'categories':'lines'}</option>${groups.map(g=>`<option>${esc(g)}</option>`).join('')}</select><select id="flag" aria-label="Filter status"><option value="">All statuses</option>${[...new Set(rows.map(r=>r.flag))].map(f=>`<option>${esc(f)}</option>`).join('')}</select></div>
 <div class="table-wrap"><table><thead><tr>${(supply?['SKU / Category','Status','14d sales','Cover']:['Machine / Line','Status','Risk score','Temp.']).map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody id="rows"></tbody></table></div><div class="table-foot" id="row-count"></div></section><section class="panel" id="detail" aria-label="Selected item"></section></div>
 <section class="panel ask"><div class="ask-head"><div><h2>Ask about your ${supply?'inventory':'machines'}</h2><div class="small">Free-text Q&A grounded in this dataset. Exact IDs retrieve item details.</div></div><span class="badge">RUNTIME AI</span></div><form id="ask-form"><input id="question" aria-label="Your question" maxlength="1000" minlength="3" required placeholder="${supply?'Why is SKU-1004 flagged?':'Which machines need attention in the next 24 hours?'}"><button id="ask-button" class="button primary">Ask AI</button></form><div class="examples"><button class="example">${supply?'Which SKUs may run out before replenishment?':'Which machines need inspection and why?'}</button><button class="example">${supply?'How are new SKUs handled?':'How reliable is this risk score?'}</button></div><div id="answer" role="status"></div></section>`;
 ['search','group','flag'].forEach(id=>$('#'+id).addEventListener(id==='search'?'input':'change',renderRows));
 if(!supply)$('#replay').onchange=e=>{replay=e.target.value;data.manufacturing=replay?data.manufacturing_replays[replay]:latestMachines;renderPage();};
 $('#ask-form').addEventListener('submit',ask);document.querySelectorAll('.example').forEach(b=>b.onclick=()=>{$('#question').value=b.textContent;$('#question').focus();});
 renderRows();renderDetail();
}
function renderRows(){
 const supply=isSupply(),term=$('#search').value.toUpperCase(),group=$('#group').value,flag=$('#flag').value;
 const rows=data[page].filter(r=>r.id.includes(term)&&(!group||(supply?r.category:r.line)===group)&&(!flag||r.flag===flag));
 $('#rows').innerHTML=rows.length?rows.map(r=>`<tr class="${r.id===selected?'selected':''}"><td><button class="entity" data-id="${r.id}" aria-label="View ${r.id}">${r.id}</button><span class="small">${esc(supply?r.category:r.line)}${r.cold_start?' · New':''}</span></td><td>${badge(r.flag)}</td><td>${supply?num(r.demand_14d):num(r.risk_score,3)}</td><td>${supply?(r.cover_days==null?'Unknown':num(r.cover_days,1)+'d'):(r.temperature_c==null?'Missing':num(r.temperature_c,1)+'°C')}</td></tr>`).join(''):'<tr><td colspan="4" class="empty">No matching items. Try another filter.</td></tr>';
 $('#row-count').textContent=`${rows.length} of ${data[page].length} items · Select an ID to inspect evidence and generate its AI explanation.`;
 document.querySelectorAll('[data-id]').forEach(b=>b.onclick=()=>{selected=b.dataset.id;renderRows();renderDetail();});
}
function renderDetail(){
 const r=data[page].find(r=>r.id===selected),supply=isSupply();selectionVersion++;
 let content='';
 if(supply){
  content=`<div class="facts">${fact('Closing stock',num(r.stock))}${fact('Lead time',r.lead_days+' days')}${fact('Lead-time sales',num(r.lead_demand))}</div>
  <div class="chart-title">Expected daily sales · 30 days <span class="legend">Shaded: empirical range</span></div>${chart([{values:r.forecast.map(f=>f.units),labels:r.forecast.map(f=>f.date.slice(5))}],{band:{upper:r.forecast.map(f=>f.upper),lower:r.forecast.map(f=>f.lower)},label:`30-day daily sales forecast for ${r.id}, ${num(r.demand_30d)} units total`})}
  <div class="chart-notes">${r.model.replaceAll('_',' ')} · Reserve: ${num(r.reserve)} units. Band is not a lead-time confidence interval.</div>
  <div class="driver"><span>Suggested replenishment quantity</span><strong>${num(r.reorder_units)} units</strong></div><div class="driver"><span>First projected stockout</span><strong>${r.stock==null?'Unknown':r.stockout_date||'Beyond 30 days'}</strong></div>
  <div class="chart-title">Observed daily sales · latest ${r.history.length} days</div>${chart([{values:r.history.map(h=>h.units),labels:r.history.map(h=>h.date.slice(5)),color:'#78978a'}],{label:`Observed sales history for ${r.id}. Missing readings remain gaps.`})}
  ${r.cold_start?`<div class="notice">Limited history: ${r.history_days} days. Forecast blends observed sales with category peers. Transfer accuracy is uncertain.</div>`:''}
  ${r.stock_source!=='observed'?`<div class="notice">Stock status: ${esc(r.stock_source)}. Verify stock before placing an order.</div>`:''}
  <div class="chart-notes">${r.missing_sales} missing sales readings · ${r.zero_stock_days} zero-stock days. Sales can understate demand during stockouts.</div>`;
 }else{
  content=`<div class="facts">${fact('Model risk score',num(r.risk_score,3))}${fact('Vibration',num(r.vibration_mm_s,3)+' mm/s')}${fact('Since maintenance',num(r.maintenance_hours)+'h')}</div>
  <div class="chart-title">Risk trend · latest 72 hours <span class="legend">Dashed: action threshold ${num(r.threshold,2)}</span></div>${chart([{values:r.trend.map(t=>t.score),labels:r.trend.map(t=>t.timestamp.slice(5,16))}],{threshold:r.threshold,label:`72-hour model risk score trend for ${r.id}. Current score ${num(r.risk_score,3)}`})}
  <div class="chart-notes">Score 24 hours earlier: ${num(r.previous_24h_score,3)}. Scores range from 0 to 1, and are uncalibrated.</div><div class="chart-title">Factors behind the model score</div><div class="drivers">${r.drivers.map(d=>`<div class="driver"><span>${esc(d.label)}<br><strong>${num(d.value,3)}</strong></span><span>${esc(d.direction)}<br>Log-odds contribution ${num(d.log_odds_contribution,2)}</span></div>`).join('')}</div><div class="chart-notes">Contributions compare features with training means. They explain model associations, not failure causes. Correlated factors may share credit.</div>
  ${r.cold_start?`<div class="notice">New machine: ${r.history_hours} hours of history. Uses the shared fleet model. No failure examples validate performance on new machines.</div>`:''}${r.missing_sensor?'<div class="notice">Latest sensor data is incomplete. Model uses a prior reading or training median. Check the sensor.</div>':''}`;
 }
 $('#detail').innerHTML=`<div class="panel-head"><div><h2 class="detail-title">${r.id}</h2><div class="detail-meta">${esc(supply?r.category:r.line)} · ${esc(r.as_of)}</div></div>${badge(r.flag)}</div><div class="detail-body">${content}<div class="ai-box"><div class="ai-label"><span>✦ AI explanation</span><button id="explain" class="button">Generate explanation</button></div><div id="explanation" class="ai-content">${status.ai_configured?'Generate a grounded explanation of this item’s status.':'AI is not configured. Add OPENAI_API_KEY to .env and restart. Numeric evidence is available above; no AI explanation has been generated.'}</div></div></div>`;
 $('#explain').onclick=explain;
 if(status.ai_configured && !['Healthy','Monitor'].includes(r.flag))explain();
}
function showAnswer(target,r){
 target.className='ai-content';target.textContent=r.answer;
 const source=document.createElement('div');source.className='sources';source.textContent=`Sources: ${r.source_ids.join(', ')||'Dataset scope and limitations'} · ${r.model} · Evidence through ${r.evidence_as_of}${r.cached?' · Cached runtime response':''}`;target.append(source);
}
async function explain(){
 const v=selectionVersion,b=$('#explain'),target=$('#explanation');b.disabled=true;target.className='ai-content';target.textContent='Generating from this item’s measurements and model evidence…';
 try{const r=await post('/api/explain',{kind:page,id:selected,as_of:replay});if(v===selectionVersion)showAnswer(target,r);}
 catch(e){if(v===selectionVersion){target.className='ai-content error';target.textContent=e.message;}}
 finally{if(v===selectionVersion)b.disabled=false;}
}
async function ask(e){
 e.preventDefault();const b=$('#ask-button'),target=$('#answer');b.disabled=true;target.className='ai-content';target.textContent='Retrieving evidence and asking AI…';
 try{showAnswer(target,await post('/api/ask',{kind:page,question:$('#question').value,as_of:replay}));}catch(e){target.className='ai-content error';target.textContent=e.message;}finally{b.disabled=false;}
}
function renderValidation(){
 const s=data.evaluation.supply,m=data.evaluation.manufacturing,qs=data.data_quality.supply,qm=data.data_quality.manufacturing;
 $('#app').innerHTML=`<div class="page-head"><div><h1>Model & data review</h1><p class="subtitle">Measured performance, data checks and the assumptions behind each decision.</p></div></div><div class="snapshot-note">Validation uses chronological holdouts. Final test data did not select the model or action threshold. Metrics describe these supplied datasets only.</div>
 <section class="metrics">${metric('Forecast WAPE',pct(s.test[s.selected].wape),'Lower is better · observed sales')}${metric('Machine average precision',num(m.test.average_precision,3),'Test positive-hour prevalence '+pct(m.test.prevalence))}${metric('Failure events detected',m.event_test.detected_events+' / '+m.event_test.eligible_events,'Complete test warning windows')}${metric('False alert hours',num(m.test.false_positive_hours),'Across '+num(m.test.rows)+' evaluated hours','warn')}</section>
 <div class="validation-grid"><section class="panel"><div class="panel-head"><h2>Supply chain validation</h2></div><div class="prose"><p><strong>Selected: ${esc(s.selected.replaceAll('_',' '))}</strong><br>Compare 28-day mean, weekly seasonal naive and a weekday pattern shrunk toward average demand. Select by tuning WAPE.</p><table><thead><tr><th>Model</th><th>Tuning WAPE</th><th>Test WAPE</th></tr></thead><tbody>${Object.keys(s.test).map(k=>`<tr><td>${esc(k.replaceAll('_',' '))}</td><td>${pct(s.tuning[k].wape)}</td><td>${pct(s.test[k].wape)}</td></tr>`).join('')}</tbody></table><p>Training grows up to each cutoff. Tuning cutoffs: 1, 15 and 29 April. Test cutoffs: 13 and 27 May, 10 June. Each forecasts the next 14 days. Missing actual sales never become evaluation targets.</p><p><strong>New launches:</strong> shrink the item’s observed mean toward category peers. Simulating 12-day histories on established SKUs gives ${pct(s.cold_start_simulation.wape)} test WAPE. This does not establish accuracy for actual launches.</p><p>Daily error-band test coverage: ${pct(s.daily_band_test_coverage)}. Bands use tuning residuals. Inventory reserve and excess-cover rules are explicit heuristics. No purchase orders, costs or target service levels are supplied.</p></div></section>
 <section class="panel"><div class="panel-head"><h2>Manufacturing validation</h2></div><div class="prose"><p><strong>Selected: ${esc(m.selected)}</strong><br>Regularized logistic regression shares evidence across the fleet. Uses current sensors, causal 6-hour summaries and missingness indicators. Predicts any failure in the next 24 hours.</p><table><tbody><tr><td>Hourly precision / recall</td><td>${pct(m.test.precision)} / ${pct(m.test.recall)}</td></tr><tr><td>Alert threshold / episodes</td><td>${num(m.test.threshold,2)} / ${m.event_test.alert_episodes}</td></tr><tr><td>False alert hours per machine-day</td><td>${num(m.event_test.false_alert_hours_per_machine_day,2)}</td></tr><tr><td>Maintenance-only baseline AP</td><td>${num(m.baseline_test.average_precision,3)}</td></tr><tr><td>Brier score / zero-score baseline</td><td>${num(m.test.brier,3)} / ${num(m.test.prevalence,3)}</td></tr></tbody></table><p>Train: January–February. Tune: March. Test: April. Purge 24 hours before each split. Exclude current failure rows and the final 24 hours per machine, whose future is unknown. Threshold maximizes March F2 and stays frozen for test.</p><p><strong>Only ${m.total_failure_events} failure events.</strong> Scores are uncalibrated. False alerts and missed events remain material. New machines have no positive events, so their recall cannot be estimated. Risk trends use the same frozen model.</p></div></section>
 <section class="panel"><div class="panel-head"><h2>Source data checks</h2></div><div class="prose"><table><thead><tr><th>Check</th><th>Supply</th><th>Plant</th></tr></thead><tbody><tr><td>Raw rows</td><td>${num(qs.raw_rows)}</td><td>${num(qm.raw_rows)}</td></tr><tr><td>Exact duplicates removed</td><td>${qs.exact_duplicates}</td><td>${qm.exact_duplicates}</td></tr><tr><td>Clean rows</td><td>${num(qs.clean_rows)}</td><td>${num(qm.clean_rows)}</td></tr><tr><td>Missing sales / temperature</td><td>${qs.missing.units_sold}</td><td>${qm.missing.temperature_c}</td></tr><tr><td>Missing stock / vibration</td><td>${qs.missing.closing_stock}</td><td>${qm.missing.vibration_mm_s}</td></tr></tbody></table><p>Normalize supply category case. Reject conflicting time keys and irregular time grids. Keep missing sales out of metrics. Reconstruct missing stock only when every intervening movement is known. Sensor fill uses up to 3 past hours, then training-only medians.</p><p>Input hashes and prediction-level backtests are included in the artifacts folder for reproducibility.</p></div></section>
 <section class="panel"><div class="panel-head"><h2>Grounded AI & operating limits</h2></div><div class="prose"><p>Explanations and free-text answers call an LLM at runtime. Exact IDs retrieve detailed evidence. Fleet questions receive all current entity summaries and validation context. Returned entity references must match the retrieved records.</p><p>If the key is absent, quota is exhausted or the provider fails, the UI reports that no AI answer is available. It never substitutes a template as generated AI.</p><p>AI wording can still misinterpret numbers. Review cited evidence before acting. The prototype never orders stock, changes machinery or sends instructions to operators.</p><p><strong>Next steps:</strong> more failure events, calibration and event-level validation, ERP purchase orders, business-approved alert costs, authentication and live ingestion.</p></div></section></div>`;
}
async function init(){
 try{const responses=await Promise.all([fetch('/api/data'),fetch('/api/status')]);if(responses.some(r=>!r.ok))throw new Error('Could not load app data. Run python train.py and restart.');[data,status]=await Promise.all(responses.map(r=>r.json()));
 latestMachines=data.manufacturing;if(!['supply','manufacturing','validation'].includes(page))page='supply';$('#ai-state').textContent=status.ai_configured?'AI configured · '+status.model:'AI setup needed · see README';renderPage();}
 catch(e){$('#app').innerHTML=`<div class="error-page"><h1>App unavailable</h1><p>${esc(e.message)}</p></div>`;}
}
init();
