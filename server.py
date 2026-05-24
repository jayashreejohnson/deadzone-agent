"""
FastAPI server for Agent 1.
Exposes POST /predict so Agent 2 (or Streamlit) can call it over HTTP.

Run:
  uvicorn server:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import re
import json

from agent1 import run_agent1

app = FastAPI(title="Dead Zone Prediction API - Agent 1", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PredictRequest(BaseModel):
    route: str
    departure_time: str


@app.get("/health")
def health():
    return {"status": "ok", "agent": "agent1"}


@app.post("/predict")
def predict(req: PredictRequest):
    try:
        output = run_agent1(req.route, req.departure_time, verbose=False)

        # Strip markdown code fences that the LLM sometimes wraps around JSON.
        # Pattern covers ```json ... ``` and ``` ... ``` (with optional newlines).
        clean = re.sub(r"```(?:json)?\s*", "", output).strip()

        try:
            parsed = json.loads(clean)
        except Exception:
            # Couldn't parse JSON — wrap in the expected shape so the backend
            # normalize_zones() call degrades gracefully instead of crashing.
            parsed = {"dead_zones": [], "raw": output}

        # Normalise: the backend expects {"dead_zones": {"dead_zones": [...]}}
        # so we must ensure the top-level dead_zones value is always a dict
        # with a "dead_zones" list inside it.
        if isinstance(parsed, list):
            # LLM returned a bare list of zones
            dead_zones = {"dead_zones": parsed}
        elif isinstance(parsed, dict) and "dead_zones" in parsed and isinstance(parsed["dead_zones"], list):
            # LLM returned {"dead_zones": [...]} — this is the expected shape
            dead_zones = parsed
        elif isinstance(parsed, dict) and "dead_zones" not in parsed:
            # Unexpected dict shape — wrap it so the backend doesn't crash
            dead_zones = {"dead_zones": [], "raw": output}
        else:
            dead_zones = parsed

        return {
            "route": req.route,
            "departure_time": req.departure_time,
            "dead_zones": dead_zones,
        }
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
