// Real Chromium, built application, credential-free local fixture API only.
import { spawn } from 'node:child_process'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import assert from 'node:assert/strict'
const directory = process.env.PARITY_PHASE15_DIR
assert(directory, 'Run scripts/verify-frontend-phase15.py')
const profile = await mkdtemp(join(tmpdir(), 'parity-landing-browser-'))
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-extensions',
  '--disable-background-networking', '--disable-component-update', '--disable-sync',
  '--use-mock-keychain', '--password-store=basic', '--remote-debugging-port=0',
  '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--user-data-dir='+profile, 'about:blank',
], {stdio:'ignore',detached:true})
const pause = ms => new Promise(resolve=>setTimeout(resolve,ms))
const errors=[],requests=[],assets=[],screenshots=[],journeys=[]
let ws, call, evaluate
try {
  let port
  for(let i=0;i<100;i++){try{port=Number((await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]);break}catch{await pause(100)}}
  assert(port)
  const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json()
  ws=new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
  let sequence=0;const pending=new Map()
  call=(method,params={})=>new Promise((resolve,reject)=>{
    const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(new Error('CDP timeout: '+method))},20000)
    pending.set(id,result=>{clearTimeout(timer);result.error?reject(new Error(JSON.stringify(result.error))):resolve(result.result)})
    ws.send(JSON.stringify({id,method,params}))
  })
  ws.onmessage=async event=>{
    const m=JSON.parse(event.data)
    if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);return}
    if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text)
    if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')errors.push(JSON.stringify(m.params.args))
    if(m.method==='Network.responseReceived'&&m.params.response.status>=400)errors.push('HTTP '+m.params.response.status+' '+m.params.response.url)
    if(m.method==='Network.requestWillBeSent'){
      const u=new URL(m.params.request.url)
      if(['http:','https:'].includes(u.protocol)){
        assets.push(u.pathname)
        if(u.origin!=='http://127.0.0.1:5178')errors.push('External request '+u.origin)
      }
    }
    if(m.method!=='Fetch.requestPaused')return
    const {requestId,request}=m.params,path=new URL(request.url).pathname
    try {
      assert.equal(request.method,'GET','Landing may not submit API operations')
      assert(['/api/presentation/workspace','/api/system-status','/api/workspace','/api/display-history/NVDA','/api/display-history/AAPL'].includes(path),'Unexpected API '+path)
      const response=await fetch('http://127.0.0.1:8054'+path,{signal:AbortSignal.timeout(8000)})
      const body=await response.text(); assert.equal(response.status,200)
      requests.push({path,method:request.method,status:response.status})
      await call('Fetch.fulfillRequest',{requestId,responseCode:200,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(body).toString('base64')})
    }catch(error){errors.push(error.message);await call('Fetch.failRequest',{requestId,errorReason:'Failed'}).catch(()=>{})}
  }
  evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result?.value}
  const wait=async expression=>{for(let i=0;i<150;i++){if(await evaluate(expression))return;await pause(100)}throw new Error('State timeout: '+expression)}
  const shot=async name=>{const s=await call('Page.captureScreenshot',{format:'png'});await writeFile(join(directory,name+'.png'),Buffer.from(s.data,'base64'));screenshots.push(name+'.png')}
  const navigate=async suffix=>{await call('Page.navigate',{url:'http://127.0.0.1:5178/'+suffix})}
  const ready=async()=>wait('document.querySelector(".landing-paper")?.dataset.renderState==="ready"')
  const check=async()=>{
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Horizontal overflow')
    assert.equal(await evaluate('getComputedStyle(document.querySelector(".ambient-background")).visibility'),'hidden','Ambient layer must not obscure landing')
    assert(await evaluate('!document.querySelector(".landing-enter")&&!document.querySelector(".landing-hero").innerText.includes("Enter Parity Pulse")'),'Entry CTA must be absent')
    assert(await evaluate('(()=>{const s=getComputedStyle(document.querySelector(".landing-halo"));return s.backgroundImage.split("radial-gradient").length===6&&s.animationName==="none"&&s.filter==="none"&&s.pointerEvents==="none"})()'),'Static layered emerald ambience missing')
    assert.equal(await evaluate('document.querySelectorAll(".product-workspace").length'),1,'Duplicate dashboard')
    assert(await evaluate('(()=>{const r=document.querySelector(".landing-copy").getBoundingClientRect();return r.top>0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth})()'),'Copy clipped')
  }
  await call('Page.enable');await call('Runtime.enable');await call('Network.enable');await call('Network.setCacheDisabled',{cacheDisabled:true})
  await call('Fetch.enable',{patterns:[{urlPattern:'http://127.0.0.1:5178/api/*'}]})
  for(const v of [
    {name:'desktop',width:1440,height:1000,mobile:false},
    {name:'tablet',width:820,height:1180,mobile:true},
    {name:'mobile',width:390,height:844,mobile:true},
    {name:'short-mobile',width:375,height:667,mobile:true},
    {name:'compact-mobile',width:320,height:568,mobile:true},
    {name:'landscape',width:844,height:390,mobile:true},
  ]){
    await call('Emulation.setDeviceMetricsOverride',{...v,deviceScaleFactor:1})
    await call('Emulation.setTouchEmulationEnabled',{enabled:v.mobile})
    await navigate('');await ready();await wait('document.body.innerText.includes("Market intelligence")')
    await check();await pause(250);await shot('landing-'+v.name)
    if(v.name==='desktop'){
      await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:770,y:400})
      await pause(300);await shot('landing-desktop-hover')
      await call('Input.dispatchMouseEvent',{type:'mousePressed',x:770,y:400,button:'left',clickCount:1})
      await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:950,y:470,button:'left',buttons:1})
      assert.equal(await evaluate('document.querySelector(".landing-paper").dataset.dragging'),'true')
      await pause(250);await shot('landing-desktop-drag')
      await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:950,y:470,button:'left',clickCount:1})
      assert.equal(await evaluate('document.querySelector(".landing-paper").dataset.dragging'),undefined)
    }
    if(v.name==='mobile'){
      await call('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:190,y:300}]})
      await call('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:250,y:305}]})
      assert.equal(await evaluate('document.querySelector(".landing-paper").dataset.dragging'),'true')
      await pause(200);await shot('landing-mobile-touch-drag')
      await call('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
      await call('Input.synthesizeScrollGesture',{x:190,y:400,yDistance:-150,speed:300,gestureSourceType:'touch'})
      await wait('scrollY>0')
      await evaluate('scrollTo(0,0)')
    }
    await evaluate('scrollTo(0,innerHeight*.4)')
    await wait('Number(document.querySelector(".landing-entrance").style.getPropertyValue("--entrance-progress"))>.2')
    await shot('landing-'+v.name+'-transition')
    assert(await evaluate('scrollY>0'),'Scroll trapped')
    await evaluate('scrollTo(0,document.querySelector(".landing-spacer").offsetHeight+2)')
    await wait('location.hash==="#overview"&&!document.querySelector(".landing-hero")')
    await wait('scrollY===0')
    assert.equal(await evaluate('document.querySelectorAll(".product-workspace").length'),1)
    await evaluate('history.back()');await ready();await check()
    await evaluate('history.forward()');await wait('!document.querySelector(".landing-hero")')
    await evaluate('history.back()');await ready()
    await wait('document.activeElement.id==="landing-title"')
    await call('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End',windowsVirtualKeyCode:35})
    await call('Input.dispatchKeyEvent',{type:'keyUp',key:'End',code:'End',windowsVirtualKeyCode:35})
    await wait('!document.querySelector(".landing-hero")')
    journeys.push({viewport:v.name,webgl:true,entry_button_absent:true,native_scroll:true,keyboard_scroll:true,back_forward:true,dashboard_instances:1})
  }
  // Direct deep links must not request the optional renderer chunk.
  const start=assets.length
  await navigate('#research');await wait('document.body.innerText.includes("Run study")')
  assert(!assets.slice(start).some(p=>p.includes('paperRenderer')))
  await call('Page.reload');await wait('document.body.innerText.includes("Run study")')
  assert.equal(await evaluate('location.hash'),'#research')
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,mobile:false,deviceScaleFactor:1})
  await call('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]})
  const reducedStart=assets.length
  await navigate('');await wait('document.querySelector(".landing-paper")?.dataset.renderState==="fallback"')
  assert.equal(await evaluate('document.querySelectorAll(".landing-paper canvas").length'),0)
  assert(!assets.slice(reducedStart).some(p=>p.includes('paperRenderer')))
  await check();await shot('landing-reduced-motion')
  await call('Emulation.setEmulatedMedia',{features:[]});await ready()
  // Simulate document lifecycle signal; verify owned RAF is paused/resumed.
  await evaluate('Object.defineProperty(document,"hidden",{configurable:true,value:true});document.dispatchEvent(new Event("visibilitychange"))')
  await wait('document.querySelector(".landing-paper").dataset.renderState==="paused"')
  await evaluate('delete document.hidden;document.dispatchEvent(new Event("visibilitychange"))');await ready()
  // Actual WebGL context loss must dispose the canvas and preserve navigation.
  await evaluate('document.querySelector(".landing-paper canvas").getContext("webgl2").getExtension("WEBGL_lose_context").loseContext()')
  await wait('document.querySelector(".landing-paper").dataset.renderState==="fallback"&&!document.querySelector(".landing-paper canvas")')
  await check();await shot('landing-context-loss')
  await evaluate('scrollTo(0,document.querySelector(".landing-spacer").offsetHeight+2)');await wait('!document.querySelector(".landing-hero")')
  const injected=await call('Page.addScriptToEvaluateOnNewDocument',{source:'const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith("webgl")?null:original.call(this,type,...args)}'})
  await navigate('');await wait('document.querySelector(".landing-paper")?.dataset.renderState==="fallback"')
  await check();await shot('landing-no-webgl')
  await evaluate('scrollTo(0,document.querySelector(".landing-spacer").offsetHeight+2)');await wait('!document.querySelector(".landing-hero")')
  await call('Page.removeScriptToEvaluateOnNewDocument',{identifier:injected.identifier})
  assert.equal(errors.length,0,JSON.stringify(errors))
  const gates=await(await fetch('http://127.0.0.1:8054/api/workspace')).json()
  assert.equal(gates.production_gates.TRUST_GATE,'BLOCKED');assert.equal(gates.production_gates.OPPORTUNITY_GATE,'BLOCKED_BY_TRUST')
  const report={status:'PASS',journeys,requests,errors,screenshots,direct_route_refresh:true,reduced_motion_no_gpu:true,context_loss_fallback:true,webgl_unavailable_fallback:true,visibility_pause_resume:true,production_gates:gates.production_gates,execution_requests:0,renderer:'Chromium SwiftShader (software WebGL2; hardware performance not measured)'}
  await writeFile(join(directory,'landing-browser.json'),JSON.stringify(report,null,2))
  console.log(JSON.stringify({status:'PASS',journeys:journeys.length,requests:requests.length,execution_requests:0,evidence:directory}))
}catch(error){if(evaluate)await writeFile(join(directory,'landing-debug.json'),JSON.stringify({error:error.message,errors,requests,page:await evaluate('document.body.innerText')}).slice(0,150000));throw error}
finally{ws?.close();try{process.kill(-chrome.pid,'SIGTERM')}catch{}await pause(200);await rm(profile,{recursive:true,force:true})}
