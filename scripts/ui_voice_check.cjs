const {chromium}=require(process.env.JARVIS_PLAYWRIGHT || "playwright");
const fs=require("fs");
(async()=>{
 const browser=await chromium.launch({channel:"msedge",headless:true,args:[
   "--autoplay-policy=no-user-gesture-required","--use-fake-device-for-media-stream",
   "--use-fake-ui-for-media-stream","--use-file-for-fake-audio-capture="+require("path").resolve("data/silence.wav")]});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto("http://127.0.0.1:8765");
  await page.waitForFunction(()=>socket?.readyState===WebSocket.OPEN && status && !status.loading);
  await page.locator("#enable-voice").click();
  await page.waitForFunction(()=>armed && document.querySelector("#orb-state").textContent==="STANDBY");
  await page.evaluate(()=>{
    window.voiceAudit=[];
    const create=context.createBufferSource.bind(context);
    context.createBufferSource=()=>{
      const source=create(),start=source.start.bind(source),stop=source.stop.bind(source);
      const item={stopped:false};
      source.start=when=>{item.start=when;item.duration=source.buffer.duration;voiceAudit.push(item);start(when);};
      source.stop=(...args)=>{item.stopped=true;stop(...args);};
      source.addEventListener("ended",()=>item.end=context.currentTime);
      return source;
    };
  });
  await page.getByRole("button",{name:"Settings",exact:true}).click();
  await page.locator('select[name="kokoro_voice"]').selectOption("bm_fable");
  await page.getByRole("button",{name:"Test voice",exact:true}).click();
  await page.waitForFunction(()=>previewVoice && playing && audioPlayer.sources.size>0,{},{timeout:30000});
  const previewIsolation=await page.evaluate(()=>armed && previewVoice && status.settings.kokoro_voice==="bm_george");
  if(!previewIsolation)throw Error("Voice preview changed saved settings or disabled the microphone");
  await page.waitForFunction(()=>!playing && !previewVoice,{},{timeout:30000});
  const preview=await page.evaluate(()=>({audio:voiceAudit.splice(0),armed,savedVoice:status.settings.kokoro_voice}));
  if(!preview.armed || preview.savedVoice!=="bm_george")throw Error("Preview did not restore listening");
  await page.screenshot({path:"data/settings-voice-test.png",fullPage:true});
  await page.getByRole("button",{name:"Close panel",exact:true}).click();
  await page.getByRole("button",{name:"Turn microphone off",exact:true}).click();
  await page.getByRole("button",{name:"Type a request"}).click();
  await page.getByLabel("Request",{exact:true}).fill("Please reply with exactly these three sentences: Certainly, Captain. Your computer is ready for another productive day and all of the essential systems are running smoothly. I can help you find files, open applications, check the computer, and keep track of your reminders.");
  await page.getByRole("button",{name:"Send request",exact:true}).click();
  await page.waitForFunction(()=>voiceAudit.length>0,{},{timeout:90000});
  await page.waitForFunction(()=>!playing && !busy && voiceAudit.length>0,{},{timeout:60000});
  const reply=await page.evaluate(()=>({audio:voiceAudit,caption:document.querySelector("#response-caption").textContent}));
  for(const item of [...preview.audio,...reply.audio]){
    if(item.stopped || !item.end || item.end+0.1<item.start+item.duration)throw Error("Speech stopped before the audio buffer ended");
  }
  if(reply.audio.length<2)throw Error("The response did not exercise multiple audio chunks");
  const gaps=reply.audio.slice(1).map((item,index)=>+(item.start-reply.audio[index].start-reply.audio[index].duration).toFixed(3));
  if(gaps.some(gap=>Math.abs(gap)>.02))throw Error("Unexpected gap between buffered speech chunks: "+gaps);
  if(errors.length)throw Error(errors.join("; "));
  const result={pageErrors:errors,previewIsolation,preview,reply,gapsSeconds:gaps};
  fs.writeFileSync("data/ui-voice-verification.json",JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
