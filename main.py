"""
Dead Zone Content Agent — Main Orchestrator
Runs Agent 1 (Prediction) → Handoff → Agent 2 (Curation)
"""
from agent1_prediction import run_prediction_agent
from agent2_curation import run_curation_agent
import json

def run_pipeline(route: str, departure_time: str):
    print("\n" + "="*60)
    print("DEAD ZONE CONTENT AGENT")
    print("="*60)
    print(f"Route: {route}")
    print(f"Departure: {departure_time}")
    print("="*60)

    # --- Agent 1: Predict dead zones ---
    agent1_output = run_prediction_agent(route, departure_time)

    # --- Handoff: Agent 1 output -> Agent 2 input ---
    print("\n" + "-"*60)
    print("HANDOFF: Agent 1 -> Agent 2")
    print("-"*60)

    # --- Agent 2: Curate content ---
    content_queue = run_curation_agent(agent1_output)

    # --- Final summary ---
    print("\n" + "="*60)
    print("PIPELINE COMPLETE")
    print("="*60)
    print(f"Content queued for offline playback: {len(content_queue)} items")
    for item in content_queue:
        print(f"  - [{item['content_type']}] {item['content_title']} @ {item['dead_zone_location']}")

    return {
        "route": route,
        "departure_time": departure_time,
        "dead_zone_analysis": agent1_output,
        "content_queue": content_queue
    }


if __name__ == "__main__":
    result = run_pipeline("Manhattan to Newark", "17:00")
