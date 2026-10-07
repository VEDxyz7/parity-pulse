// Built UI + actual isolated local backends. No production/provider execution requests.
// See docs/DEMO_UI_INTEGRATION.md for the three safe backend configurations.
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'

const profile = await mkdtemp(join(tmpdir(), 'parity-demo-ui-browser-'))
const child = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
  '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--use-mock-keychain', '--password-store=basic', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank',
], { stdio: 'ignore', detached: true })
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
let ws, backendPort = 8011, phase = 'DEMO_DESKTOP'
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
  const pending = new Map(), requests = [], errors = [], observations = []
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence
    pending.set(id, result => result.error ? reject(new Error('Browser command failed')) : resolve(result))
    ws.send(JSON.stringify({ id, method, params }))
  })
  ws.onmessage = async event => {
    const message = JSON.parse(event.data)
    if (message.id) { pending.get(message.id)?.(message); pending.delete(message.id) }
    if (message.method === 'Runtime.exceptionThrown') errors.push('BROWSER_RUNTIME_EXCEPTION')
    if (message.method !== 'Fetch.requestPaused') return
    const { requestId, request } = message.params
    const path = new URL(request.url).pathname
    try {
      const paper = /^\/api\/demo\/paper\/(fills|positions\/[0-9a-f-]{36}\/(monitor|exit|scorecard))$/.test(path)
      const analytical = ['/api/health', '/api/system-status', '/api/demo/trust/scenarios',
        '/api/demo/trust/scenarios/steady', '/api/demo/trust/scenarios/thin-move',
        '/api/demo/trust/scenarios/supported-move', '/api/demo/opportunity', '/api/demo/risk',
        '/api/demo/quote', '/api/demo/prepare', '/api/demo/simulate']
      assert(paper || analytical.includes(path) || (phase === 'ORDINARY_OVERVIEW' && path === '/api/assets/NVDA/trust'))
      const post = paper ? !path.endsWith('/scorecard') : ['/api/demo/opportunity', '/api/demo/risk', '/api/demo/quote', '/api/demo/prepare', '/api/demo/simulate'].includes(path)
      assert.equal(request.method, post ? 'POST' : 'GET')
      const response = await fetch('http://127.0.0.1:' + backendPort + path, {
        method: request.method, headers: { 'Content-Type': 'application/json' },
        ...(post ? { body: request.postData } : {}),
      })
      const body = await response.text()
      if (path === '/api/system-status') {
        const value = JSON.parse(body)
        assert.equal(value.execution_mode, 'DRY_RUN')
        assert.equal(value.live_trading_enabled, false)
        assert.equal(value.require_simulation, true)
        for (const gate of ['SWAP_LIVE_GATE', 'RFQ_LIVE_GATE', 'AGENTIC_WALLET_LIVE_GATE']) assert.equal(value.gates[gate], 'BLOCKED')
        if (phase.startsWith('DEMO')) assert.equal(value.runtime_mode, 'DEMO')
        else {
          assert.equal(value.runtime_mode, undefined)
          assert.equal(value.data_mode, 'DEMO') // Ordinary runtime, synthetic read-only inputs.
        }
      }
      requests.push({ phase, method: request.method, path, status: response.status })
      await call('Fetch.fulfillRequest', { requestId, responseCode: response.status,
        responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from(body).toString('base64') })
    } catch {
      errors.push('UNEXPECTED_OR_FAILED_LOCAL_API_REQUEST')
      await call('Fetch.failRequest', { requestId, errorReason: 'Failed' })
    }
  }
  const evaluate = async expression => (await call('Runtime.evaluate', { expression, returnByValue: true })).result?.result?.value
  async function wait(expression, expected) {
    for (let index = 0; index < 100; index++) {
      if (await evaluate(expression) === expected) return
      await pause(100)
    }
    throw new Error('Expected browser state not reached: ' + expression)
  }
  const click = text => evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent === ${JSON.stringify(text)}).click()`)
  const stage = name => `Array.from(document.querySelectorAll('.demo-pipeline li')).find(row => row.dataset.stage === ${JSON.stringify(name)})?.dataset.status`
  const shot = async name => {
    const result = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
    await writeFile(join(tmpdir(), 'parity-demo-ui-' + name + '.png'), Buffer.from(result.result.data, 'base64'))
  }
  await call('Runtime.enable'); await call('Page.enable')
  await call('Fetch.enable', { patterns: [{ urlPattern: 'http://127.0.0.1:5174/api/*' }] })
  for (const viewport of [
    { name: 'desktop', width: 1440, height: 1100, mobile: false, backend: 8011 },
    { name: 'mobile', width: 390, height: 844, mobile: true, backend: 8012 },
  ]) {
    backendPort = viewport.backend; phase = 'DEMO_' + viewport.name.toUpperCase()
    await call('Emulation.setDeviceMetricsOverride', { width: viewport.width, height: viewport.height, mobile: viewport.mobile, deviceScaleFactor: 1 })
    await call('Page.navigate', { url: 'http://127.0.0.1:5174/#overview' })
    await wait('Array.from(document.querySelectorAll("a")).some(a => a.textContent === "Open DEMO SANDBOX")', true)
    await evaluate('Array.from(document.querySelectorAll("a")).find(a => a.textContent === "Open DEMO SANDBOX").click()')
    await wait('document.querySelector("#demo-scenario")?.options.length', 3)
    assert.equal(await evaluate('window.location.hash'), '#demo-sandbox')
    await evaluate('document.querySelector(".skip-link").click()')
    assert.equal(await evaluate('window.location.hash'), '#demo-sandbox')
    assert.equal(await evaluate('document.activeElement.id'), 'main-content')
    for (const label of ['DEMO SANDBOX', 'SIMULATED DATA — NOT LIVE MARKET DATA', 'NO REAL FUNDS WILL MOVE']) assert((await evaluate('document.body.innerText')).includes(label))
    assert.equal(await evaluate('Array.from(document.querySelectorAll(".demo-pipeline li")).every(row => row.dataset.status === "pending")'), true)
    await evaluate('document.querySelector("h1").scrollIntoView()')
    await shot(viewport.name + '-entry')
    for (const [scenario, label, classification] of [
      ['steady', 'NORMAL', 'NORMAL'], ['thin-move', 'LIKELY NOISE', 'LIKELY_NOISE'],
      ['supported-move', 'LIKELY INFORMATION', 'LIKELY_INFORMATION'],
    ]) {
      await click(label)
      assert.equal(await evaluate('Array.from(document.querySelectorAll(".demo-pipeline li")).every(row => row.dataset.status === "pending")'), true)
      await click('Run demo scenario')
      await wait('document.querySelector("#demo-sandbox .trust-representation strong")?.textContent', classification)
      await wait(stage('TRUST'), 'pass')
      await click('Analyze Opportunity')
      await wait(stage('OPPORTUNITY'), scenario === 'supported-move' ? 'pass' : 'rejected')
      await wait(stage('ROUTING'), scenario === 'supported-move' ? 'pass' : 'rejected')
      await click('Analyze Risk')
      await wait(stage('RISK'), scenario === 'supported-move' ? 'pass' : 'rejected')
      if (scenario !== 'supported-move') {
        assert((await evaluate('document.querySelector(".pipeline-stop").innerText')).includes('Pipeline stopped at OPPORTUNITY'))
        assert.equal(await evaluate('Array.from(document.querySelectorAll("button")).some(b => b.textContent === "Generate DEMO Quote")'), false)
        await wait(stage('PAPER EXECUTION'), 'pending')
      } else {
        for (const [button, name] of [
          ['Generate DEMO Quote', 'QUOTE'], ['Prepare DEMO Transaction', 'PREPARATION'],
          ['Run DEMO Simulation', 'SIMULATION'], ['Create Paper Fill', 'PAPER EXECUTION'],
          ['Monitor Synthetic Opening Observation', 'MONITOR'], ['Exit Paper Position', 'EXIT'],
          ['View Paper Scorecard', 'SCORECARD'],
        ]) { await click(button); await wait(stage(name), 'pass') }
        assert.equal(await evaluate('Array.from(document.querySelectorAll(".demo-pipeline li")).every(row => row.dataset.status === "pass")'), true)
        assert((await evaluate('document.querySelector(".demo-paper-flow").innerText')).includes('1.45335603303197526425600'))
        assert((await evaluate('document.querySelector(".demo-paper-flow").innerText')).includes('Production TRUST_GATE=BLOCKED'))
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
    assert.deepEqual(await evaluate('Array.from(document.querySelectorAll("button.deferred")).map(b => b.disabled)'), [true, true])
    await evaluate('Array.from(document.querySelectorAll("a")).find(a => a.textContent === "Return to Overview").click()')
    await wait('Array.from(document.querySelectorAll("button")).some(b => b.textContent === "Assess trust")', true)
  }
  assert.equal(requests.filter(r => r.phase.startsWith('DEMO') && r.path === '/api/assets/NVDA/trust').length, 0)
  phase = 'ORDINARY_OVERVIEW'; backendPort = 8013
  // A new document clears the prior DEMO status query when switching test backends.
  await call('Page.navigate', { url: 'http://127.0.0.1:5174/?verification=ordinary#overview' })
  await wait('Array.from(document.querySelectorAll(".status-badge")).some(b => b.textContent === "Backend connected")', true)
  await click('Assess trust')
  await wait('document.querySelector("#trust .trust-representation strong")?.textContent', 'INSUFFICIENT_EVIDENCE')
  await evaluate('Array.from(document.querySelectorAll("a")).find(a => a.textContent === "Open DEMO SANDBOX").click()')
  await wait('document.querySelector(".demo-unavailable h2")?.textContent', 'The connected backend has the sandbox disabled.')
  assert.equal(requests.filter(r => r.phase === 'ORDINARY_OVERVIEW' && r.path.startsWith('/api/demo/')).length, 0)
  assert.equal(errors.length, 0)
  assert(requests.every(r => r.status === 200))
  const report = {
    milestone: 'FINAL_DEMO_UI_INTEGRATION', verified_at_utc: new Date().toISOString(), status: 'PASS',
    browser: 'Disposable headless Google Chrome', frontend: 'Built UI at localhost:5174',
    dataset_type: 'DEMO_FIXTURE', synthetic: true, production_eligible: false,
    actual_local_backends: { desktop: 8011, mobile: 8012, ordinary_runtime_with_synthetic_data: 8013 },
    scenario_results: observations, desktop_mobile_no_page_overflow: true,
    dedicated_navigation: '#demo-sandbox', pipeline_statuses_verified: true,
    production_trust_calls_from_demo_sandbox: 0, ordinary_overview_trust: 'INSUFFICIENT_EVIDENCE',
    ordinary_runtime_demo_requests: 0, production_opportunity_navigation_disabled: true,
    live_provider_calls: 0, live_execution_calls: 0, runtime_errors: errors, request_log: requests,
  }
  await writeFile('docs/evidence/DEMO_UI_BROWSER.json', JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify({ status: 'PASS', scenarios: observations.length, local_api_requests: requests.length, production_trust_calls_from_demo: 0, live_execution_calls: 0 }))
} finally {
  ws?.close()
  try { process.kill(-child.pid, 'SIGTERM') } catch {}
  await pause(400)
  try { process.kill(-child.pid, 'SIGKILL') } catch {}
  child.unref()
  await rm(profile, { recursive: true, force: true })
}
