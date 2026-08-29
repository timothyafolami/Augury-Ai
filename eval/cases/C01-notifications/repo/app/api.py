"""The endpoint couriers post to."""

from fastapi import FastAPI

from app.queue import inbox

app = FastAPI(title="notifications")


@app.post("/deliveries")
async def accept_delivery(event: dict) -> dict:
    """Take a delivery event from the courier and acknowledge it."""
    await inbox.accept(event)
    return {"accepted": True, "queued": inbox.depth()}
