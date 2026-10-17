const {chromium}=require(process.env.JARVIS_PLAYWRIGHT || "playwright");
const fs=require("fs");
(async()=>{
 const browser=await chromium.connectOverCDP("http://127.0.0.1:9223");
 const page=browser.contexts()[0].pages().find(p=>p.url().startsWith("http://127.0.0.1:8765"));
 await page.waitForFunction(()=>status&&!status.loading&&socket.readyState===WebSocket.OPEN);
 await page.evaluate(()=>{
   window.calendarActions=[];
   socket.addEventListener("message",event=>{
     const data=JSON.parse(event.data);if(data.type==="action"||data.type==="error")calendarActions.push(data);
   });
 });
 const title="Voice calendar verification";
 async function ask(text){
   await page.evaluate(text=>{cancelAudio();send("text",{text});},text);
   await page.waitForFunction(()=>busy||playing,{},{timeout:10000});
   await page.waitForFunction(()=>!busy&&!playing,{},{timeout:120000});
 }
 await ask("Use the calendar tool to create an event titled Voice calendar verification on 3 April 2030 from 10:00 AM to 10:30 AM India time, with no alert. Confirm it briefly.");
 const get=()=>page.evaluate(()=>api("calendar?start=2030-04-01T00:00:00Z&end=2030-05-01T00:00:00Z"));
 let events=await get(),event=events.events.find(e=>e.title===title);
 if(!event)throw Error("The model did not create the calendar event: "+JSON.stringify(await page.evaluate(()=>calendarActions)));
 if(event.remind_minutes!==-1)throw Error("No-alert request was not respected");
 const original=new Date(event.start_at).getTime();
 await ask("Move that same event one hour later. Keep its title, duration, and lack of alert unchanged. Use the calendar tool.");
 events=await get();event=events.events.find(e=>e.title===title);
 if(!event||event.remind_minutes!==-1||new Date(event.start_at).getTime()!==original+3600000)throw Error("The model did not reschedule the event correctly");
 await ask("Delete that Voice calendar verification event using the calendar tool.");
 events=await get();if(events.events.some(e=>e.title===title))throw Error("The model did not delete the event");
 const result={model:"jarvis-local:4b",createMoveDelete:true,actions:await page.evaluate(()=>calendarActions)};
 fs.writeFileSync("data/voice-calendar-verification.json",JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
