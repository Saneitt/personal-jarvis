"""Validated local calendar records shared by the API and voice tools."""
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, model_validator

def timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Include a timezone in calendar dates")
    return parsed.timestamp()

class CalendarEvent(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_at: str
    end_at: str
    all_day: bool = False
    notes: str = Field(default="", max_length=2000)
    remind_minutes: int = Field(default=-1, ge=-1, le=10080)

    @model_validator(mode="after")
    def valid_interval(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Enter an event title")
        start, end = timestamp(self.start_at), timestamp(self.end_at)
        if end <= start:
            raise ValueError("End time must be after start time")
        if end - start > 366 * 86400:
            raise ValueError("An event can span at most one year")
        return self

    def record(self):
        return dict(title=self.title, starts_at=timestamp(self.start_at),
                    ends_at=timestamp(self.end_at), all_day=int(self.all_day),
                    notes=self.notes, remind_minutes=self.remind_minutes)

def event_json(row):
    return {**row, "start_at": datetime.fromtimestamp(row["starts_at"]).astimezone().isoformat(),
            "end_at": datetime.fromtimestamp(row["ends_at"]).astimezone().isoformat(),
            "all_day": bool(row["all_day"])}
