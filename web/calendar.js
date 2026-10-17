"use strict";
class JarvisCalendar {
  constructor(api, openEditor, onError) {
    this.api=api;this.openEditor=openEditor;this.onError=onError;
    this.selected=new Date();this.month=new Date(this.selected.getFullYear(),this.selected.getMonth(),1);
    this.events=[];this.reminders=[];this.revision=0;
    document.querySelector("#calendar-prev").onclick=()=>this.move(-1);
    document.querySelector("#calendar-next").onclick=()=>this.move(1);
    document.querySelector("#calendar-today").onclick=()=>this.focus(new Date());
    document.querySelector("#calendar-add").onclick=()=>this.openEditor(null,this.selected);
    this.render();
  }
  dateKey(value) { const d=new Date(value);return [d.getFullYear(),String(d.getMonth()+1).padStart(2,"0"),String(d.getDate()).padStart(2,"0")].join("-"); }
  focus(value) {
    const date=typeof value==="string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(value+"T12:00:00") : new Date(value);
    if(!Number.isFinite(date.getTime()))return;
    this.selected=date;this.month=new Date(date.getFullYear(),date.getMonth(),1);this.refresh();
  }
  move(offset) { this.month=new Date(this.month.getFullYear(),this.month.getMonth()+offset,1);this.selected=new Date(this.month);this.refresh(); }
  async refresh() {
    const revision=++this.revision;
    const first=new Date(this.month);first.setDate(1-((first.getDay()+6)%7));
    const last=new Date(first);last.setDate(last.getDate()+42);
    try {
      const result=await this.api("calendar?start="+encodeURIComponent(first.toISOString())+"&end="+encodeURIComponent(last.toISOString()));
      if(revision!==this.revision)return;
      this.events=result.events;this.reminders=result.reminders;this.render();
    }catch(error){if(revision===this.revision)this.onError(error);}
  }
  entries(date) {
    const start=new Date(date);start.setHours(0,0,0,0);
    const end=new Date(start);end.setDate(end.getDate()+1);
    return [...this.events.filter(e=>new Date(e.start_at)<end&&new Date(e.end_at)>start).map(e=>({...e,kind:"event"})),
      ...this.reminders.filter(r=>r.due*1000>=start&&r.due*1000<end).map(r=>({...r,title:r.text,start_at:new Date(r.due*1000).toISOString(),kind:"reminder"}))]
      .sort((a,b)=>new Date(a.start_at)-new Date(b.start_at));
  }
  render() {
    const q=s=>document.querySelector(s),grid=q("#calendar-grid");
    q("#calendar-month").textContent=this.month.toLocaleDateString([],{month:"long",year:"numeric"});
    grid.replaceChildren();
    const first=new Date(this.month);first.setDate(1-((first.getDay()+6)%7));
    const today=this.dateKey(new Date()),selected=this.dateKey(this.selected);
    for(let index=0;index<42;index++){
      const date=new Date(first);date.setDate(date.getDate()+index);
      const key=this.dateKey(date),count=this.entries(date).length,button=document.createElement("button");
      button.type="button";button.textContent=date.getDate();
      button.className="calendar-day"+(date.getMonth()!==this.month.getMonth()?" outside":"")+(key===today?" today":"")+(count?" has-events":"");
      button.setAttribute("aria-pressed",String(key===selected));
      button.setAttribute("aria-label",date.toLocaleDateString([],{weekday:"long",day:"numeric",month:"long",year:"numeric"})+(count?", "+count+" scheduled":""));
      button.onclick=()=>{this.selected=date;this.render();};
      grid.append(button);
    }
    q("#agenda-date").textContent=this.selected.toLocaleDateString([],{weekday:"short",day:"numeric",month:"short"});
    const agenda=q("#calendar-agenda");agenda.replaceChildren();
    const entries=this.entries(this.selected);
    if(!entries.length){const p=document.createElement("p");p.className="empty-copy";p.textContent="A little breathing room.";agenda.append(p);}
    for(const event of entries){
      const button=document.createElement("button");button.type="button";button.className="agenda-event";
      const time=document.createElement("span"),copy=document.createElement("span"),title=document.createElement("strong"),detail=document.createElement("small");
      time.textContent=event.all_day?"ALL DAY":new Date(event.start_at).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"});
      title.textContent=event.title;detail.textContent=event.kind==="reminder"?"Reminder":event.notes||"Calendar event";
      copy.append(title,detail);button.append(time,copy);
      button.onclick=()=>this.openEditor(event,this.selected);agenda.append(button);
    }
  }
}
