const $=id=>document.getElementById(id);
const slots=['B-1','B-2','B-3','R-1','R-2','R-3'];
const names={patrol:'순찰',baseline:'자율 임무',idle:'대기',blocker:'통로 방어',capture_runner:'거점 이동'};

export class ExperimentConsole {
  constructor(state,selected){
    this.state=state;this.selected=selected;this.chain=Promise.resolve();this.held=null;this.activeSlot=null;this.droneURL=null;
    for(const slot of slots){const label=document.createElement('label');label.textContent=slot;const input=document.createElement('select');input.dataset.slot=slot;input.setAttribute('aria-label',slot+' 정책');for(const [key,name] of Object.entries(names)){const option=document.createElement('option');option.value=key;option.textContent=name;input.append(option);}label.append(input);$('team-policies').append(label);}
    $('policy').addEventListener('change',()=>{for(const input of $('team-policies').querySelectorAll('select'))input.value=$('policy').value;});
    for(const button of document.querySelectorAll('[data-drive]')){
      button.onpointerdown=event=>{event.preventDefault();if(button.disabled)return;button.setPointerCapture(event.pointerId);this.release();this.activeSlot=selected();this.held=button;button.classList.add('held');const [v,w]=button.dataset.drive.split(',').map(Number);this.drive(v,w);this.timer=setInterval(()=>this.drive(v,w),100);};
      button.onpointerup=button.onpointercancel=()=>this.release();
    }
    window.addEventListener('blur',()=>this.release());
    document.addEventListener('visibilitychange',()=>{if(document.hidden)this.release();});
    $('manual-release').onclick=()=>this.release(true);
    $('manual-fire').onclick=()=>this.send('fire',{});
    for(const axis of ['pan','tilt'])$('manual-'+axis).oninput=()=>{$(axis+'-value').textContent=$('manual-'+axis).value;clearTimeout(this.aimTimer);this.aimTimer=setTimeout(()=>this.send('gimbal',{pan:Number($('manual-pan').value),tilt:Number($('manual-tilt').value),speed:60,acc:20}),90);};
    this.pollEvidence();
  }
  policies(){return Object.fromEntries([...$('team-policies').querySelectorAll('select')].map(input=>[input.dataset.slot,input.value]));}
  send(command,parameters={},slot=this.selected()){
    const match=this.state()?.match_id;
    this.chain=this.chain.catch(()=>{}).then(async()=>{
      if(match!==this.state()?.match_id)return;
      const response=await fetch('/api/control/'+slot,{method:'POST',headers:{'Content-Type':'application/json','X-Maicon-Operator':'1'},body:JSON.stringify({command,parameters,match_id:match})});
      const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'제어 요청을 확인하세요.');
      $('manual-message').textContent=value.message||'제어 명령 접수';
    }).catch(error=>{$('manual-message').textContent=error.message;});
    return this.chain;
  }
  drive(v,w){if(this.drivePending)return;this.drivePending=true;this.send('cmd_vel',{linear_x_mps:v,angular_z_rps:w},this.activeSlot).finally(()=>{this.drivePending=false;});}
  release(force=false){clearInterval(this.timer);if(this.held||force){this.held?.classList.remove('held');this.send('release',{},this.activeSlot||this.selected());}this.held=null;this.activeSlot=null;}
  update(state,slot){
    if(this.lastSlot!==slot||this.lastMatch!==state.match_id){this.release();clearTimeout(this.aimTimer);this.lastSlot=slot;this.lastMatch=state.match_id;this.lastDroneStamp=null;$('drone-image').removeAttribute('src');$('drone-detail').textContent='새 프레임 대기';if(this.droneURL){URL.revokeObjectURL(this.droneURL);this.droneURL=null;}}
    const enabled=state.phase==='running'&&!state.paused;
    for(const control of document.querySelectorAll('.drive-pad button,#manual-pan,#manual-tilt'))control.disabled=!enabled;
    if(!enabled)this.release();
    for(const input of $('team-policies').querySelectorAll('select'))input.disabled=state.phase!=='waiting';
    $('build-info').textContent=`${state.scenario_id} · ${state.profile_id} · revision ${state.build_revision.slice(0,12)} · M1 ${state.llm_mode}`;
    $('manual-state').textContent=state.manual_slots?.includes(slot)?'수동 제어 중':'자동 정책';
    $('run-kind').textContent=state.manual_interventions?'수동 개입 포함':'자율 실행';
    $('report-title').textContent=slot+' · 보고·관측';
    for(const mission of ['m1','m3','m6'])$('report-'+mission).textContent=state.reports?.[slot]?.[mission]?JSON.stringify(state.reports[slot][mission],null,2):'아직 제출 없음';
  }
  async pollEvidence(){
    const slot=this.selected(),match=this.state()?.match_id;
    try{
      if(match){
        const response=await fetch('/api/participant/'+slot);if(response.ok){const value=await response.json();if(slot===this.selected()&&match===this.state()?.match_id)$('participant-diagnostics').textContent=JSON.stringify(value.diagnostics||{},null,2);}
        const drone=await fetch('/api/drone/'+slot+'.jpg');
        if(slot===this.selected()&&match===this.state()?.match_id){
          if(drone.ok){const stamp=drone.headers.get('X-Captured-At'),interval=drone.headers.get('X-Frame-Interval-S');$('drone-status').textContent=`${interval}초 간격`;$('drone-detail').textContent='촬영 '+stamp+(stamp===this.lastDroneStamp?' · 이전 정상 프레임':'');if(stamp!==this.lastDroneStamp){const url=URL.createObjectURL(await drone.blob());$('drone-image').src=url;if(this.droneURL)URL.revokeObjectURL(this.droneURL);this.droneURL=url;this.lastDroneStamp=stamp;}}
          else{$('drone-status').textContent=drone.status===403?'시설 3개 피격 · 수신 중단':drone.status===409?'경기 중 제공':'프레임 대기';}
        }
      }
    }catch{}
    setTimeout(()=>this.pollEvidence(),1000);
  }
}
