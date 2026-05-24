import asyncio
from pydantic import BaseModel
from backend.agent1 import run_agent1
import json, re

class PredictRequest(BaseModel):
    route: str
    departure_time: str

@app.post("/predict")
async def predict(req: PredictRequest):
    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(
        None, run_agent1, req.route, req.departure_time, False
    )
    # strip markdown code fences if present
    clean = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        dead_zones = json.loads(clean)
    except Exception:
        dead_zones = {"raw": raw}
    return {
        "route": req.route,
        "departure_time": req.departure_time,
        "dead_zones": dead_zones
    }
