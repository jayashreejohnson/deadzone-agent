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
            "name": "fetch_content",
            "description": "Fetch real web content (article or podcast) using Nimble web scraping API. Use this to get content that fits the dead zone duration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content_type": {"type": "string", "enum": ["article", "podcast_clip", "navigation"], "description": "Type of content to fetch"},
                    "query": {"type": "string", "description": "Search query or topic for the content"},
                    "duration_minutes": {"type": "number", "description": "Duration of dead zone in minutes — used to match content length"}
                },
                "required": ["content_type", "query", "duration_minutes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "queue_content",
            "description": "Add fetched content to the offline playback queue for a specific dead zone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dead_zone_location": {"type": "string", "description": "Location of the dead zone this content is for"},
                    "content_title": {"type": "string", "description": "Title or description of the content"},
                    "content_url": {"type": "string", "description": "URL of the fetched content"},
                    "content_type": {"type": "string", "description": "Type: article, podcast_clip, or navigation"},
                    "ready_by": {"type": "string", "description": "Time by which content must be cached (before dead zone start)"}
                },
                "required": ["dead_zone_location", "content_title", "content_url", "content_type"]
            }
        }
    }
]

# --- Simulated tool implementations ---
def fetch_content(content_type: str, query: str, duration_minutes: float) -> dict:
    """Calls Nimble API to fetch real web content — simulated for now."""
    print(f"  [Nimble] Fetching {content_type} for '{query}' ({duration_minutes} min dead zone)")
    # TODO: Replace with real Nimble API call
    # import requests
    # response = requests.post("https://api.nimbleway.com/v1/realtime",
    #     headers={"Authorization": f"Basic {NIMBLE_KEY}"},
    #     json={"url": f"https://news.ycombinator.com/search?q={query}", "render_js": False}
    # )
    content_map = {
        "article": {
            "title": f"Understanding {query}: A Deep Dive",
            "url": f"https://example.com/articles/{query.replace(' ', '-')}",
            "read_time_minutes": duration_minutes,
            "source": "Nimble web scrape (simulated)"
        },
        "podcast_clip": {
            "title": f"{query} — Quick Take",
            "url": f"https://example.com/podcasts/{query.replace(' ', '-')}",
            "duration_minutes": duration_minutes,
            "source": "Nimble web scrape (simulated)"
        },
        "navigation": {
            "title": "Offline navigation cache",
            "url": "local://navigation-cache",
            "cached": True,
            "source": "Local cache"
        }
    }
    return content_map.get(content_type, {"error": "unknown content type"})

content_queue = []

def queue_content(dead_zone_location: str, content_title: str, content_url: str,
                  content_type: str, ready_by: str = "") -> dict:
    """Adds content to the offline playback queue."""
    print(f"  [Queue] Adding '{content_title}' for {dead_zone_location}")
    item = {
        "dead_zone_location": dead_zone_location,
        "content_title": content_title,
        "content_url": content_url,
        "content_type": content_type,
        "ready_by": ready_by,
        "status": "queued"
    }
    content_queue.append(item)
    return {"queued": True, "queue_size": len(content_queue), "item": item}

TOOL_MAP = {
    "fetch_content": fetch_content,
    "queue_content": queue_content
}

# --- Agent 2 loop ---
def run_curation_agent(dead_zone_predictions: str) -> list:
    print(f"\n=== Agent 2: Content Curation Agent ===")
    print(f"Received dead zone predictions from Agent 1\n")

    messages = [
        {
            "role": "system",
            "content": (
                "You are a content curation agent. Given dead zone predictions, fetch appropriate content "
                "for each dead zone based on its duration. Use these exact rules:\n"
                "- 3+ minutes: fetch an article\n"
                "- 1-2 minutes: fetch a podcast clip\n"
                "- Always also queue navigation cache regardless of duration\n"
                "After fetching, queue all content using queue_content. "
                "If a tool returns an error, move on and summarize what you successfully fetched."
            )
        },
        {
            "role": "user",
            "content": f"Here are the predicted dead zones:\n\n{dead_zone_predictions}\n\nFetch and queue appropriate content for each dead zone."
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
            print(f"Agent 2 thinking: {msg.content}")

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
            print("\n=== Agent 2 Final Output ===")
            print(msg.content)
            return content_queue

    messages.append({
        "role": "user",
        "content": "Summarize what content you successfully queued and what failed."
    })
    response = client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=messages,
        temperature=0.1
    )
    print("Partial conclusion:", response.choices[0].message.content)
    return content_queue


if __name__ == "__main__":
    sample_prediction = """
    Dead zones detected on Manhattan to Newark route:
    1. Lincoln Tunnel approach - starts 17:12, duration 3 minutes, severity: complete
    2. NJ Turnpike Exit 14 underpass - starts 17:28, duration 1 minute, severity: partial
    """
    queue = run_curation_agent(sample_prediction)
    print("\nContent Queue:", json.dumps(queue, indent=2))
