const {chromium}=require(process.env.JARVIS_PLAYWRIGHT || "playwright");
const fs=require("fs");
(async()=>{
 const browser=await chromium.connectOverCDP("http://127.0.0.1:9223");
 const page=browser.contexts()[0].pages().find(p=>p.url().startsWith("http://127.0.0.1:8765"));
 await page.reload();
 await page.waitForFunction(()=>status&&!status.loading&&socket.readyState===WebSocket.OPEN);
 await page.evaluate(async()=>{
   const current=await api("status");
   for(const item of current.reminders)if(item.text.startsWith("Reminder verification"))await api("reminders/"+item.id,{method:"DELETE"});
 });
 await page.locator("#calendar-today").click();
 // Existing reminders can be edited through the same agenda.
 await page.locator("#calendar-add").click();
 await page.locator('#calendar-form [name="title"]').fill("Reminder verification");
 await page.locator('#calendar-form [name="kind"]').selectOption("reminder");
 await page.getByRole("button",{name:"Save to calendar",exact:true}).click();
 await page.getByRole("button",{name:/Reminder verification/}).click();
 await page.locator('#calendar-form [name="title"]').fill("Reminder verification updated");
 await page.getByRole("button",{name:"Save changes",exact:true}).click();
 await page.getByRole("button",{name:/Reminder verification updated/}).click();
 await page.locator("#delete-event").click();
 const demo=await page.evaluate(async()=>{
   const start=new Date();start.setMinutes(start.getMinutes()+60);start.setSeconds(0,0);
   const end=new Date(start.getTime()+1800000);
   return api("calendar",{method:"POST",body:JSON.stringify({title:"Weekly planning",start_at:start.toISOString(),
     end_at:end.toISOString(),notes:"Review priorities and make room for the week.",remind_minutes:15})});
 });
 try {
   await page.evaluate(date=>calendar.focus(date),demo.start_at);
   await page.getByRole("button",{name:/Weekly planning/}).click();
   await page.locator('#calendar-form [name="notes"]').fill("Review priorities and make room for the week.");
   await page.getByRole("button",{name:"Save changes",exact:true}).click();
   const alert=await page.evaluate(async id=>{
     const date=new Date();const first=new Date(date.getFullYear(),date.getMonth(),1),last=new Date(date.getFullYear(),date.getMonth()+1,1);
     const result=await api("calendar?start="+encodeURIComponent(first.toISOString())+"&end="+encodeURIComponent(last.toISOString()));
     return result.events.find(e=>e.id===id).remind_minutes;
   },demo.id);
   if(alert!==15)throw Error("Editing changed a custom alert");
   await page.evaluate(()=>send("new_conversation"));
   await page.waitForFunction(()=>!playing&&!busy);
   await page.getByRole("button",{name:/Weekly planning/}).waitFor();
   fs.mkdirSync("docs/images",{recursive:true});
   await page.screenshot({path:"docs/images/jarvis-desktop.jpg",type:"jpeg",quality:86,fullPage:true});
   fs.copyFileSync("docs/images/jarvis-desktop.jpg",".runtime/portfolio-update/assets/jarvis.jpg");
   const original=await page.evaluate(()=>({width:innerWidth,height:innerHeight}));
   await page.setViewportSize({width:390,height:844});
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
   await page.screenshot({path:"data/calendar-mobile.png",fullPage:true});
   await page.setViewportSize(original);
   if(overflow)throw Error("Calendar caused mobile overflow");
   fs.writeFileSync("data/calendar-final-ui.json",JSON.stringify({reminderEdit:true,customAlertPreserved:true,mobileOverflow:false},null,2));
   console.log(JSON.stringify({reminderEdit:true,customAlertPreserved:true,mobileOverflow:false}));
 }finally{await page.evaluate(id=>api("calendar/"+id,{method:"DELETE"}),demo.id);}
 process.exit(0);
})().catch(e=>{console.error(e);process.exit(1);});
