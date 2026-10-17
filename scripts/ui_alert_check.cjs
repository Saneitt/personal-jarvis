const {chromium}=require(process.env.JARVIS_PLAYWRIGHT || "playwright");
const fs=require("fs");
(async()=>{
 const browser=await chromium.connectOverCDP("http://127.0.0.1:9223");
 const context=browser.contexts()[0],page=context.pages().find(p=>p.url().startsWith("http://127.0.0.1:8765"));
 const cdp=await context.newCDPSession(page);
 const ready=await cdp.send("Runtime.evaluate",{expression:"new Promise((resolve,reject)=>{const started=Date.now();const timer=setInterval(()=>{if(typeof status!=='undefined'&&status&&!status.loading&&socket.readyState===WebSocket.OPEN){clearInterval(timer);resolve(navigator.userActivation.hasBeenActive);}else if(Date.now()-started>30000){clearInterval(timer);reject(Error('Speech did not load'));}},100);})",awaitPromise:true,userGesture:false,returnByValue:true});
 if(ready.result.value)throw Error("Test requires an untouched native page");
 const result=await cdp.send("Runtime.evaluate",{expression:"(async()=>{const before=navigator.userActivation.hasBeenActive;await api('reminders',{method:'POST',body:JSON.stringify({text:'Alert verification',due_at:new Date(Date.now()+3000).toISOString()})});return await new Promise((resolve,reject)=>{let began=false;const started=Date.now();const timer=setInterval(()=>{if(playing&&context?.state==='running'&&audioPlayer.sources.size)began=true;if(began&&!playing){clearInterval(timer);resolve({automaticAlertPlayed:true,userGesture:before,microphoneArmed:armed});}else if(Date.now()-started>30000){clearInterval(timer);reject(Error('Alert audio did not complete'));}},100);});})()",awaitPromise:true,userGesture:false,returnByValue:true});
 if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));
 fs.writeFileSync("data/automatic-alert-verification.json",JSON.stringify(result.result.value,null,2));
 console.log(JSON.stringify(result.result.value));process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
