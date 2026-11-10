#!/usr/bin/env python3
"""Simple Time API Server for OpenWebUI"""
from fastapi import FastAPI
from datetime import datetime
import pytz

app = FastAPI(title="Time API", version="1.0.0")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/current_time")
def get_current_time(timezone: str = "UTC"):
    """Get current time in specified timezone"""
    try:
        tz = pytz.timezone(timezone)
        now = datetime.now(tz)
        return {
            "timezone": timezone,
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "day": now.strftime("%A")
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/list_timezones")
def list_timezones():
    """List common timezones"""
    common = ["UTC", "Europe/Amsterdam", "Europe/London", "America/New_York", 
              "America/Los_Angeles", "Asia/Tokyo", "Asia/Singapore"]
    return {"timezones": common}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8300)

