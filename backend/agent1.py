from openai import OpenAI
from dotenv import load_dotenv
import json

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from tools import TOOLS, TOOL_FUNCTIONS

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

def run_agent1(route: str, departure_time: str, verbose: bool = True) -> str:
    if verbose:
        print(f"\n=== Agent 1: Dead Zone Prediction ===")
        print(f"Route: {route} | Departure: {departure_time}\n")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a cellular signal prediction expert. Your job is to identify dead zones "
                "along a driving route before the driver encounters them. "
                "Use your tools in this order: "
                "1. query_senso_knowledge to get known dead zones "
                "2. query_signal_history to get signal readings per segment "
                "3. predict_dead_zones to identify and classify dead zones from the signal data "
                "Always include location, start_time, duration_minutes, and severity for each dead zone. "
                "Your final output will be read by another AI agent that will fetch offline content — "
                "structure it clearly so that agent can act immediately without ambiguity. "
                "If a tool returns an error, move on and work with what you have."
            )
        },
        {
            "role": "user",
            "content": f"Predict dead zones for this route: {route}, departing at {departure_time}."
        }
    ]

    MAX_ITERATIONS = 50
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1
        response = client.chat.completions.create(
            model="google/gemini-2.0-flash-001",
            messages=messages,
            tools=TOOLS,
            temperature=0.1
        )
        msg = response.choices[0].message

        if msg.content and verbose:
            print(f"Agent 1: {msg.content}")

        if msg.tool_calls:
            messages.append(msg)
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                if verbose:
                    print(f"  -> {fn_name}({fn_args})")
                try:
                    result = TOOL_FUNCTIONS[fn_name](**fn_args)
                except Exception as e:
                    result = {"error": str(e), "status": "failed"}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result)
                })
        else:
            if verbose:
                print("\n=== Agent 1 Output ===")
                print(msg.content)
            return msg.content

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
    result = run_agent1("Manhattan to Newark", "17:00")
