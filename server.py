#!/usr/bin/env python3
"""QuizForge Backend - serves static files + AI quiz generation API on port 8085."""

import json
import os
import re
import time
import logging
from typing import List

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("quizforge")

# ---------------------------------------------------------------------------
# AI Gateway config
# ---------------------------------------------------------------------------

def load_gateway_config():
    for path in ["/dev/shm/claude_settings.json", "/root/.claude/settings.json"]:
        try:
            with open(path) as f:
                data = json.load(f)
            env = data.get("env", {})
            base_url = env.get("ANTHROPIC_BASE_URL")
            token = env.get("ANTHROPIC_AUTH_TOKEN")
            model = env.get("ANTHROPIC_MODEL")
            if base_url and token and model:
                log.info(f"Loaded AI gateway config from {path}")
                return {"base_url": base_url, "token": token, "model": model}
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            continue
    log.warning("No valid AI gateway config found")
    return None

GW = load_gateway_config()

# ---------------------------------------------------------------------------
# AI Quiz Generation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a quiz question generator. Generate quiz questions based on the user's request.

IMPORTANT: You must respond with ONLY a valid JSON array. No markdown, no explanation, no code fences.

Each question object must have these fields:
- "type": one of "mcq", "tf", or "fib"
- "diff": one of "easy", "medium", or "hard"
- "topic": the topic string
- "q": the question text
- "exp": a brief explanation of the correct answer (1-2 sentences)

Additional fields by type:
- For "mcq": "opts" (array of 4 option strings), "ans" (0-based index of correct option)
- For "tf": "ans" (boolean true or false)
- For "fib": "ans" (the correct fill-in word/phrase), "alts" (array of acceptable alternative answers)

Rules:
- Questions should be educational, accurate, and well-written
- MCQ distractors should be plausible but clearly wrong
- Fill-in-blank questions should have a clear single answer
- Vary the difficulty as requested
- Make explanations informative and concise"""


def build_user_prompt(topic, text, types, diff, count):
    parts = [f"Generate exactly {count} quiz questions"]
    if topic:
        parts.append(f"about the topic: {topic}")
    if text:
        parts.append(f"\n\nBase the questions on this text:\n\"\"\"\n{text[:3000]}\n\"\"\"")
    type_map = {"mcq": "Multiple Choice", "tf": "True/False", "fib": "Fill in the Blank"}
    type_names = [type_map.get(t, t) for t in types]
    parts.append(f"\nQuestion types to include: {', '.join(type_names)}")
    if diff and diff != "mixed":
        parts.append(f"Difficulty level: {diff}")
    else:
        parts.append("Mix of easy, medium, and hard difficulty levels")
    parts.append(f"\nRespond with ONLY a JSON array of {count} question objects. No other text.")
    return "\n".join(parts)


def call_ai(system, user, timeout=120):
    if not GW:
        raise RuntimeError("AI gateway not configured")
    url = f"{GW['base_url'].rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GW['token']}", "Content-Type": "application/json"}
    payload = {
        "model": GW["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    log.info(f"Calling AI: model={GW['model']}, timeout={timeout}s")
    t0 = time.time()
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
    log.info(f"AI response in {time.time()-t0:.1f}s")
    return resp.json()["choices"][0]["message"]["content"]


def parse_questions(raw_text, expected_count):
    text = raw_text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    match = re.search(r"\[[\s\S]*\]", text)
    if match:
        text = match.group(0)
    questions = json.loads(text)
    if not isinstance(questions, list):
        raise ValueError("Expected a JSON array")
    valid = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        qtype = q.get("type", "")
        if qtype not in ("mcq", "tf", "fib"):
            continue
        q["id"] = f"ai{i}"
        if qtype == "mcq":
            opts = q.get("opts", [])
            ans = q.get("ans", 0)
            if not isinstance(opts, list) or len(opts) < 2:
                continue
            if not isinstance(ans, int) or ans < 0 or ans >= len(opts):
                q["ans"] = 0
        if qtype == "tf":
            q["ans"] = bool(q.get("ans", True))
        if qtype == "fib":
            if not q.get("ans"):
                continue
            if "alts" not in q:
                q["alts"] = [str(q["ans"]).lower()]
        q.setdefault("diff", "medium")
        q.setdefault("topic", "General")
        q.setdefault("exp", "")
        valid.append(q)
    return valid[:expected_count]


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI()


class GenerateRequest(BaseModel):
    topic: str = ""
    text: str = ""
    types: List[str] = ["mcq", "tf", "fib"]
    difficulty: str = "mixed"
    count: int = 10


@app.post("/api/generate")
async def generate(req: GenerateRequest):
    """Generate quiz questions via AI."""
    topic = req.topic.strip()
    text = req.text.strip()
    types = req.types
    diff = req.difficulty
    count = min(req.count, 20)

    if not topic and not text:
        return JSONResponse({"error": "Provide a topic or text"}, status_code=400)
    if not GW:
        return JSONResponse({"error": "AI gateway not configured"}, status_code=503)

    user_prompt = build_user_prompt(topic, text, types, diff, count)
    try:
        raw = call_ai(SYSTEM_PROMPT, user_prompt, timeout=120)
        questions = parse_questions(raw, count)
        if not questions:
            return JSONResponse({"error": "AI returned no valid questions. Try again."}, status_code=502)
        log.info(f"Generated {len(questions)} questions for topic='{topic}'")
        return {"questions": questions}
    except httpx.TimeoutException:
        log.error("AI gateway timeout")
        return JSONResponse({"error": "AI model took too long. Please try again."}, status_code=504)
    except httpx.HTTPStatusError as e:
        log.error(f"AI gateway HTTP error: {e.response.status_code}")
        return JSONResponse({"error": f"AI service error ({e.response.status_code})"}, status_code=502)
    except json.JSONDecodeError:
        log.error("Failed to parse AI response as JSON")
        return JSONResponse({"error": "AI returned invalid format. Please try again."}, status_code=502)
    except Exception as e:
        log.error(f"Generation error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": GW["model"] if GW else "not configured"}


# Static files - MUST be last (catch-all)
app.mount("/", StaticFiles(directory="/workspace/AI_quizforge", html=True), name="static")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8085))
    log.info(f"QuizForge server starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
