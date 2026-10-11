// Real built UI, real isolated API calculations. No provider credentials or external execution.
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'
const directory = process.env.PARITY_PHASE15_DIR
assert(directory, 'Run scripts/verify-frontend-phase15.py')
const profile = await mkdtemp(join(tmpdir(), 'parity-product-browser-'))
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
  '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--use-mock-keychain', '--password-store=basic', '--remote-debugging-port=0',
  '--user-data-dir='+profile, 'about:blank',
], {stdio:'ignore',detached:true})
const pause = ms => new Promise(resolve=>setTimeout(resolve,ms))
let ws, call, evaluate
const requests=[],errors=[],shots=[],journeys=[],routes=[]
try {
  let port
  for(let i=0;i<100;i++){try{port=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{await pause(100)}}
  assert(port)
  const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json()
  ws=new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
  let sequence=0;const pending=new Map()
  call=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++sequence, timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method))},15000)
    pending.set(id,result=>{clearTimeout(timer);result.error?reject(new Error(JSON.stringify(result.error))):resolve(result.result)})
    ws.send(JSON.stringify({id,method,params}))
  })
  ws.onmessage=async event=>{
    const message=JSON.parse(event.data)
    if(message.id){pending.get(message.id)?.(message);pending.delete(message.id);return}
    if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails.text)
    if(message.method==='Runtime.consoleAPICalled'&&message.params.type==='error')errors.push('Console error')
    if(message.method==='Network.requestWillBeSent'){
      const u=new URL(message.params.request.url)
      if(['http:','https:'].includes(u.protocol)&&u.origin!=='http://127.0.0.1:5178')errors.push('External browser request')
    }
    if(message.method!=='Fetch.requestPaused')return
    const {requestId,request}=message.params,path=new URL(request.url).pathname
    try{
      assert(['/api/presentation/workspace','/api/presentation/research','/api/presentation/scan','/api/presentation/exposure','/api/display-history/NVDA','/api/display-history/AAPL'].includes(path),'Unexpected API '+path)
      assert.equal(request.method,path.endsWith('/workspace')||path.startsWith('/api/display-history/')?'GET':'POST')
      const response=await fetch('http://127.0.0.1:8054'+path,{method:request.method,headers:{'Content-Type':'application/json'},...(request.postData?{body:request.postData}:{}),signal:AbortSignal.timeout(8000)})
      const text=await response.text()
      assert.equal(response.status,200,'API failure '+path)
      const value=JSON.parse(text)
      if(path.endsWith('/workspace')){assert.equal(value.provenance.production_eligible,false);assert.equal(value.assets.length,4)}
      if(path.startsWith('/api/display-history/')){assert.equal(value.production_reference_eligible,false);assert.equal(value.status,'AVAILABLE');assert.equal(value.observations.length,390);assert(value.observations.every(r=>r.data_quality==='HISTORICAL'))}
      if(path.endsWith('/research')){assert.equal(value.provenance.execution_ready,false);assert.equal(value.provenance.transaction_broadcast,false)}
      if(path.endsWith('/exposure'))routes.push(value)
      requests.push({path,method:request.method,status:response.status,inputs:request.postData?JSON.parse(request.postData):null})
      await call('Fetch.fulfillRequest',{requestId,responseCode:response.status,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(text).toString('base64')})
    }catch(error){errors.push(error.message);await call('Fetch.failRequest',{requestId,errorReason:'Failed'}).catch(()=>{})}
  }
  evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true});assert(!r.exceptionDetails,'Evaluation: '+expression);return r.result?.value}
  const wait=async expression=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await pause(100)}throw new Error('State timeout: '+expression)}
  const text=async()=>evaluate('document.body.innerText')
  const click=async value=>evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent.trim()===${JSON.stringify(value)}).click()`)
  const set=async(label,value)=>evaluate(`(()=>{const l=Array.from(document.querySelectorAll('label')).find(l=>l.childNodes[0].textContent===${JSON.stringify(label)});const el=l.querySelector('input,select');Object.getOwnPropertyDescriptor(el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  const shot=async name=>{
    await wait('Array.from(document.images).every(i=>i.complete)')
    assert(await evaluate('Array.from(document.images).every(i=>i.naturalWidth>0)'), 'Local brand images loaded')
    const s=await call('Page.captureScreenshot',{format:'png'});await writeFile(join(directory,name+'.png'),Buffer.from(s.data,'base64'));shots.push(name+'.png')
    const metrics=await call('Page.getLayoutMetrics'),size=metrics.cssContentSize
    const full=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:size.width,height:size.height,scale:1}})
    await writeFile(join(directory,name+'-full.png'),Buffer.from(full.data,'base64'));shots.push(name+'-full.png')
  }
  const check=async()=>{
    assert(!/DEMO|Illustrative data|Synthetic inputs|Unavailable|Disabled on this backend|No real transaction was broadcast|TRUST_GATE|OPPORTUNITY_GATE/.test(await text()),'Development language in normal view')
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Horizontal page overflow')
    assert(await evaluate('document.activeElement.classList.contains("skip-link")||getComputedStyle(document.querySelector(".skip-link")).clipPath==="inset(50%)"'),'Offscreen skip link paints only on focus')
  }
  await call('Page.enable');await call('Runtime.enable');await call('Network.enable')
  await call('Fetch.enable',{patterns:[{urlPattern:'http://127.0.0.1:5178/api/*'}]})
  for(const viewport of [{name:'desktop',width:1440,height:1100,mobile:false},{name:'tablet',width:820,height:1180,mobile:true},{name:'mobile',width:390,height:844,mobile:true}]){
    await call('Emulation.setDeviceMetricsOverride',{...viewport,deviceScaleFactor:1})
    await call('Page.navigate',{url:'http://127.0.0.1:5178/#overview'})
    await wait('document.body.innerText.includes("Market intelligence")')
    assert(!(await text()).includes('System Health'))
    assert(!(await text()).includes('Capability Gates'))
    await wait('!!document.querySelector(".history-readout")')
    assert.equal(await evaluate('document.querySelector(".price-line").getAttribute("d").match(/M/g).length'),1,'Five complete sessions use one observed-price path')
    assert.equal(await evaluate('document.querySelector(".chart-cursor input").max'),'389')
    await click('1D');await wait('document.querySelector(".chart-cursor input").max==="77"')
    assert((await evaluate('document.querySelector(".history-readout").textContent')).includes('09 Oct'))
    await click('1W');await wait('document.querySelector(".chart-cursor input").max==="389"')
    assert(await evaluate('document.querySelector(".overview-stats").getBoundingClientRect().bottom <= document.querySelector(".overview-hero").getBoundingClientRect().top'), 'Overview metrics precede the chart and retained hero')
    if(viewport.name==='desktop'){
      assert(await evaluate('document.querySelector(".page-heading").getBoundingClientRect().top < 200'), 'Compact workspace heading')
      assert(await evaluate('parseFloat(getComputedStyle(document.querySelector(".overview-hero h1")).fontSize) <= 44'), 'Hero supports terminal density')
    }
    await click('Refresh workspace');await wait('document.body.innerText.includes("Scenario inputs unchanged")')
    assert((await text()).includes('Provider prices were not refreshed'))
    await shot('product-'+viewport.name+'-overview-top')
    await evaluate('document.querySelector(".chart-cursor input").focus()')
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Home',code:'Home',windowsVirtualKeyCode:36})
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Home',code:'Home',windowsVirtualKeyCode:36})
    assert.equal(await evaluate('document.querySelector(".chart-cursor input").value'),'0')
    assert((await evaluate('document.querySelector(".history-readout").textContent')).includes('05 Oct'))
    await check();await shot('product-'+viewport.name+'-overview')
    const nav=async hash=>{await evaluate(`location.hash=${JSON.stringify(hash)}`);await pause(80);assert.equal(await evaluate('scrollY'),0,'New section starts at its heading')}
    await nav('#markets');await wait('document.body.innerText.includes("Representation terminal")')
    await set('Search assets','Apple');await wait('document.querySelectorAll("tbody tr").length===2')
    await set('Search assets','');await wait('document.querySelectorAll("tbody tr").length===4')
    await evaluate('Array.from(document.querySelectorAll("button")).find(b=>b.getAttribute("aria-label")==="Inspect AAPL Meridian model").click()')
    await wait('document.querySelector(".study-result").innerText.includes("Apple")')
    await click('Reassess signal');await wait('document.querySelector(".study-toolbar button").textContent==="Reassess signal"')
    await click('Compare routes');await wait('document.body.innerText.includes("Exposure proposal ready")')
    assert.equal(await evaluate('document.querySelectorAll(".snapshot-comparison [data-series]").length'),2,'Two timestamped scenario observations, not fabricated history')
    assert.equal(await evaluate('document.querySelectorAll(".route-economics").length'),2)
    const assertRoute=async()=>{
      const actual=await evaluate('Array.from(document.querySelectorAll(".route-economics")).map(g=>Array.from(g.querySelectorAll(".bar-label strong")).map(s=>s.textContent))')
      const last=routes.at(-1),fmt=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:4}).format(Number(v))
      assert.deepEqual(actual,[last.candidates.map(c=>fmt(c.effective_cost_per_share_usd)),last.candidates.map(c=>fmt(c.all_in_cost_per_share_usd))],'Both charts render returned route economics')
    }
    await assertRoute()
    await set('Budget ($)','120');assert.equal(await evaluate('document.querySelectorAll(".route-economics").length'),0,'Old comparison clears when inputs change')
    await click('Compare routes');await wait('document.querySelectorAll(".route-economics").length===2');await assertRoute()
    await set('Asset','AAPL');await click('Compare routes');await wait('document.querySelector(".route-chart-heading")?.textContent.includes("AAPL")');await assertRoute()
    await evaluate('document.querySelector(".route-bar").focus()')
    await wait('document.querySelectorAll(".route-bar[data-active=true]").length===2')
    await check();await shot('product-'+viewport.name+'-markets')
    await evaluate('document.querySelector(".study-result").scrollIntoView({behavior:"instant",block:"start"})')
    await shot('product-'+viewport.name+'-asset-detail')
    await nav('#trust');await wait('document.body.innerText.includes("Evidence-backed signals")');await check();await shot('product-'+viewport.name+'-trust')
    await nav('#opportunities');await click('Run scan');await wait('document.body.innerText.includes("Ranking policy")')
    await click('Inspect proposal');await wait('document.body.innerText.includes("local constraints passed")');await check();await shot('product-'+viewport.name+'-opportunities')
    await nav('#research');await wait('document.body.innerText.includes("Run study")')
    await set('Preset','low-liquidity');await click('Run study');await wait('document.body.innerText.includes("Thin liquidity weakens")');await check()
    await click('Pin for comparison');await set('Preset','normal');await click('Run study');await wait('document.body.innerText.includes("Wait for a stronger signal")')
    await set('Preset','news');await set('Token price ($)','55');await click('Run study');await wait('document.querySelectorAll(".study-result")[1].innerText.includes("$110.00")')
    await check();await shot('product-'+viewport.name+'-research')
    await click('Reset baseline');await wait('document.querySelectorAll(".study-result")[1].innerText.includes("$102.00")')
    await nav('#portfolio');await wait('document.body.innerText.includes("Portfolio exposure")')
    assert.equal(await evaluate('document.querySelectorAll(".allocation-slice").length'),3)
    assert.equal(await evaluate('document.querySelector(".donut-value").textContent'),'$812.92')
    const weights=await evaluate('Array.from(document.querySelectorAll(".allocation-slice")).map(s=>Number(s.getAttribute("stroke-dasharray").split(" ")[0]))')
    assert(Math.abs(weights.reduce((a,b)=>a+b,0)-1)<1e-10,'Backend weights reconcile')
    await set('Holdings filter','AAPL');await wait('document.querySelectorAll("tbody tr").length===1');await check();await shot('product-'+viewport.name+'-portfolio')
    await nav('#scorecard');await wait('document.body.innerText.includes("Decisions with a trace")');await set('Asset filter','NVDA');await wait('document.querySelectorAll("tbody tr").length===30')
    assert.equal(await evaluate('document.querySelectorAll(".evaluation-chart circle").length'),60,'Two supplied deviation observations per filtered episode');await click('Trace decision');await wait('document.body.innerText.includes("not a real-market backtest")');await set('Outcome filter','incorrect');await check();await shot('product-'+viewport.name+'-scorecard')
    await call('Page.reload');await wait('document.body.innerText.includes("Decisions with a trace")');assert.equal(await evaluate('location.hash'),'#scorecard');await check()
    if(viewport.mobile){
      await evaluate('document.querySelector(".mobile-menu-toggle").click()')
      assert.equal(await evaluate('document.querySelector(".mobile-menu-toggle").getAttribute("aria-expanded")'),'true')
    }
    journeys.push({viewport:viewport.name,sections:7,custom_price_effective_share:'110.00',search:true,route:true,scan:true,research_presets:true,portfolio_filter:true,scorecard_trace:true,refresh_route:true,session_compression:true,period_controls:true,timestamped_two_series:true,allocation_reconciled:true,synchronized_route_graphs:true,full_page_screenshots:true})
  }
  assert.equal(errors.length,0,JSON.stringify(errors))
  assert(requests.some(r=>r.path.endsWith('/research')&&r.inputs.token_price==='55'))
  await evaluate('history.back()');await wait('location.hash!=="#scorecard"')
  await evaluate('history.forward()');await wait('location.hash==="#scorecard"')
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]})
  await wait('document.querySelector(".ambient-background").dataset.motion==="static"')
  assert.equal(await evaluate('document.querySelectorAll(".ambient-background canvas").length'),0)
  await evaluate('Object.defineProperty(document,"hidden",{configurable:true,value:true});document.dispatchEvent(new Event("visibilitychange"))')
  await call('Emulation.setEmulatedMedia',{features:[]})
  await wait('document.querySelector(".ambient-background").dataset.motion==="paused"')
  await evaluate('delete document.hidden;document.dispatchEvent(new Event("visibilitychange"))')
  await wait('document.querySelector(".ambient-background").dataset.motion==="running"')
  assert(requests.every(r=>r.path.startsWith('/api/presentation/')||r.path.startsWith('/api/display-history/')))
  const status=await(await fetch('http://127.0.0.1:8054/api/system-status')).json()
  assert.equal(status.live_trading_enabled,false)
  assert.equal(status.execution_mode,'DRY_RUN')
  for(const g of ['SWAP_LIVE_GATE','RFQ_LIVE_GATE','AGENTIC_WALLET_LIVE_GATE'])assert.equal(status.gates[g],'BLOCKED')
  const production=await(await fetch('http://127.0.0.1:8054/api/workspace')).json()
  assert.equal(production.production_gates.TRUST_GATE,'BLOCKED')
  assert.equal(production.production_gates.OPPORTUNITY_GATE,'BLOCKED_BY_TRUST')
  const report={status:'PASS',journeys,requests,errors,screenshots:shots,gates:production.production_gates,execution_requests:0}
  await writeFile(join(directory,'productization-browser.json'),JSON.stringify(report,null,2))
  console.log(JSON.stringify({status:'PASS',journeys:journeys.length,requests:requests.length,execution_requests:0,evidence:directory}))
}catch(error){if(evaluate)await writeFile(join(directory,'productization-debug.json'),JSON.stringify({error:error.message,errors,requests,page:await evaluate('document.body.innerText')}).slice(0,200000));throw error}
finally{ws?.close();try{process.kill(-chrome.pid,'SIGTERM')}catch{}await pause(200);await rm(profile,{recursive:true,force:true})}
