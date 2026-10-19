
const ws=new WebSocket(process.argv[2]);let id=0;const p=new Map();
const send=(m,q)=>new Promise(r=>{const i=++id;p.set(i,r);ws.send(JSON.stringify({id:i,method:m,params:q||{}}))});
ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id&&p.has(m.id)){p.get(m.id)(m.result);p.delete(m.id)}});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
ws.addEventListener('open',async()=>{await send('Page.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:760,height:240,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:process.argv[3]});await sleep(2500);
 const s=await send('Page.captureScreenshot',{format:'png'});
 require('fs').writeFileSync(process.argv[4],Buffer.from(s.data,'base64'));
 ws.close();process.exit(0);});
