import json
import time
import logging
from typing import Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from groq import RateLimitError, APIConnectionError
import groq
import os
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GROQ_API_KEY", "")
_client = groq.Groq(api_key=API_KEY)

class AgentError(Exception):
    pass

class BaseAgent:
    name: str = "base_agent"
    model: str = "llama-3.1-8b-instant"
    max_tokens: int = 900
    def __init__(self):
        self.logs: list[dict] = []
        self.retry_count: int = 0
        self.last_confidence: float = 0.0
    def log(self, step: str, detail: Any, level: str = "info"):
        entry = {"agent": self.name, "step": step, "detail": detail, "ts": time.time(), "level": level}
        self.logs.append(entry)
        getattr(logger, level, logger.info)(f"[{self.name}] {step}: {detail}")
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
        reraise=True,
    )
    def call_llm(self, system: str, user: str, max_tokens: Optional[int] = None) -> str:
        mt = max_tokens or self.max_tokens

        self.log("api_call", {"system_len": len(system), "user_len": len(user)})

        response = _client.chat.completions.create(
            model="llama-3.1-8b-instant",  # or mixtral, gemma, etc.
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=mt,
            temperature=0.2,
        )
        text = response.choices[0].message.content

        self.log("api_response", {"chars": len(text)})
        return text

    def parse_json(self, text: str) -> dict:
        cleaned = text.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    cleaned = part
                    break
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
 
        start = cleaned.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape_next = False
            for i, ch in enumerate(cleaned[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\" and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                if not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            candidate = cleaned[start:i + 1]
                            try:
                                return json.loads(candidate)
                            except json.JSONDecodeError as e:
                                self.log("json_parse_error", str(e), level="warning")
                            break
        raise AgentError(f"Could not parse JSON from response. Raw snippet: {text[:300]}")
    def run(self, *args, **kwargs) -> dict:
        raise NotImplementedError