document.querySelector('#logout').addEventListener('click',async()=>{await fetch('/auth/logout',{method:'POST',headers:{'X-Maicon-Operator':'1'}});location.replace('/login');});
