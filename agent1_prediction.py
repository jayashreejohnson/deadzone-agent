from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY
)

# --- Tool definitions ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "query_signal_history",
            "description": "Query historical cellular signal quality data for a specific location from ClickHouse. Returns signal strength readings over time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Location name or coordinates to query signal data for"},
                    "route_segment": {"type": "string", "description": "The road or highway segment (e.g. Lincoln Tunnel, I-95 NJ)"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "predict_dead_zones",
            "description": "Predict cellular dead zones along a route based on signal history and time of day. Returns list of predicted dead zones with location, timing, and severity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {"type": "string", "description": "The full route (e.g. Manhattan to Newark)"},
                    "departure_time": {"type": "string", "description": "Departure time in HH:MM format"},
                    "signal_data": {"type": "string", "description": "Signal history data from query_signal_history to base predictions on"}
                },
                "required": ["route", "departure_time"]
            }
        }
    }
]

# --- Simulated tool implementations ---
def query_signal_history(location: str, route_segment: str = "") -> dict:
    """Simulated ClickHouse query — replace with real ClickHouse call."""
    print(f"  [ClickHouse] Querying signal history for: {location}")
    # Simulated data — wire up real ClickHouse here
    simulated_data = {
        "location": location,
        "readings": [
            {"time": "17:00", "signal_dbm": -95, "quality": "poor"},
            {"time": "17:05", "signal_dbm": -110, "quality": "dead_zone"},
            {"time": "17:08", "signal_dbm": -112, "quality": "dead_zone"},
            {"time": "17:12", "signal_dbm": -98, "quality": "poor"},
            {"time": "17:15", "signal_dbm": -75, "quality": "good"}
        ],
        "source": "ClickHouse signal_quality table",
        "note": "Simulated data — production would query real ClickHouse Cloud instance"
    }
    return simulated_data

def predict_dead_zones(route: str, departure_time: str, signal_data: str = "") -> dict:
    """Simulated dead zone prediction — LLM reasons over this output."""
    print(f"  [Predictor] Predicting dead zones for {route} at {departure_time}")
    return {
        "route": route,
        "departure_time": departure_time,
        "dead_zones": [
            {
                "location": "Lincoln Tunnel approach (Manhattan side)",
                "start_time": "17:12",
                "duration_minutes": 3,
                "severity": "complete",
                "confidence": 0.92
            },
            {
                "location": "NJ Turnpike Exit 14 underpass",
                "start_time": "17:28",
                "duration_minutes": 1,
                "severity": "partial",
                "confidence": 0.75
            }
        ],
        "source": "Simulated prediction model"
    }

TOOL_MAP = {
    "query_signal_history": query_signal_history,
    "predict_dead_zones": predict_dead_zones
}

# --- Agent 1 loop ---
def run_prediction_agent(route: str, departure_time: str) -> str:
    print(f"\n=== Agent 1: Prediction Agent ===")
    print(f"Route: {route} | Departure: {departure_time}\n")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a signal prediction expert. Analyze routes and identify dead zones using your tools. "
                "Always include location, start_time, duration_minutes, and severity for each dead zone. "
                "Your final conclusion will be passed directly to another AI agent — structure it clearly "
                "so that agent can immediately act on it without ambiguity. "
                "If a tool returns an error, do not retry — move on and work with what you have."
            )
        },
        {
            "role": "user",
            "content": f"Analyze this route for cellular dead zones: {route}, departing at {departure_time}. Use your tools to query signal history and predict dead zones."
        }
    ]

    MAX_ITERATIONS = 50
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=messages,
            tools=tools,
            temperature=0.1
        )
        msg = response.choices[0].message

        if msg.content:
            print(f"Agent 1 thinking: {msg.content}")

        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                print(f"  -> Calling: {fn_name}({fn_args})")
                try:
                    result = TOOL_MAP[fn_name](**fn_args)
                except Exception as e:
                    result = {"error": str(e), "status": "failed"}
                    print(f"  [ERROR] {fn_name}: {e}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
        else:
            print("\n=== Agent 1 Final Output ===")
            print(msg.content)
            return msg.content

    # Hit max iterations — ask agent to conclude
    messages.append({
        "role": "user",
        "content": "Summarize the dead zones you found with what you have so far."
    })
    response = client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=messages,
        temperature=0.1
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    result = run_prediction_agent("Manhattan to Newark", "17:00")
    print("\nAgent 1 output ready for Agent 2.")
