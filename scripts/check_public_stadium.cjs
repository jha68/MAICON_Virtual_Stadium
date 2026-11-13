// Read-only public verification. Password is loaded from a private file; never log requests/cookies.
const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const passwordFile=process.env.MAICON_PUBLIC_PASSWORD_FILE||'artifacts/codex-domain-session/private/web.password';
 if(fs.statSync(passwordFile).mode&0o077)throw Error('Password file must be private');
 const password=fs.readFileSync(passwordFile,'utf8').trim();
 const base='https://maicon.junununseo.com';
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_BIN||'/usr/bin/chromium',headless:true,args:['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader'],proxy:{server:process.env.HTTPS_PROXY||process.env.https_proxy,bypass:'127.0.0.1,localhost'}});
 const context=await browser.newContext({viewport:{width:1600,height:1200}}),page=await context.newPage(),errors=[],bad=[];
 
 page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=500)bad.push({path:new URL(r.url()).pathname,status:r.status()});});
 try{
  await page.goto(base+'/login');await page.fill('#password',password);await page.click('#login button');await page.waitForSelector('#connection.online',{timeout:60000});
  const r=await context.request.get(base+'/api/state');const state=await r.json();
  const localResponse=await context.request.get('http://127.0.0.1:18080/api/state',{headers:{Authorization:'Basic '+Buffer.from('admin:'+password).toString('base64')}});
  if(!localResponse.ok())throw Error('Local state unavailable');
  const local=await localResponse.json();
  if(r.headers()['x-maicon-compute']!=='codex-cloud'||state.match_id!==local.match_id||state.build_revision!==local.build_revision)throw Error('Public build differs from local');
  if(state.arena.base_panels?.length!==6)throw Error('Missing M5 panels');
  if(state.scenario_id!=='reference_stadium'||state.boxes.length!==20||Object.keys(state.visual_assets).length!==16||Object.keys(state.facility_signals).length!==6||state.m1_mode!=='direct_order'||state.m6_mode!=='mock')throw Error('Unexpected reference map');
  await page.waitForFunction(()=>document.querySelectorAll('.asset-card img').length===16&&[...document.querySelectorAll('.asset-card img')].every(i=>i.complete&&i.naturalWidth>0),null,{timeout:60000});
  await page.waitForFunction(()=>document.querySelector('#camera').naturalWidth===640,null,{timeout:60000});
  fs.mkdirSync('artifacts/evidence',{recursive:true});
  await page.screenshot({path:'artifacts/evidence/public-reference-2d.png',fullPage:true});
  await page.click('#view-3d');await page.waitForSelector('#world canvas',{state:'visible',timeout:60000});await page.waitForTimeout(3000);
  const webgl=await page.locator('#world canvas').evaluate(canvas=>({width:canvas.width,height:canvas.height,context:!!canvas.getContext('webgl2')}));
  if(webgl.width<100||!webgl.context)throw Error('WebGL unavailable');
  await page.locator('#world canvas').screenshot({path:'artifacts/evidence/public-reference-webgl.png'});
  await page.screenshot({path:'artifacts/evidence/public-reference-3d.png',fullPage:true});
  const cameras=[];for(const slot of ['B-1','B-2','B-3','R-1','R-2','R-3']){const image=await context.request.get(base+'/api/camera/'+slot+'.jpg');if(image.status()!==200)throw Error('Camera unavailable '+slot);cameras.push({slot,status:image.status(),bytes:(await image.body()).length});}
  if(await page.locator('#change-password,#password-form,#logout').count())throw Error('Removed controls restored');
  if(errors.length||bad.length)throw Error('Browser errors');
  fs.writeFileSync('artifacts/public-stadium-evidence.json',JSON.stringify({status:'passed',url:base,compute:r.headers()['x-maicon-compute'],match_id:state.match_id,phase:state.phase,revision:state.build_revision,scenario_id:state.scenario_id,boxes:20,images:16,basePanels:6,receivers:6,m1_mode:state.m1_mode,m6_mode:state.m6_mode,passwordPreserved:true,tlsVerification:true,operatorCommandsSent:0,webgl,cameras,browserErrors:errors,serverErrors:bad},null,2));
  console.log('Public desktop check passed: same password, build, match, map, 16 textures, 6 receivers, WebGL and all 6 RGB cameras. No match commands sent.');
 }finally{await browser.close();}
})().catch(e=>{console.error('Public desktop check failed: '+e.name);process.exit(1)});
