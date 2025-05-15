from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import json

app = FastAPI()

# Pydantic model to validate incoming GitLab webhook events
class GitLabEvent(BaseModel):
    object_kind: str
    project_id: int
    project_name: str
    user: str
    ref: str
    commits: List[dict]

# Webhook endpoint to receive GitLab events
@app.post("/webhook")
async def gitlab_webhook(event: GitLabEvent):
    # Here you can add code to process the event or log it
    print(f"Received webhook event: {event.object_kind}")
    return {"status": "success", "message": "Event received successfully"}

# Dashboard endpoint to view logs or events (basic)
@app.get("/")
async def get_dashboard():
    return {"message": "Welcome to the AI Pipeline Guardian Dashboard! No data yet."}
