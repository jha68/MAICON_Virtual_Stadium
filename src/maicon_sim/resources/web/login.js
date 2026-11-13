document.querySelector('#login').addEventListener('submit',async event=>{
 event.preventDefault();const error=document.querySelector('#error'),button=event.target.querySelector('button');button.disabled=true;error.textContent='';
 try{const response=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-Maicon-Operator':'1'},body:JSON.stringify({password:document.querySelector('#password').value})});if(!response.ok)throw new Error((await response.json()).detail);location.replace('/');}catch(e){error.textContent=e.message||'로그인하지 못했습니다.';}finally{button.disabled=false;}
});
