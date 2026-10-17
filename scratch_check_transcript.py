import json

transcript_path = r"C:\Users\Soham\.gemini\antigravity-ide\brain\6ccc0ffc-5e5d-4ae6-98a5-158e296efa7e\.system_generated\logs\transcript.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    for idx, line in enumerate(f):
        if 975 <= idx <= 1020:
            data = json.loads(line)
            if data.get("type") in ("USER_INPUT", "ASK_QUESTION") or (data.get("source") == "MODEL" and data.get("content")):
                print(f"[{idx}] {data.get('type')}: {str(data.get('content'))[:200]}")
            for tc in data.get("tool_calls", []):
                print(f"[{idx}] TOOL: {tc.get('name')}: {str(tc.get('args'))[:200]}")


