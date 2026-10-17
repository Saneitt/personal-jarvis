"use strict";
const $ = s => document.querySelector(s);
const token = $('meta[name="jarvis-token"]').content;
const esc = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let socket, stream, context, micNode, sourceNode, zeroGain;
let armed = false, muted = false, playing = false, busy = false, awake = false;
let previewVoice = false;
let turn = 0, status, approvalId, panel = "", panelOpener, toastTimer;
let retryTimer, stopped = false, connectionReady;
const modelLabel = name => name === "jarvis-local:4b" ? "Qwen3.5 · 4B" : name;
function toast(message) {
  $("#toast").textContent = message; $("#toast").hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $("#toast").hidden = true, 6500);
}
function phase(name, label) {
  if (playing && !["listening","error"].includes(name)) return;
  document.body.dataset.phase = name;
  $("#voice-state").textContent = label;
  $("#orb-state").textContent = name.toUpperCase();
}
function send(type, payload = {}) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type, ...payload}));
}
async function api(path, options = {}) {
  const response = await fetch("/api/" + path, { ...options,
    headers: {"Content-Type":"application/json", "X-Jarvis-Token":token, ...(options.headers || {})} });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "Request failed");
  return body;
}
function readyState() {
  if (playing || busy) return;
  phase(armed ? (awake ? "listening" : "standby") : "idle",
    armed ? (awake ? "I'm listening, Captain" : "Say “Hey Jarvis”") : "Microphone off");
}
async function ensureContext() {
  if (!context || context.state === "closed") context = new AudioContext();
  if (context.state === "suspended") await context.resume();
  return context;
}
const audioPlayer = new JarvisAudioPlayer(ensureContext, active => {
  playing = active;
  if ($("#voice-test-status") && previewVoice) $("#voice-test-status").textContent = active ? "Playing sample…" : "Sample finished.";
  $("#stop-response").hidden = !active;
  send("playback", {playing:active, turn});
  if (active) {
    document.body.dataset.phase = "speaking";
    $("#voice-state").textContent = "At your service, sir";
    $("#orb-state").textContent = "SPEAKING";
  } else { previewVoice = false; readyState(); }
}, error => toast("Audio could not play: " + error.message));
function cancelAudio() {
  audioPlayer.cancel();
  previewVoice = false;
  playing = false;
  $("#stop-response").hidden = true;
}
async function chime() {
  if (muted || !context) return;
  const oscillator = context.createOscillator(), gain = context.createGain();
  oscillator.type = "sine"; oscillator.frequency.value = 620;
  gain.gain.setValueAtTime(0.035, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + .13);
  oscillator.connect(gain); gain.connect(context.destination);
  oscillator.start(); oscillator.stop(context.currentTime + .14);
}
function connect() {
  connectionReady = new Promise((resolve, reject) => {
    socket = new WebSocket("ws://" + location.host + "/ws", ["jarvis", token]);
    socket.onopen = () => { $("#connection").textContent = "Connected locally"; resolve(); };
    socket.onmessage = event => {
      const data = JSON.parse(event.data);
      if (data.type === "interrupted") {
        turn = data.turn; cancelAudio(); previewVoice = data.reason === "voice_preview"; busy = false; return;
      }
      if (data.turn != null && data.turn < turn) return;
      if (data.turn != null) turn = data.turn;
      switch (data.type) {
        case "connected": readyState(); break;
        case "phase":
          if (data.phase === "listening") awake = true;
          if (data.phase === "standby") awake = false;
          busy = ["thinking","working","transcribing"].includes(data.phase);
          phase(data.phase, data.label); break;
        case "wake": awake = true; chime(); break;
        case "heard": $("#heard-caption").textContent = "HEARD · " + data.text; $("#response-caption").textContent = ""; break;
        case "caption": $("#response-caption").textContent = data.text; break;
        case "audio": if (!muted || previewVoice) { audioPlayer.enqueue(data.wav); if (data.final) audioPlayer.finish(); } break;
        case "done": audioPlayer.finish(); if (!playing) previewVoice = false; busy = false; awake = !!data.awake; readyState(); refresh(); break;
        case "metrics": $("#latency").textContent = data.tokens_per_second + " tokens/s · first word " + data.first_token_seconds + "s"; break;
        case "approval":
          approvalId = data.id; $("#approval").hidden = false;
          $("#approval-title").textContent = data.title; $("#approval-detail").textContent = data.detail; break;
        case "approval_cleared": approvalId = null; $("#approval").hidden = true; break;
        case "action": if (data.name==="calendar" && data.result?.focus_date) calendar.focus(data.result.focus_date); refresh(); break;
        case "reminder": toast("Reminder: " + data.text); refresh(); break;
        case "error":
          if (previewVoice && !playing) {
            previewVoice = false; busy = false;
            if ($("#voice-test-status")) $("#voice-test-status").textContent = "Sample unavailable.";
          }
          toast(data.message); phase("error", data.message); break;
      }
    };
    socket.onerror = () => reject(new Error("Local connection failed"));
    socket.onclose = event => {
      disableMicrophone(false); cancelAudio(); previewVoice = false; busy = false;
      $("#connection").textContent = "Disconnected";
      phase("error", event.code === 4409 ? "Already open in another window" : "Local connection lost");
      if (!stopped && ![4403,4409].includes(event.code)) retryTimer = setTimeout(connect, 2500);
      if (event.code === 4403) toast("Jarvis restarted. Refresh this window to reconnect.");
    };
  });
  connectionReady.catch(() => {});
}
async function enableMicrophone(listenNow = false) {
  if (armed) { if (listenNow) {cancelAudio(); send("listen");} return; }
  try {
    await connectionReady;
    if (!navigator.mediaDevices?.getUserMedia) throw new Error("Use Edge or Chrome on localhost for microphone access.");
    await ensureContext();
    stream = await navigator.mediaDevices.getUserMedia({audio:{
      echoCancellation:true, noiseSuppression:true, autoGainControl:true, channelCount:1
    }, video:false});
    await context.audioWorklet.addModule("/static/audio-worklet.js");
    sourceNode = context.createMediaStreamSource(stream);
    micNode = new AudioWorkletNode(context, "jarvis-pcm");
    zeroGain = context.createGain(); zeroGain.gain.value = 0;
    sourceNode.connect(micNode); micNode.connect(zeroGain); zeroGain.connect(context.destination);
    micNode.port.onmessage = event => {
      if (armed && !previewVoice && socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < 64000) socket.send(event.data);
      const values = new Int16Array(event.data);
      let sum=0; for(const sample of values) sum += sample*sample;
      const level=Math.min(1, Math.sqrt(sum/values.length)/4500);
      $(".voice-stage").style.setProperty("--level", level.toFixed(3));
    };
    armed = true;
    stream.getAudioTracks()[0].onended = () => disableMicrophone();
    $("#enable-voice").textContent = "Speak to Jarvis ↗";
    $("#voice-button").setAttribute("aria-label","Speak to Jarvis");
    $("#mic-off").hidden = false; $("#mic-dot").classList.add("live");
    $("#privacy-status").textContent = "Microphone on · listening locally";
    send("arm");
    if (listenNow) send("listen");
  } catch(error) {
    disableMicrophone();
    toast(error.name === "NotAllowedError" ? "Allow microphone access in your browser, then enable voice again." : error.message);
    phase("error", "Microphone unavailable");
  }
}
function disableMicrophone(notify = true) {
  armed = false; awake = false;
  if (stream) for (const track of stream.getTracks()) {track.onended = null; track.stop();}
  stream = null;
  for (const node of [sourceNode,micNode,zeroGain]) if (node) try {node.disconnect();} catch {}
  sourceNode = micNode = zeroGain = null;
  $("#enable-voice").innerHTML = "Enable voice <span>↗</span>";
  $("#voice-button").setAttribute("aria-label","Enable voice and speak");
  $("#mic-off").hidden = true; $("#mic-dot").classList.remove("live");
  $("#privacy-status").textContent = "Microphone off · local processing";
  $(".voice-stage").style.setProperty("--level", 0);
  if (notify) {cancelAudio(); send("disarm");}
}
async function refresh() {
  try {
    status = await api("status");
    calendar.refresh();
    $("#model-name").textContent = modelLabel(status.settings.model);
    $("#voice-name").textContent = status.settings.tts_engine === "kokoro" ? status.settings.kokoro_voice.replace("bm_","") + " · Kokoro" : "Alan · Piper";
    $("#greeting").textContent = "At your service, " + status.settings.owner_name + ".";
    $("#brain-status").classList.toggle("ready", status.model.available);
    $("#stt-status").classList.toggle("ready", status.speech.stt);
    $("#tts-status").classList.toggle("ready", status.speech.tts);
    const notes=[];
    if (status.loading) notes.push("Preparing local speech engines…");
    if (status.warming) notes.push("Loading the local brain into memory…");
    if (!status.model.connected) notes.push("Model server offline. Restart using Launch Jarvis.");
    else if (!status.model.available) notes.push("The selected model is not downloaded. Run Setup Jarvis.");
    if (!status.loading && (!status.speech.stt || !status.speech.tts)) notes.push("Speech models need setup.");
    $("#setup-note").textContent = notes.join(" ");
    $("#setup-note").hidden = !notes.length;
    $("#reminder-count").textContent = status.reminders.length;
    $("#reminders").innerHTML = status.reminders.length ? status.reminders.map(r =>
      '<div class="reminder-entry"><p>'+esc(r.text)+'<small>'+esc(new Date(r.due*1000).toLocaleString([], {weekday:"short",hour:"numeric",minute:"2-digit"}))+
      '</small></p><button data-cancel-reminder="'+r.id+'" aria-label="Cancel reminder">×</button></div>').join("") : '<p class="empty-copy">A clear slate, sir.</p>';
    for(const button of document.querySelectorAll("[data-cancel-reminder]")) button.onclick = async () => {await api("reminders/"+button.dataset.cancelReminder,{method:"DELETE"});refresh();};
    const action=status.actions[0];
    if(action) {
      let args, result; try {args=JSON.parse(action.arguments);result=JSON.parse(action.result);}catch {args={};result={};}
      $("#last-action").textContent = (result.error ? "Could not complete: " : result.cancelled ? "Cancelled: " : "") + action.name + " · " + (args.action || args.reason || "command");
    }
  } catch(error) { $("#setup-note").hidden=false; $("#setup-note").textContent=error.message; }
}
function closePanel() {
  $("#detail-panel").hidden=true; $("#panel-backdrop").hidden=true; panel="";
  panelOpener?.focus();
}
function localDateInput(value) {
  const date=new Date(value);return [date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-")+"T"+[date.getHours(),date.getMinutes()].map(n=>String(n).padStart(2,"0")).join(":");
}
async function openCalendarEditor(event,date) {
  panelOpener=document.activeElement;panel="calendar";
  $("#detail-panel").hidden=false;$("#panel-backdrop").hidden=false;
  const reminder=event?.kind==="reminder";
  $("#panel-title").textContent=event?(reminder?"A timely nudge.":"On your calendar."):"Make a little time.";
  $("#close-panel").focus();
  const start=event?new Date(event.start_at):new Date(date);
  if(!event){start.setHours(Math.max(9,new Date().getHours()+1),0,0,0);}
  const end=event?.end_at?new Date(event.end_at):new Date(start.getTime()+3600000);
  const alerts=[[-1,"No alert"],[0,"At the start"],[5,"5 minutes before"],[10,"10 minutes before"],[30,"30 minutes before"],[60,"1 hour before"],[1440,"1 day before"]];
  if(event && !alerts.some(([value])=>value===event.remind_minutes) && !reminder) alerts.push([event.remind_minutes,event.remind_minutes+" minutes before"]);
  $("#panel-content").innerHTML='<form id="calendar-form"><p class="panel-intro">Saved on this PC. Alerts sound while Jarvis is open.</p>'+
    '<label class="setting">Title<input name="title" maxlength="200" required value="'+esc(event?.title||"")+'"></label>'+
    (!event?'<label class="setting">Kind<select name="kind"><option value="event">Calendar event</option><option value="reminder">Reminder</option></select></label>':'')+
    '<label class="setting">Starts<input name="start_at" type="datetime-local" required value="'+localDateInput(start)+'"></label>'+
    (!reminder?'<label class="setting" id="event-end-setting">Ends<input name="end_at" type="datetime-local" required value="'+localDateInput(end)+'"></label>'+
    '<label class="setting check" id="event-day-setting"><input name="all_day" type="checkbox" '+(event?.all_day?'checked':'')+'><span>All day</span></label>'+
    '<label class="setting" id="event-notes-setting">Notes<textarea name="notes" maxlength="2000">'+esc(event?.notes||"")+'</textarea></label>'+
    '<label class="setting" id="event-alert-setting">Alert<select name="remind_minutes">'+alerts.map(([value,label])=>'<option value="'+value+'" '+(value===(event?.remind_minutes??10)?'selected':'')+'>'+label+'</option>').join("")+'</select></label>':'')+
    '<div class="save-row">'+('<button class="primary-button">Save '+(event?'changes':'to calendar')+'</button>')+(event?'<button type="button" id="delete-event" class="secondary-button">'+(reminder?'Cancel reminder':'Delete event')+'</button>':'')+'</div></form>';
  const form=$("#calendar-form");
  if(form.elements.kind)form.elements.kind.onchange=()=>{
    const isReminder=form.elements.kind.value==="reminder";
    for(const id of ["event-end-setting","event-day-setting","event-notes-setting","event-alert-setting"])$("#"+id).hidden=isReminder;
    form.elements.end_at.required=!isReminder;
  };
  form.onsubmit=async e=>{
    e.preventDefault();
    try {
      const start=new Date(form.elements.start_at.value);
      if(reminder || form.elements.kind?.value==="reminder"){
        await api("reminders"+(event?"/"+event.id:""),{method:event?"PUT":"POST",body:JSON.stringify({text:form.elements.title.value,due_at:start.toISOString()})});
      }else{
        let end=new Date(form.elements.end_at.value);
        if(form.elements.all_day.checked){
          start.setHours(0,0,0,0);end.setHours(0,0,0,0);
          if(end<=start){end=new Date(start);end.setDate(end.getDate()+1);}
        }
        await api("calendar"+(event?"/"+event.id:""),{method:event?"PUT":"POST",body:JSON.stringify({
          title:form.elements.title.value,start_at:start.toISOString(),end_at:end.toISOString(),
          all_day:form.elements.all_day.checked,notes:form.elements.notes.value,
          remind_minutes:Number(form.elements.remind_minutes.value)})});
      }
      closePanel();calendar.focus(start);refresh();toast("Safely on your calendar.");
    }catch(error){toast(error.message);}
  };
  if(event)$("#delete-event").onclick=async()=>{
    try{await api((reminder?"reminders/":"calendar/")+event.id,{method:"DELETE"});closePanel();refresh();toast(reminder?"Reminder cancelled.":"Event removed.");}catch(error){toast(error.message);}
  };
}
const calendar = new JarvisCalendar(api,openCalendarEditor,error=>toast("Calendar: "+error.message));
async function openPanel(name) {
  panelOpener=document.activeElement; panel=name;
  $("#detail-panel").hidden=false;$("#panel-backdrop").hidden=false;
  $("#panel-title").textContent={settings:"Make yourself at home.",memory:"What I remember.",activity:"Action record.",fallback:"A quiet word."}[name];
  $("#panel-content").innerHTML='<p class="panel-intro">One moment…</p>';$("#close-panel").focus();
  try {
    if(name==="fallback"){
      $("#panel-content").innerHTML='<p class="panel-intro">For when speaking is inconvenient. Replies still come through Jarvis.</p><form id="request-form"><textarea id="typed-request" class="fallback-input" maxlength="6000" aria-label="Request" placeholder="What can I do for you, sir?"></textarea><button class="primary-button">Send request</button></form>';
      $("#typed-request").focus();
      $("#request-form").onsubmit=async event=>{event.preventDefault();const text=$("#typed-request").value.trim();if(!text)return;await ensureContext();cancelAudio();send("text",{text});closePanel();};
    }else if(name==="memory"){
      const memories=await api("memory"); if(panel!==name)return;
      $("#panel-content").innerHTML='<p class="panel-intro">Preferences you ask me to remember, stored on this PC.</p>'+
        memories.map(m=>'<article class="memory-card"><div><h3>'+esc(m.text)+'</h3></div><button data-forget="'+m.id+'">Forget</button></article>').join("")+
        '<form id="memory-form" class="memory-form"><label for="new-memory">Add a preference</label><div><input id="new-memory" maxlength="500" required><button class="primary-button">Save</button></div></form>';
      document.querySelectorAll("[data-forget]").forEach(b=>b.onclick=async()=>{await api("memory/"+b.dataset.forget,{method:"DELETE"});openPanel("memory");});
      $("#memory-form").onsubmit=async e=>{e.preventDefault();await api("memory",{method:"POST",body:JSON.stringify({text:$("#new-memory").value})});openPanel("memory");};
    }else if(name==="activity"){
      const actions=await api("activity");if(panel!==name)return;
      $("#panel-content").innerHTML='<p class="panel-intro">Real tool results, including failures. File overwrite backups stay in the local data folder.</p>'+
      (actions.length?actions.map(a=>'<article class="activity-entry"><span class="eyebrow">'+esc(new Date(a.created).toLocaleString())+'</span><h3>'+esc(a.name)+'</h3><details><summary>Arguments and result</summary><pre>'+esc(a.arguments)+'\n\n'+esc(a.result)+'</pre></details></article>').join(""):'<p class="empty-copy">No actions yet, sir.</p>');
    }else if(name==="settings"){
      await refresh();if(panel!==name||!status)return;
      const s=status.settings, models=status.model.models.length?status.model.models:[s.model];
      $("#panel-content").innerHTML='<form id="settings-form"><p class="panel-intro">Tune the conversation to your room and your pace.</p>'+
        '<label class="setting">What should I call you?<input name="owner_name" value="'+esc(s.owner_name)+'" maxlength="60"></label>'+
        '<label class="setting">Local brain<select name="model">'+models.map(m=>'<option value="'+esc(m)+'" '+(m===s.model?'selected':'')+'>'+esc(modelLabel(m))+'</option>').join("")+'</select><small>Install another model with the download script, then choose it here.</small></label>'+
        '<label class="setting">Pause before replying (milliseconds)<input name="silence_ms" type="number" min="300" max="2000" step="100" value="'+s.silence_ms+'"><small>Increase this if Jarvis interrupts your pauses.</small></label>'+
        '<label class="setting">Follow-up listening (seconds)<input name="follow_up_seconds" type="number" min="5" max="300" value="'+s.follow_up_seconds+'"></label>'+
        '<label class="setting">Speech engine<select name="tts_engine"><option value="kokoro" '+(s.tts_engine==='kokoro'?'selected':'')+'>Kokoro · natural</option><option value="piper" '+(s.tts_engine==='piper'?'selected':'')+'>Piper · lightweight</option></select></label>'+
        '<label class="setting">British voice<select name="kokoro_voice">'+["bm_george","bm_lewis","bm_daniel","bm_fable"].map(v=>'<option value="'+v+'" '+(v===s.kokoro_voice?'selected':'')+'>'+v.replace("bm_","")+'</option>').join("")+'</select></label>'+
        '<label class="setting">Voice speed<input name="speech_speed" type="range" min=".7" max="1.5" step=".05" value="'+s.speech_speed+'"></label>'+
        '<div class="save-row"><button type="button" id="test-voice" class="primary-button">Test voice</button><span id="voice-test-status" class="status-text"></span></div><p class="panel-intro">Hear the selected voice and speed before saving. Listening pauses during the sample.</p>'+
        '<label class="setting">Wake-word threshold<input name="wake_threshold" type="range" min=".1" max=".95" step=".05" value="'+s.wake_threshold+'"><small>Lower is easier to wake. Higher rejects more background speech.</small></label>'+
        '<label class="setting">Microphone noise floor<input name="noise_floor" type="number" min=".001" max=".15" step=".001" value="'+s.noise_floor+'"><small>Lower this if quiet speech is missed.</small></label>'+
        '<label class="setting">Listening setup<select name="audio_output"><option value="speakers" '+(s.audio_output==='speakers'?'selected':'')+'>Speakers</option><option value="headphones" '+(s.audio_output==='headphones'?'selected':'')+'>Headphones</option></select><small>Choose where you hear Jarvis.</small></label>'+
        '<label class="setting check"><input name="barge_in" type="checkbox" '+(s.barge_in?'checked':'')+'><span>Voice interruption<small>Speak normally to interrupt a reply. Escape and the central core interrupt immediately.</small></span></label>'+
        '<label class="setting check"><input name="confirm_shell" type="checkbox" '+(s.confirm_shell?'checked':'')+'><span>Ask before running PowerShell<small>Turning this off lets model-generated scripts run immediately under your Windows account. File deletes and overwrites still ask.</small></span></label>'+
        '<div class="save-row"><button class="primary-button">Save settings</button><span id="saved" class="status-text"></span></div></form>';
      $("#test-voice").onclick=async()=>{
        try {
          await connectionReady; await ensureContext();
          const form=$("#settings-form"), values={};
          for(const key of ["tts_engine","kokoro_voice"]) values[key]=form.elements[key].value;
          values.speech_speed=Number(form.elements.speech_speed.value);
          cancelAudio(); previewVoice=true;
          $("#voice-test-status").textContent="Preparing sample…";
          send("preview_voice",{settings:values});
        } catch(error) { previewVoice=false; toast(error.message); }
      };
      $("#settings-form").onsubmit=async e=>{
        e.preventDefault();const data=new FormData(e.target), values={};
        for(const [key,value] of data) values[key]=["owner_name","model","tts_engine","kokoro_voice","audio_output"].includes(key)?value:Number(value);
        values.barge_in=e.target.elements.barge_in.checked;values.confirm_shell=e.target.elements.confirm_shell.checked;
        try{await api("settings",{method:"PUT",body:JSON.stringify(values)});$("#saved").textContent="Saved.";refresh();}catch(error){toast(error.message);}
      };
    }
  }catch(error){$("#panel-content").innerHTML='<p class="panel-error">'+esc(error.message)+'</p>';}
}
$("#enable-voice").onclick=()=>enableMicrophone(armed);
$("#voice-button").onclick=()=>enableMicrophone(true);
$("#mic-off").onclick=()=>disableMicrophone();
$("#stop-response").onclick=()=>{cancelAudio();send("interrupt");};
$("#mute").onclick=()=>{muted=!muted;if(muted)cancelAudio();$("#mute").classList.toggle("muted",muted);$("#mute").setAttribute("aria-label",muted?"Unmute assistant voice":"Mute assistant voice");toast(muted?"Voice muted. Captions remain visible.":"Voice enabled.");};
$("#approve").onclick=()=>{if(approvalId)send("approval",{approved:true,id:approvalId});};
$("#decline").onclick=()=>{if(approvalId)send("approval",{approved:false,id:approvalId});};
$("#fresh-start").onclick=()=>{cancelAudio();send("new_conversation");$("#heard-caption").textContent="";};
document.querySelectorAll("[data-panel]").forEach(b=>b.onclick=()=>openPanel(b.dataset.panel));
$("#close-panel").onclick=closePanel;$("#panel-backdrop").onclick=closePanel;
document.addEventListener("keydown",event=>{
  if(event.key==="Escape"){cancelAudio();send("interrupt");if(panel)closePanel();}
  if(event.code==="Space"&&!event.repeat&&!/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement.tagName)&&!panel){event.preventDefault();enableMicrophone(true);}
  if(event.key==="Tab"&&panel){
    const nodes=[...$("#detail-panel").querySelectorAll("button,input,select,textarea")].filter(n=>!n.disabled),first=nodes[0],last=nodes.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
});
window.addEventListener("beforeunload",()=>{stopped=true;clearTimeout(retryTimer);disableMicrophone(false);socket?.close();});
function clock(){const date=new Date();$("#clock").textContent=date.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});$("#date-label").textContent=date.toLocaleDateString([], {weekday:"long",day:"numeric",month:"long"});}
connect();refresh();clock();setInterval(refresh,10000);setInterval(clock,1000);
