// Built UI + actual isolated local backends. No production/provider execution requests.
// Run through scripts/verify-frontend-phase15.py; requires a built frontend and local Chrome.
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

const outputDir = process.env.PARITY_PHASE15_DIR
assert(outputDir, 'Use the isolated Phase 15 runner')
// Forward independently: Phase 16 verifies the actual concurrent memory runtime.
const apiTimings=[];
const localFetch=async (...args)=>{ const started=performance.now();try{return await fetch(args[0],{...args[1],signal:AbortSignal.timeout(8000)})}finally{apiTimings.push({path:new URL(args[0]).pathname,elapsed_ms:performance.now()-started})} };
const profile = await mkdtemp(join(tmpdir(), 'parity-demo-ui-browser-'))
const child = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
  '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--use-mock-keychain', '--password-store=basic', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank',
], { stdio: 'ignore', detached: true })
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
let workspaceFailure=false; const workspaceObservations=[];
let agentFailure=false; const agentObservations=[]; let scorecardFailure = false; const scorecardObservations = []; let terminalFailure = false; const terminalObservations = [];
let ws, backendPort = 8054, phase = 'DEMO_DESKTOP'
try {
  let port
  for (let index = 0; index < 100; index++) {
    try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break }
    catch { await pause(100) }
  }
  assert(port, 'Browser debugging port unavailable')
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json()
  ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let sequence = 0
  const pending = new Map(), requests = [], errors = [], observations = [], networkOrigins = new Set(), cancelledNetwork = new Set(), cancelledReads = []
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence
    const deadline=setTimeout(()=>{pending.delete(id);reject(new Error('Browser command timeout: '+method))},30000)
    pending.set(id, result => {clearTimeout(deadline);result.error ? reject(new Error('Browser command failed: ' + method + ' ' + JSON.stringify(result.error))) : resolve(result)})
    ws.send(JSON.stringify({ id, method, params }))
  })
  ws.onmessage = async event => {
    const originPhase=phase, originBackend=backendPort;
    const message = JSON.parse(event.data)
    if (message.id) { pending.get(message.id)?.(message); pending.delete(message.id) }
    if (message.method === 'Network.requestWillBeSent') { const url=new URL(message.params.request.url);if(['http:','https:'].includes(url.protocol)){networkOrigins.add(url.origin);if(url.origin!=='http://127.0.0.1:5178')errors.push('EXTERNAL_BROWSER_REQUEST')} }
    if (message.method === 'Network.loadingFailed' && message.params.canceled) cancelledNetwork.add(message.params.requestId)
    if (message.method === 'Runtime.exceptionThrown') errors.push({code:'BROWSER_RUNTIME_EXCEPTION',phase:originPhase,detail:message.params.exceptionDetails.text})
    if (message.method !== 'Fetch.requestPaused') return
    const { requestId, request, networkId } = message.params
    const path = decodeURIComponent(new URL(request.url).pathname)
    try {
      const paper = /^\/api\/demo\/paper\/(fills|positions\/[0-9a-f-]{36}\/(monitor|exit|scorecard))$/.test(path)
      const analytical = ['/api/health', '/api/system-status', '/api/demo/trust/scenarios',
        '/api/demo/trust/scenarios/steady', '/api/demo/trust/scenarios/thin-move',
        '/api/demo/trust/scenarios/supported-move', '/api/demo/opportunity', '/api/demo/risk',
        '/api/demo/quote', '/api/demo/prepare', '/api/demo/simulate']
      const evaluation = ['TERMINAL','WORKSPACE'].includes(originPhase) && (path === '/api/scorecard' || /^\/api\/audit\/decisions\/[A-Za-z0-9_.:-]{1,160}$/.test(path));
      const liveStatus = originPhase === 'LIVE_STATUS' && path === '/api/live/fills' && request.method === 'GET';
      const terminal = path === '/api/terminal'
      const portfolio = originPhase === 'PORTFOLIO_API_SMOKE' && ['/api/autopilot', '/api/portfolio', '/api/portfolio/plans', '/api/portfolio/audit'].includes(path)
      const workspace = originPhase === 'WORKSPACE' && (['/api/workspace','/api/exposure/quote','/api/opportunities/scan','/api/autopilot','/api/portfolio/plans','/api/audit'].includes(path) || /^\/api\/opportunities\/[a-f0-9]{64}$/.test(path) || /^\/api\/assets\/(AAPL|NVDA)\/trust$/.test(path));
      assert(liveStatus || workspace || (originPhase === 'AGENT_API' && path === '/api/agent/tools') || evaluation || terminal || portfolio || paper || analytical.includes(path) || (originPhase === 'ORDINARY_OVERVIEW' && path === '/api/assets/NVDA/trust'))
      const post = paper ? !path.endsWith('/scorecard') : ['/api/demo/opportunity', '/api/demo/risk', '/api/demo/quote', '/api/demo/prepare', '/api/demo/simulate', '/api/exposure/quote', '/api/opportunities/scan', '/api/autopilot', '/api/portfolio/plans'].includes(path)
      assert.equal(request.method, portfolio ? (['/api/autopilot', '/api/portfolio/plans'].includes(path) ? 'POST' : 'GET') : post ? 'POST' : 'GET')
      const response = await localFetch('http://127.0.0.1:' + originBackend + path + new URL(request.url).search, {
        method: request.method, headers: { 'Content-Type': 'application/json' },
        ...((post || portfolio && request.method === 'POST') ? { body: request.postData } : {}),
      })
      const body = await response.text()
      if (originPhase === 'WORKSPACE') await pause(150) // expose bounded loading state, never change financial response
      if (workspace && path === '/api/workspace' && workspaceFailure || originPhase === 'AGENT_API' && path === '/api/agent/tools' && agentFailure || terminal && terminalFailure || evaluation && scorecardFailure) {
        requests.push({phase:originPhase,method:request.method,path,status:503,injected:true});
        await call('Fetch.fulfillRequest',{requestId,responseCode:503,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from('{}').toString('base64')}); return
      }
      if (path === '/api/system-status') {
        const value = JSON.parse(body)
        assert.equal(value.execution_mode, 'DRY_RUN')
        assert.equal(value.live_trading_enabled, false)
        assert.equal(value.require_simulation, true)
        for (const gate of ['SWAP_LIVE_GATE', 'RFQ_LIVE_GATE', 'AGENTIC_WALLET_LIVE_GATE']) assert.equal(value.gates[gate], 'BLOCKED')
        if (originBackend !== 8056 && (originPhase.startsWith('DEMO') || originPhase === 'TERMINAL' || originPhase === 'AGENT_API' || originPhase === 'WORKSPACE' || originPhase === 'LIVE_STATUS')) assert.equal(value.runtime_mode, 'DEMO')
        else {
          assert.equal(value.runtime_mode, undefined)
          assert.equal(value.data_mode, 'DEMO') // Ordinary runtime, synthetic read-only inputs.
        }
      }
      requests.push({ phase:originPhase, method: request.method, path, status: response.status })
      await call('Fetch.fulfillRequest', { requestId, responseCode: response.status,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(body).toString('base64') })
    } catch (error) {
      // React Query cancels a read when navigation unmounts its view. Chrome
      // invalidates that intercepted request; only a confirmed cancelled GET
      // snapshot is accepted here. Writes and other interception failures fail.
      await pause(50)
      if (request.method === 'GET' && path === '/api/terminal' && error.message.includes('Invalid InterceptionId') && cancelledNetwork.has(networkId)) {
        cancelledReads.push({phase:originPhase,path,reason:'CLIENT_CANCELLED_SNAPSHOT_READ'}); return
      }
      errors.push({code:'UNEXPECTED_OR_FAILED_LOCAL_API_REQUEST',phase:originPhase,path,detail:error.message})
      await call('Fetch.failRequest', { requestId, errorReason: 'Failed' }).catch(error => errors.push(error.message))
    }
  }
  const evaluate = async expression => { const response=(await call('Runtime.evaluate', { expression, returnByValue: true })).result; assert(!response?.exceptionDetails, 'Browser evaluation exception: '+expression); return response?.result?.value }
  async function wait(expression, expected) {
    for (let index = 0; index < 100; index++) {
      if (await evaluate(expression) === expected) return
      await pause(100)
    }
    await writeFile(join(outputDir, 'browser-debug.json'), JSON.stringify({phase,errors,requests:requests.slice(-8),page:await evaluate('document.body.innerText')})); throw new Error('Expected browser state not reached: ' + expression)
  }
  const click = text => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent === ${JSON.stringify(text)}).click()`)
  const stage = name => `Array.from(document.querySelectorAll('.demo-pipeline li')).find(row => row.dataset.stage === ${JSON.stringify(name)})?.dataset.status`
  const shot = async name => {
    const result = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
    await writeFile(join(outputDir, name + '.png'), Buffer.from(result.result.data, 'base64'))
  }
  await call('Runtime.enable'); await call('Page.enable')
  await call('Network.enable');
  await call('Fetch.enable', { patterns: [{ urlPattern: 'http://127.0.0.1:5178/api/*' }] })
  for (const viewport of [
    { name: 'desktop', width: 1440, height: 1100, mobile: false, backend: 8054 },
    { name: 'mobile', width: 390, height: 844, mobile: true, backend: 8055 },
  ]) {
    backendPort = viewport.backend; phase = 'DEMO_' + viewport.name.toUpperCase()
    await call('Emulation.setDeviceMetricsOverride', { width: viewport.width, height: viewport.height, mobile: viewport.mobile, deviceScaleFactor: 1 })
    await call('Page.navigate', { url: 'http://127.0.0.1:5178/?workspace=verified#overview' })
    await wait('Array.from(document.querySelectorAll("a")).some(a => a.textContent.trim() === "Open Research Lab")', true)
    await evaluate('Array.from(document.querySelectorAll("a")).find(a => a.textContent.trim() === "Open Research Lab").click()')
    await wait('document.querySelector("#demo-scenario")?.options.length', 3)
    assert.equal(await evaluate('window.location.hash'), '#demo-sandbox')
    await evaluate('document.querySelector(".skip-link").click()')
    assert.equal(await evaluate('window.location.hash'), '#demo-sandbox')
    assert.equal(await evaluate('document.activeElement.id'), 'main-content')
    for (const label of ['Research Lab', 'Illustrative data', 'NO REAL FUNDS WILL MOVE']) assert((await evaluate('document.body.innerText')).includes(label))
    assert.equal(await evaluate('Array.from(document.querySelectorAll(".demo-pipeline li")).every(row => row.dataset.status === "pending")'), true)
    await evaluate('document.querySelector("h1").scrollIntoView()')
    await shot(viewport.name + '-entry')
    for (const [scenario, label, classification] of [
      ['steady', 'NORMAL', 'NORMAL'], ['thin-move', 'LIKELY NOISE', 'LIKELY_NOISE'],
      ['supported-move', 'LIKELY INFORMATION', 'LIKELY_INFORMATION'],
    ]) {
      await click(label)
      assert.equal(await evaluate('Array.from(document.querySelectorAll(".demo-pipeline li")).every(row => row.dataset.status === "pending")'), true)
      await click('Run scenario')
      await wait('document.querySelector("#demo-sandbox .trust-representation strong")?.textContent', classification)
      await wait(stage('TRUST'), 'pass')
      await click('Analyze Opportunity')
      await wait(stage('OPPORTUNITY'), scenario === 'supported-move' ? 'pass' : 'rejected')
      await wait(stage('ROUTING'), scenario === 'supported-move' ? 'pass' : 'rejected')
      await click('Analyze Risk')
      await wait(stage('RISK'), scenario === 'supported-move' ? 'pass' : 'rejected')
      if (scenario !== 'supported-move') {
        assert((await evaluate('document.querySelector(".pipeline-stop").innerText')).includes('Pipeline stopped at OPPORTUNITY'))
        assert.equal(await evaluate('Array.from(document.querySelectorAll("button")).some(b => b.textContent === "Generate Illustrative Quote")'), false)
        await wait(stage('PAPER EXECUTION'), 'pending')
      } else {
        for (const [button, name] of [
          ['Generate Illustrative Quote', 'QUOTE'], ['Prepare Unsigned Request', 'PREPARATION'],
          ['Run Local Simulation', 'SIMULATION'], ['Create Paper Fill', 'PAPER EXECUTION'],
          ['Monitor Synthetic Opening Observation', 'MONITOR'], ['Exit Paper Position', 'EXIT'],
          ['View Paper Scorecard', 'SCORECARD'],
        ]) { await click(button); await wait(stage(name), 'pass') }
        assert.equal(await evaluate('Array.from(document.querySelectorAll(".demo-pipeline li")).every(row => row.dataset.status === "pass")'), true)
        assert((await evaluate('document.querySelector(".demo-paper-flow").innerText')).includes('1.45335603303197526425600'))
        assert((await evaluate('document.querySelector(".demo-paper-flow").innerText')).includes('Production Trust and Opportunity remain blocked'))
        await evaluate('document.querySelector(".demo-pipeline").scrollIntoView()')
        await shot(viewport.name + '-pipeline')
        await evaluate('Array.from(document.querySelectorAll(".demo-paper-flow h4")).at(-1).scrollIntoView()')
        await shot(viewport.name + '-scorecard')
      }
      assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true)
      observations.push({ viewport: viewport.name, scenario, trust: classification,
        opportunity: scenario === 'supported-move' ? 'ACTIONABLE' : scenario === 'steady' ? 'NO_OPPORTUNITY' : 'REJECTED_BY_TRUST',
        full_hero_flow: scenario === 'supported-move', stand_down: scenario !== 'supported-move', status: 'PASS' })
    }
    assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".execution-controls button[disabled]")).map(b => b.disabled)'), [true, true])
    await evaluate('Array.from(document.querySelectorAll("a")).find(a => a.textContent.trim() === "Return to Overview").click()')
    await wait('Array.from(document.querySelectorAll("button")).some(b => b.textContent === "Assess trust")', true)
  }
  assert.equal(requests.filter(r => r.phase.startsWith('DEMO') && r.path === '/api/assets/NVDA/trust').length, 0)
  phase = 'ORDINARY_OVERVIEW'; backendPort = 8056
  // A new document clears the prior DEMO status query when switching test backends.
  await call('Page.navigate', { url: 'http://127.0.0.1:5178/?workspace=verified&verification=ordinary#overview' })
  await wait('Array.from(document.querySelectorAll(".status-badge")).some(b => b.textContent === "Backend connected")', true)
  await click('Assess trust')
  await wait('document.querySelector("#trust .trust-representation strong")?.textContent', 'INSUFFICIENT_EVIDENCE')
  await evaluate('Array.from(document.querySelectorAll("a")).find(a => a.textContent.trim() === "Open Research Lab").click()')
  await wait('document.querySelector(".demo-unavailable h2")?.textContent', 'Scenario research is disabled on this backend.')
  assert.equal(requests.filter(r => r.phase === 'ORDINARY_OVERVIEW' && r.path.startsWith('/api/demo/')).length, 0)
  const smoke = {superseded_by: 'actual_frontend_mandate_and_drift_journey'}
  for (const viewport of [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}]) {
    phase='TERMINAL'; backendPort=8054;
    await call('Emulation.setDeviceMetricsOverride', {width:viewport.width,height:viewport.height,deviceScaleFactor:1,mobile:viewport.name==='mobile'});
    await call('Page.navigate',{url:'http://127.0.0.1:5178/?workspace=verified&terminal='+viewport.name+'#terminal'});
    await wait('document.querySelector(".terminal h2")?.textContent','Issuer spread board / normalized prices');
    const text = await evaluate('document.querySelector(".terminal").innerText');
    for (const expected of ['Synthetic inputs, not live market data.','$102','2.00%','STALE','INSUFFICIENT_EVIDENCE','Agent evidence','SYNTHETIC FIXTURE — NOT A REAL TRADE','Historical episodes','Opening outcome AVAILABLE']) assert(text.includes(expected),expected);
    assert(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'));
    assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".execution-controls button[disabled]")).map(b=>b.disabled)'),[true,true]);
    await shot(viewport.name+'-terminal');
    // React-controlled input uses the native setter to simulate actual typing.
    await evaluate('Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(document.querySelector("#terminal-ticker"),"ZZZZ"); document.querySelector("#terminal-ticker").dispatchEvent(new Event("input",{bubbles:true}))');
    await click('Apply filter');
    await wait('document.querySelector(".terminal").innerText.includes("No cached representations match this filter.")',true);
    terminalFailure=true;
    await click('Refresh Terminal');
    await wait('document.querySelector(".terminal [role=alert]")?.innerText.includes("No fallback values")',true);
    assert(!(await evaluate('document.querySelector(".terminal").innerText')).includes('$102'));
    terminalFailure=false;
    await evaluate('Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(document.querySelector("#terminal-ticker"),""); document.querySelector("#terminal-ticker").dispatchEvent(new Event("input",{bubbles:true}))');
    await click('Apply filter');
    await wait('document.querySelector(".terminal").innerText.includes("$102")',true);
    await click('Scorecard & audit');
    await wait('document.querySelector(".scorecard-audit")?.innerText.includes("Evaluations")',true);
    assert((await evaluate('document.querySelector(".scorecard-audit").innerText')).includes('CORRECT_ABSTENTION'));
    await evaluate('Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,"value").set.call(document.querySelectorAll(".scorecard-audit select")[1],"PAPER_EXITED"); document.querySelectorAll(".scorecard-audit select")[1].dispatchEvent(new Event("change",{bubbles:true}))');
    await click('Filter evaluations');
    await wait('Array.from(document.querySelectorAll(".scorecard-audit article")).some(a=>a.textContent.trim().includes("PAPER_EXITED"))',true);
    const score = await evaluate('document.querySelector(".scorecard-audit").innerText');
    for (const label of ['SYNTHETIC EVALUATION — NOT A REAL TRADE','No execution evidence','PAPER_EXITED','Composite score unavailable']) assert(score.includes(label),label);
    await evaluate('Array.from(document.querySelectorAll(".scorecard-audit article")).find(a=>a.innerText.includes("PAPER_EXITED")).querySelector("button").click()');
    await wait('document.querySelector(".decision-audit")?.innerText.includes("Complete for recorded scope: Yes")',true);
    const traceText=await evaluate('document.querySelector(".decision-audit").innerText');
    for(const label of ['SIMULATION','PAPER_EXITED','UNAVAILABLE_OR_NOT_APPLICABLE','EXIT','Source projections']) assert(traceText.includes(label),label);
    assert(!traceText.includes('EXECUTION_CONFIRMED'));
    assert(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'));
    await evaluate('document.querySelector(".scorecard-audit h2").scrollIntoView()');
    await shot(viewport.name+'-phase13-scorecard');
    await evaluate('document.querySelector(".decision-audit h3").scrollIntoView()');
    await shot(viewport.name+'-phase13-audit');
    scorecardFailure=true;
    await click('Refresh evaluations');
    await wait('document.querySelector(".scorecard-audit [role=alert]")?.innerText.includes("No fallback or cached outcome")',true);
    assert.equal(await evaluate('document.querySelectorAll(".scorecard-audit article").length'),0);
    scorecardFailure=false;
    await click('Refresh evaluations');
    await wait('document.querySelector(".scorecard-audit")?.innerText.includes("SYNTHETIC EVALUATION")',true);
    scorecardObservations.push({viewport:viewport.name,status:'PASS',scorecard:true,paper_outcome_distinct:true,abstention:true,audit_complete_for_recorded_scope:true,unrecorded_stages_unknown:true,no_false_confirmation:true,api_error_clears_values:true,recovery:true,no_page_overflow:true});
    terminalObservations.push({viewport:viewport.name,status:'PASS',sections:6,backend_exact_values:true,empty_filter:true,api_failure_clears_values:true,recovery:true,no_overflow:true,live_calls:0});
  }
  for(const viewport of [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}]) {
    phase='AGENT_API'; backendPort=8054;
    await call('Emulation.setDeviceMetricsOverride',{width:viewport.width,height:viewport.height,deviceScaleFactor:1,mobile:viewport.name==='mobile'});
    await call('Page.navigate',{url:'http://127.0.0.1:5178/?workspace=verified&agent='+viewport.name+'#overview'});
    await wait('Array.from(document.querySelectorAll("a")).some(a=>a.textContent.trim()==="Agent API")',true);
    await evaluate('Array.from(document.querySelectorAll("a")).find(a=>a.textContent.trim()==="Agent API").click()');
    await wait('document.querySelector(".agent-api-inspection")?.innerText.includes("Backend: Ready")',true);
    const text=await evaluate('document.querySelector(".agent-api-inspection").innerText');
    for(const label of ['NO REAL FUNDS WILL MOVE','buy_stock_exposure','find_opportunity','get_route','get_portfolio','get_autopilot_status','get_stock_trust','compare_stock_tokens','SIMULATION REQUIRED']) assert(text.includes(label),label);
    await evaluate('document.querySelector(".agent-api-inspection details").open=true');
    assert(await evaluate('document.documentElement.scrollWidth <= innerWidth'));
    assert(await evaluate('Array.from(document.querySelectorAll(".execution-controls button[disabled]")).every(b=>b.disabled)'));
    assert.equal(await evaluate('document.querySelectorAll(".agent-api-inspection button").length'),0);
    await shot(viewport.name+'-phase14-agent-api');
    agentFailure=true;
    await call('Page.navigate',{url:'http://127.0.0.1:5178/?workspace=verified&agent-error='+viewport.name+'#agent-api'});
    await wait('document.querySelector(".agent-api-inspection [role=alert]") !== null',true);
    agentFailure=false;
    await click('Retry catalog');
    await wait('document.querySelector(".agent-api-inspection")?.innerText.includes("Backend: Ready")',true);
    agentObservations.push({viewport:viewport.name,status:'PASS',seven_tools:true,schema_expansion:true,inspection_only:true,no_overflow:true,production_navigation_locked:true,api_failure_recovery:true});
  }
  const text = () => evaluate('document.body.innerText');
  const input = (label,value) => evaluate(`(()=>{const l=Array.from(document.querySelectorAll('label')).find(l=>l.textContent.startsWith(${JSON.stringify(label)})); const i=l?.querySelector('input,select'); if(!i)throw Error('Input unavailable'); Object.getOwnPropertyDescriptor(i.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(i,${JSON.stringify(value)});i.dispatchEvent(new Event(i.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
  let journeyStarted; const loadTimings=[];
  const navigate = async(hash,tag='') => {journeyStarted=performance.now();await call('Page.navigate',{url:'http://127.0.0.1:5178/?workspace=verified&phase15='+tag+hash});await wait('Array.from(document.querySelectorAll(".status-badge")).some(b=>b.textContent==="Backend connected")',true);loadTimings.push({tag,ready_ms:performance.now()-journeyStarted,navigation:await evaluate('(()=>{const n=performance.getEntriesByType("navigation")[0];return n?{dom_content_loaded_ms:n.domContentLoadedEventEnd,load_ms:n.loadEventEnd}:null})()')})};
  const mark = async(viewport,journey,details={})=>{assert(await evaluate('document.documentElement.scrollWidth<=innerWidth'),journey+' overflow');workspaceObservations.push({viewport,journey,journey_elapsed_ms:performance.now()-journeyStarted,status:'PASS',no_page_overflow:true,...details});console.log(JSON.stringify({viewport,journey,status:'PASS'}));};
  for (const viewport of [{name:'desktop',width:1440,height:1100,backend:8054},{name:'mobile',width:390,height:844,backend:8055},{name:'tablet',width:768,height:1024,backend:8054}]) {
    phase='WORKSPACE';backendPort=viewport.backend;
    await call('Emulation.setDeviceMetricsOverride',{width:viewport.width,height:viewport.height,mobile:viewport.name==='mobile',deviceScaleFactor:1});
    await navigate('#overview',viewport.name+'-home');await wait('document.querySelector(".home-actions")!==null',true);
    assert((await text()).includes('MARKETS MOVE.'));await wait('document.querySelector(".snapshot-table")!==null',true);await shot(viewport.name+'-overview');if(viewport.name==='mobile'){await click('Menu');assert(await evaluate('document.querySelector(".mobile-menu").getAttribute("aria-expanded")=="true"'));assert(await evaluate('getComputedStyle(document.querySelector(".primary-navigation")).display!=="none"'));await shot('mobile-navigation');await click('Menu');}await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});assert.equal(await evaluate('getComputedStyle(document.querySelector(".refresh-button")).transitionDuration'),'0s');await call('Emulation.setEmulatedMedia',{features:[]});assert((await text()).includes('Illustrative data'));assert((await text()).includes('stale'));assert(await evaluate('document.querySelector(".snapshot-table").tabIndex===0'));assert(!(await text()).includes('DEMO SANDBOX'));assert(!(await text()).includes('DATA_MODE='));assert.equal(await evaluate('document.querySelectorAll(".home-actions a").length'),3);
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
    assert.equal(await evaluate('document.activeElement.className'),'skip-link');await call('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});await call('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
    assert.equal(await evaluate('document.activeElement.id'),'main-content');await mark(viewport.name,'Home / keyboard navigation',{keyboard_skip_link:true});
    await navigate('#ask',viewport.name+'-ask');await wait('document.querySelector("#stock-request")!==null',true);
    // Existing Ask textarea, not a new interpretation or pricing implementation.
    await evaluate(`(()=>{const i=document.querySelector('#stock-request');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,'Buy $50 Apple');i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    // Match the existing frozen backend fixture clock only for this synthetic journey.
    await evaluate("Date.now=()=>Date.parse('2026-10-08T15:00:00Z')");
    await click('Create exposure proposal');await wait('document.querySelector(".ask-result")?.innerText.includes("Indicative proposal")',true);
    assert((await text()).includes('AAPL'));assert((await text()).includes('No real transaction was broadcast.'));assert((await text()).includes('Route Comparison'));
    await click('Review proposal');await wait('document.querySelector(".ask-result")?.innerText.includes("Independent assessment as of")',true);
    for(const label of ['INSUFFICIENT_EVIDENCE','PUBLIC_APPROVAL_UNAVAILABLE','live execution blocked','Simulation: UNAVAILABLE'])assert((await text()).includes(label),label);
    assert.equal(await evaluate('Array.from(document.querySelectorAll("button")).some(b=>!b.disabled&&/^(execute|approve|sign)/i.test(b.textContent))'),false);
    await shot(viewport.name+'-direct-review');await mark(viewport.name,'Direct / routing / Trust-blocked / dry-run review',{backend_proposal:true,approval_unavailable:true});
    await evaluate('Array.from(document.querySelectorAll("a")).find(a=>a.textContent.trim()==="Inspect proposal audit").click()');
    await wait('document.querySelector(".decision-audit")!==null',true);await wait('document.querySelector(".decision-audit")?.innerText.includes("INDICATIVE_ONLY")',true);
    await mark(viewport.name,'Direct proposal → decision audit');
    await navigate('#opportunity',viewport.name+'-opportunity');await wait('document.querySelector(".workspace-form")!==null',true);
    await input('Investment amount / USD notional','100');await input('Risk budget / USD','10');await input('Explicit synthetic scenario','steady');await click('Scan opportunities');
    await wait('document.querySelector(".workspace-view")?.innerText.includes("NO_QUALIFYING_OPPORTUNITY")',true);await mark(viewport.name,'Opportunity / no qualifying opportunity',{stand_down:true});
    await input('Explicit synthetic scenario','supported-move');await click('Scan opportunities');await wait('document.querySelector(".workspace-view table")!==null',true);
    await evaluate('Array.from(document.querySelectorAll("button")).find(b=>/^Inspect .* evidence$/.test(b.textContent)).click()');await wait('document.querySelector(".workspace-view section[aria-label]")!==null',true);
    assert((await text()).includes('Historical scan snapshot'));assert((await text()).includes('Simulation: unavailable for this scan. Approval/execution: blocked.'));
    await shot(viewport.name+'-opportunity');await mark(viewport.name,'Opportunity scan / detail',{ranked_by_backend:true});
    await evaluate('Array.from(document.querySelectorAll("a")).find(a=>a.textContent.trim()==="Open persisted scan").click()');await wait('document.querySelector(".workspace-view table")!==null',true);
    assert.equal(await evaluate('document.querySelectorAll(".workspace-form").length'),0);await mark(viewport.name,'Persisted scan GET');
    await navigate('#portfolio',viewport.name+'-portfolio');await wait('document.querySelector(".workspace-view")?.innerText.includes("Persistent positions")',true);
    for(const label of ['Backend allocation / drift snapshot','historical planning snapshot','NVDA','OPEN','USDT'])assert((await text()).includes(label),label);
    await shot(viewport.name+'-portfolio');await mark(viewport.name,'Portfolio / allocation / drift / persistent position',{backend_values:true});
    await navigate('#autopilot',viewport.name+'-autopilot');await wait('document.querySelector(".workspace-view")?.innerText.includes("Reviewed non-executable mandate")',true);
    assert((await text()).includes('Risk budget'));await mark(viewport.name,'Autopilot / rules / risk / rebalance',{no_automatic_action:true});
    await navigate('#settings',viewport.name+'-settings');await wait('document.querySelector(".workspace-view")?.innerText.includes("WALLET_UNAVAILABLE")',true);
    for(const label of ['WORKER_UNAVAILABLE','EXACT_LIVE_EQUIVALENCE_UNVERIFIED','PUBLIC_APPROVAL_UNAVAILABLE','BLOCKED_BY_TRUST','LIVE_BLOCKED'])assert((await text()).includes(label),label);
    await shot(viewport.name+'-settings');await mark(viewport.name,'Wallet unavailable / live blocked');
    workspaceFailure=true;await click('Refresh workspace state');await wait('document.querySelector(".workspace-view [role=alert]")!==null',true);
    assert(!(await text()).includes('WALLET_UNAVAILABLE'));assert((await text()).includes('remain unknown'));
    workspaceFailure=false;await click('Refresh workspace state');await wait('document.querySelector(".workspace-view")?.innerText.includes("WALLET_UNAVAILABLE")',true);await mark(viewport.name,'Workspace API failure / recovery',{no_zero_substitution:true});
    await navigate('#audit',viewport.name+'-audit');await wait('Array.from(document.querySelectorAll("h2")).some(e=>e.textContent==="Audit events")',true);await wait('document.body.innerText.includes("Recorded backend evidence")',true);
    await shot(viewport.name+'-audit');await mark(viewport.name,'Scorecard / audit pagination / decision links');
  }
  // Ordinary runtime: real existing API behavior with isolated synthetic read-only data.
  phase='WORKSPACE';backendPort=8056;
  await call('Emulation.setDeviceMetricsOverride',{width:390,height:844,mobile:true,deviceScaleFactor:1});
  await navigate('#autopilot','ordinary-empty');await wait('document.body.innerText.includes("No portfolio mandate is configured")',true);
  for(const [label,v] of [['Stock ticker','NVDA'],['Stock target fraction','0.5'],['Cash target fraction','0.5'],['Drift band fraction','0.05'],['Rebalance cap USD','50'],['Risk budget USD','2'],['Stock exposure cap USD','100']])await input(label,v);
  await click('Save reviewed mandate');await wait('document.body.innerText.includes("Mandate saved by backend")',true);await wait('document.body.innerText.includes("Version 1")',true); // Initial reviewed mandate in an empty isolated backend.
  await click('Evaluate drift proposal');await wait('document.body.innerText.includes("Backend rebalance decision: BLOCKED")',true);
  assert((await text()).includes('No execution.'));await mark('mobile','Reviewed mandate → backend drift → blocked rebalance',{expected_version:true,no_execution:true});
  // Actual unchanged simulation service rejects changed synthetic wallet budget.
  phase='DEMO_SIMULATION_FAILURE';backendPort=8057;
  await navigate('#demo-sandbox','simulation-failure');await wait('document.querySelector("#demo-scenario")?.options.length',3);
  await click('LIKELY INFORMATION');await click('Run scenario');await wait(stage('TRUST'),'pass');
  for(const [button,name] of [['Analyze Opportunity','OPPORTUNITY'],['Analyze Risk','RISK'],['Generate Illustrative Quote','QUOTE'],['Prepare Unsigned Request','PREPARATION']]){await click(button);await wait(stage(name),'pass')}
  await click('Run Local Simulation');await wait(stage('SIMULATION'),'rejected');
  assert((await text()).includes('Simulation: SIMULATION_FAIL'));assert((await text()).includes('FAIL · RISK_REVALIDATION')); 
  assert.equal(await evaluate('Array.from(document.querySelectorAll("button")).some(b=>b.textContent==="Create Paper Fill")'),false);
  await shot('mobile-simulation-failure');await mark('mobile','Actual simulation failure',{risk_revalidation:true,no_paper_fill:true});

  // Real persisted agent/scan identifiers include colons. Exercise the encoded
  // HTTP path through React, not only a mocked API transport.
  phase='WORKSPACE';backendPort=8054;
  const persistedAudit=await (await localFetch('http://127.0.0.1:8054/api/scorecard?scorecard_type=OPPORTUNITY&limit=100')).json();
  const agentDecision=persistedAudit.page.items.find(e=>e.decision_id.startsWith('decision:'))?.decision_id;
  assert(agentDecision,'A seeded original agent/scan decision must be inspectable');
  await navigate('#audit/'+agentDecision,'encoded-agent-audit');
  await wait('document.querySelector(".decision-audit")?.innerText.includes("Complete for recorded scope:")',true);
  assert((await text()).includes(agentDecision));
  await mark('mobile','Encoded original agent/scan decision → audit trace',{encoded_colon_contract:true});

  // PR #1 merge regression: current premium dashboard + read-only execution page.
  for(const viewport of [{name:'desktop',width:1440,height:1000},{name:'mobile',width:390,height:844}]) {
    phase='LIVE_STATUS';backendPort=8054;
    await call('Emulation.setDeviceMetricsOverride',{width:viewport.width,height:viewport.height,mobile:viewport.name==='mobile',deviceScaleFactor:1});
    await navigate('#live',viewport.name+'-execution-status');
    await wait('document.body.innerText.includes("Execution worker diagnostics are not configured")',true);
    assert(await evaluate('document.querySelector(".primary-navigation")!==null'));
    assert.equal(await evaluate('Array.from(document.querySelectorAll("button")).some(b=>!b.disabled&&/execute|sign|approve|retire/i.test(b.textContent))'),false);
    for(const gate of ['SWAP_LIVE_GATE','RFQ_LIVE_GATE','AGENTIC_WALLET_LIVE_GATE'])assert((await text()).includes(gate));
    await shot(viewport.name+'-execution-status');
    await mark(viewport.name,'Merged execution status / unconfigured worker',{read_only:true,gates_blocked:true});
  }

  if(errors.length) await writeFile(join(outputDir,'request-errors.json'),JSON.stringify({errors,requests},null,2));
  assert.equal(errors.length, 0)
  assert(requests.every(r => r.status === 200 || r.phase === 'LIVE_STATUS' && r.path === '/api/live/fills' && r.status === 404 || ['TERMINAL','AGENT_API','WORKSPACE'].includes(r.phase) && r.status === 503 && r.injected))
  const report = {
    milestone: 'EMERALD_FRONTEND_REDESIGN', forwarding_serialized:false, api_timings:apiTimings, load_timings:loadTimings, verified_at_utc: new Date().toISOString(), status: 'PASS',
    browser: 'Disposable headless Google Chrome', frontend: 'Built UI at localhost:5178',
    dataset_type: 'DEMO_FIXTURE', synthetic: true, production_eligible: false,
    actual_local_backends: { desktop: 8054, mobile: 8055, ordinary_runtime_with_synthetic_data: 8056, simulation_failure:8057 },
    workspace_scenarios:workspaceObservations, agent_api_scenarios:agentObservations, scenario_results: observations, terminal_scenarios:terminalObservations, scorecard_scenarios:scorecardObservations, portfolio_api_smoke: smoke, desktop_mobile_no_page_overflow: true,
    dedicated_navigation: '#demo-sandbox', pipeline_statuses_verified: true,
    production_trust_calls_from_demo_sandbox: 0, ordinary_overview_trust: 'INSUFFICIENT_EVIDENCE',
    ordinary_runtime_demo_requests: 0, production_opportunity_navigation_disabled: true,
    cancelled_snapshot_reads:cancelledReads, network_origins:[...networkOrigins], external_browser_requests:0, live_provider_calls: 0, live_execution_calls: 0, runtime_errors: errors, request_log: requests,
  }
  await writeFile(join(outputDir, 'browser-evidence.json'), JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify({ status: 'PASS', scenarios: observations.length, local_api_requests: requests.length, production_trust_calls_from_demo: 0, live_execution_calls: 0 }))
} finally {
  ws?.close()
  try { process.kill(-child.pid, 'SIGTERM') } catch {}
  await pause(400)
  try { process.kill(-child.pid, 'SIGKILL') } catch {}
  child.unref()
  await rm(profile, { recursive: true, force: true })
}
