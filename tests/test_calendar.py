from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from jarvis.calendar import CalendarEvent
from jarvis.config import Settings
from jarvis.storage import Store
from jarvis.tools import ToolRunner, validate_call

def event(**changes):
    return CalendarEvent.model_validate({"title":"Planning", "start_at":"2030-04-03T10:00:00+05:30",
        "end_at":"2030-04-03T11:00:00+05:30", "remind_minutes":10, **changes})

@pytest.fixture
def store(tmp_path):return Store(tmp_path/"calendar.sqlite3")

def test_calendar_persists_without_changing_existing_reminders(store):
    reminder=store.add_reminder("Stretch",100)
    saved=store.save_event(event())
    reopened=Store(store.path)
    assert reopened.event(saved["id"])["title"]=="Planning"
    assert reopened.reminders()[0]["id"]==reminder

@pytest.mark.parametrize("changes",[
    {"title":" "}, {"start_at":"2030-04-03T10:00:00"}, {"end_at":"2030-04-03T09:00:00+05:30"},
    {"remind_minutes":-2}, {"remind_minutes":10081}])
def test_calendar_rejects_invalid_dates_and_alerts(changes):
    with pytest.raises(ValueError):event(**changes)

def test_event_range_includes_multiday_overlap_but_not_end_boundary(store):
    saved=store.save_event(event(end_at="2030-04-05T11:00:00+05:30"))
    start=datetime.fromisoformat("2030-04-04T00:00:00+05:30").timestamp()
    assert store.events(start,start+86400)[0]["id"]==saved["id"]
    assert not store.events(saved["ends_at"],saved["ends_at"]+86400)

def test_alerts_fire_once_and_reschedule_on_update(store):
    saved=store.save_event(event())
    now=saved["starts_at"]-9*60
    assert store.due_events(now)[0]["id"]==saved["id"]
    store.notify_event(saved["id"])
    assert not store.due_events(now)
    store.save_event(event(title="Moved"),saved["id"])
    assert store.due_events(now)[0]["title"]=="Moved"
    assert not store.due_events(saved["ends_at"]+1)
    assert store.delete_event(saved["id"])
    assert not store.event(saved["id"]) and not store.due_events(now)

def test_disabled_alert_never_fires(store):
    saved=store.save_event(event(remind_minutes=-1))
    assert not store.due_events(saved["starts_at"])

def test_voice_calendar_create_list_update_delete(store):
    tools=ToolRunner(store,Settings())
    result=tools.calendar("create",title="Meeting",start_at="2030-04-03T10:00:00+05:30",
                          end_at="2030-04-03T11:00:00+05:30")
    item=result["event"]["id"]
    assert result["focus_date"]=="2030-04-03"
    assert tools.calendar("list",start_at="2030-04-03T00:00:00+05:30")["events"][0]["id"]==item
    assert tools.calendar("update",id=item,title="Updated")["event"]["title"]=="Updated"
    assert tools.calendar("delete",id=item)["deleted"]
    with pytest.raises(ValueError):tools.calendar("update",id=item,title="Missing")
    with pytest.raises(ValueError):validate_call("calendar",{"action":"update"})
    with pytest.raises(ValueError):validate_call("calendar",{"action":"create","all_day":"yes"})

def test_calendar_api_crud_and_invalid_input(monkeypatch,store):
    import jarvis.server as server
    monkeypatch.setattr(server,"store",store)
    client=TestClient(server.app)
    headers={"X-Jarvis-Token":server.TOKEN}
    payload=event().model_dump()
    assert client.post("/api/calendar",json=payload).status_code==401
    response=client.post("/api/calendar",json=payload,headers=headers)
    assert response.status_code==200
    item=response.json()["id"]
    assert client.put(f"/api/calendar/{item}",json={**payload,"title":"Changed"},headers=headers).json()["title"]=="Changed"
    url="/api/calendar?start=2030-04-01T00:00:00Z&end=2030-05-01T00:00:00Z"
    assert len(client.get(url,headers=headers).json()["events"])==1
    assert client.post("/api/calendar",json={**payload,"end_at":payload["start_at"]},headers=headers).status_code==422
    assert client.delete(f"/api/calendar/{item}",headers=headers).json()["deleted"]
    assert not client.get(url,headers=headers).json()["events"]
    assert client.put(f"/api/calendar/{item}",json=payload,headers=headers).status_code==404


def test_reminder_update_persists_and_validates_existing_id(store):
    runner=ToolRunner(store,Settings())
    created=runner.reminders("create",text="First",seconds=3600)["created"]
    runner.reminders("update",id=created,text="Moved",seconds=7200)
    assert store.reminder(created)["text"]=="Moved"
    with pytest.raises(ValueError):runner.reminders("update",id=99999,text="Missing",seconds=3600)
