import { diagnosticOutput } from './local-outputs.mjs'
// Disposable Chrome profile; never attaches to a personal browser/session.
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'
const profile = await mkdtemp(join(tmpdir(), 'parity-ask-browser-'))
const child = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
  '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--use-mock-keychain', '--password-store=basic', '--remote-debugging-port=0',
  '--user-data-dir=' + profile, 'about:blank',
], { stdio: 'ignore', detached: true })
let ws
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
try {
  let port
  const deadline = Date.now() + 12_000
  while (Date.now() < deadline) {
    try { port = Number((await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break }
    catch { await pause(100) }
  }
  assert(port, 'Browser debugging port unavailable')
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json()
  ws = new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let seq = 0
  const pending = new Map(), apiRequests = [], errors = []
  ws.onmessage = event => {
    const message = JSON.parse(event.data)
    if (message.id) { pending.get(message.id)?.(message); pending.delete(message.id) }
    if (message.method === 'Network.requestWillBeSent') {
      const request = message.params.request, url = new URL(request.url)
      if (url.pathname.startsWith('/api/')) apiRequests.push({ method: request.method, path: url.pathname })
    }
    if (message.method === 'Runtime.exceptionThrown') errors.push('BROWSER_RUNTIME_EXCEPTION')
  }
  const call = (method, params = {}) => new Promise(resolve => {
    const id = ++seq; pending.set(id, resolve); ws.send(JSON.stringify({ id, method, params }))
  })
  const evaluate = async expression => (await call('Runtime.evaluate', { expression, returnByValue: true })).result?.result?.value
  async function waitText(expected) {
    for (let index = 0; index < 80; index++) {
      const text = await evaluate('document.body.innerText')
      if (text?.includes(expected)) return text
      await pause(150)
    }
    throw new Error('Expected browser state not reached: ' + expected)
  }
  await call('Network.enable'); await call('Runtime.enable'); await call('Page.enable')
  await call('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })
  await call('Page.navigate', { url: 'http://127.0.0.1:5173/' })
  const initial = await waitText('Backend connected')
  assert(initial.includes('Ask for stock exposure'))
  assert(initial.includes('Ask for stock exposure'))
  assert.equal(apiRequests.filter(r => r.method === 'POST').length, 0)
  await evaluate('Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Create exposure proposal")).click()')
  const proposalText = await waitText('No real transaction was broadcast.')
  for (const value of ['NVDA', 'Shares per token', 'Estimated real-share exposure', 'Indicative proposal', 'Illustrative values', 'Simulation: UNAVAILABLE', 'Trust integration: NOT ASSESSED']) assert(proposalText.includes(value), value)
  const deferred = await evaluate('Array.from(document.querySelectorAll(".execution-controls button[disabled]")).map(b => b.disabled)')
  assert.deepEqual(deferred, [true, true])
  assert(apiRequests.filter(r => r.method === 'POST').every(r => r.path === '/api/exposure/quote'))
  assert.equal(errors.length, 0)
  const screenshot = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  await writeFile('/private/tmp/parity-ask-desktop.png', Buffer.from(screenshot.result.data, 'base64'))
  await call('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  assert(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow')
  const mobile = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  await writeFile('/private/tmp/parity-ask-mobile.png', Buffer.from(mobile.result.data, 'base64'))
  await evaluate('document.querySelector("#stock-request").focus(); document.querySelector("#stock-request").select()')
  await call('Input.insertText', { text: 'Buy $50 UnsupportedStockXYZ' })
  await evaluate('Array.from(document.querySelectorAll("button")).find(b => b.textContent.includes("Create exposure proposal")).click()')
  const failedText = await waitText('NO_VERIFIED_MATCH')
  assert(failedText.includes('NO_PROPOSAL')); assert(!failedText.includes('Estimated token quantity'))
  const report = {
    timestamp: new Date().toISOString(), url: 'http://127.0.0.1:5173/', result: 'PASS',
    browser: 'Google Chrome headless, disposable profile', data_mode: 'DEMO',
    complete_ask: 'PASS', unsupported_asset_fail_closed: 'PASS',
    mobile_no_horizontal_overflow: 'PASS', backend_financial_values_displayed: 'PASS',
    no_automatic_proposal_post: 'PASS', later_phase_navigation: 'DISABLED',
    simulation_status: 'UNAVAILABLE', execution_ready: false, api_requests: apiRequests,
    runtime_exceptions: 0,
  }
  await writeFile(await diagnosticOutput('CANONICAL_PHASE_2_ASK_REGRESSION.json'), JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify(report))
} finally {
  ws?.close()
  try { process.kill(-child.pid, 'SIGTERM') } catch {}
  await pause(500)
  try { process.kill(-child.pid, 'SIGKILL') } catch {}
  child.unref()
  await rm(profile, { recursive: true, force: true })
}
