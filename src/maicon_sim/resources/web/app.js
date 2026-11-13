import {ExperimentConsole} from './console.js';
import {ArenaMap, updateCatalog} from './arena-map.js';
const $=id=>document.getElementById(id), slots=['B-1','B-2','B-3','R-1','R-2','R-3'];
let state=null,selected='B-1',busy=false,world=null,view='2d',match=null,trails=new Map(),cameraURL=null;
const arenaMap=new ArenaMap($('map'));
const experiment=new ExperimentConsole(()=>state,()=>selected);
const phases={waiting:'세팅 중',ready:'참가팀 준비 중',running:'경기 진행',reporting:'최종 보고',finished:'경기 종료'};
for(const slot of slots){const b=document.createElement('button');b.className='robot'+(slot[0]==='R'?' red-team':'');b.dataset.slot=slot;b.innerHTML='<span class="status">대기</span><strong></strong><div class="hp"></div><small></small>';
 b.querySelector('strong').textContent=slot;for(let i=0;i<4;i++)b.querySelector('.hp').append(document.createElement('i'));b.onclick=()=>{selected=slot;render();};$('robots').append(b);}
function time(t){const s=t/100;return `${String(Math.floor(s/60)).padStart(2,'0')}:${(s%60).toFixed(2).padStart(5,'0')}`;}
function render(){if(!state)return;const s=state;$('phase').textContent=s.paused?'일시정지':phases[s.phase]||s.phase;$('clock').textContent=time(s.phase==='reporting'?s.reporting_elapsed_ticks:s.match_elapsed_ticks);$('match-id').textContent=s.match_id;
 $('lag').textContent=s.performance.max_lag_s.toFixed(2)+' s';$('drops').textContent=s.performance.frame_drops;
 for(const b of $('robots').children){const r=s.robots[b.dataset.slot];b.classList.toggle('active',b.dataset.slot===selected);b.querySelector('.status').textContent=r.ready?'준비 완료':'대기';b.querySelector('small').textContent=`HP ${r.hp}/4 · 탄약 ${r.ammo}`;[...b.querySelector('.hp').children].forEach((v,i)=>v.classList.toggle('filled',i<r.hp));}
 $('selected-slot').textContent=selected;$('camera-title').textContent=selected+' · 로봇 카메라';
 const allReady=Object.values(s.robots).every(r=>r.ready),allowed={ready:s.phase==='waiting',start:s.phase==='ready'&&allReady,pause:s.phase==='running'&&!s.paused,resume:s.phase==='running'&&s.paused,finish:s.phase==='running',reset:['waiting','ready','finished'].includes(s.phase)};
 for(const b of document.querySelectorAll('[data-action]'))b.disabled=busy||!allowed[b.dataset.action];
 $('hint').textContent=({waiting:'준비 시작 → 여섯 기체 준비 확인 → 자동 임무 시작',ready:'참가팀 프로세스가 센서를 확인하고 있습니다. 준비 완료 후 시작할 수 있습니다.',running:'경기 시간은 실제 시간으로 진행합니다.',reporting:'최대 30초의 최종 보고를 기다립니다.',finished:'점수가 저장됐습니다. 다음 경기 초기화로 세팅 단계에 돌아갈 수 있습니다.'})[s.phase];
 $('result').hidden=s.phase!=='finished';$('scores').hidden=!s.scores;if(s.scores){$('score-rows').replaceChildren(...slots.map(slot=>{const e=document.createElement('span');e.textContent=`${slot}  ${s.scores[slot].total}점`;return e;}));}
 updateCatalog($('asset-legend'),$('receiver-status'),s);experiment.update(s,selected);
 if(view==='2d')drawMap();else if(world)world.update(s,selected);
}
function drawMap(){arenaMap.update(state,selected,trails);}
async function poll(){try{const r=await fetch('/api/state');if(r.status===401){location.replace('/login');return;}if(!r.ok)throw Error(`HTTP ${r.status}`);state=await r.json();if(match!==state.match_id){trails.clear();match=state.match_id;}for(const [slot,r] of Object.entries(state.robots)){const t=trails.get(slot)||[],p=r.pose;if(!t.length||t.at(-1)[0]!==p.x_m||t.at(-1)[1]!==p.y_m)t.push([p.x_m,p.y_m]);if(t.length>350)t.shift();trails.set(slot,t);}$('connection').textContent='실시간 연결';$('connection').classList.add('online');render();}catch(e){$('connection').textContent='연결 재시도 중';$('connection').classList.remove('online');}setTimeout(poll,350);}
async function camera(){try{if(state&&!state.capabilities.rgb)throw Error('2D 모드에서는 RGB 카메라를 제공하지 않습니다.');const requestedSlot=selected,requestedMatch=state?.match_id;const r=await fetch(`/api/camera/${requestedSlot}.jpg${requestedMatch?'?match_id='+encodeURIComponent(requestedMatch):''}`,{cache:'no-store'});if(!r.ok)throw Error('카메라 프레임을 기다립니다');const blob=await r.blob();if(requestedSlot!==selected||requestedMatch!==state?.match_id)return setTimeout(camera,500);const next=URL.createObjectURL(blob);$('camera').src=next;if(cameraURL)URL.revokeObjectURL(cameraURL);cameraURL=next;$('camera-empty').hidden=true;$('camera-stamp').textContent='캡처 tick '+r.headers.get('X-Sim-Captured-Tick');}catch(e){$('camera-empty').hidden=false;$('camera-empty').textContent=e.message;}setTimeout(camera,500);}
for(const b of document.querySelectorAll('[data-action]'))b.onclick=async()=>{if(b.dataset.action==='reset'&&!confirm('경기 상태를 초기화하고 세팅 단계로 돌아갈까요?'))return;busy=true;render();$('notice').textContent='처리 중…';try{const r=await fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-Maicon-Operator':'1'},body:JSON.stringify({action:b.dataset.action})});const value=await r.json();if(!r.ok)throw Error(value.detail||'조작 실패');$('notice').textContent='처리됐습니다.';}catch(e){$('notice').textContent=e.message;}finally{busy=false;render();}};
$('view-2d').onclick=()=>{view='2d';$('map').hidden=false;$('world').hidden=true;$('view-2d').classList.add('selected');$('view-3d').classList.remove('selected');$('view-help').textContent='로봇 카드를 눌러 카메라를 선택하세요';render();};
$('view-3d').onclick=async()=>{if(!state)return;try{if(!world){const {World}=await import('/assets/world.js');world=new World($('world'));}view='3d';$('map').hidden=true;$('world').hidden=false;$('view-3d').classList.add('selected');$('view-2d').classList.remove('selected');$('view-help').textContent='드래그로 회전 · 스크롤로 확대/축소';render();}catch(e){$('notice').textContent='브라우저 3D를 사용할 수 없습니다. 2D 지도와 로봇 카메라는 계속 사용할 수 있습니다.';}};
$('world').addEventListener('textureerror',()=>{$('notice').textContent='일부 경기장 이미지를 불러오지 못했습니다. 연결을 확인하고 새로고침하세요.';});
window.addEventListener('resize',render);poll();camera();
