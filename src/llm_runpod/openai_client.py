from __future__ import annotations

import json
import urllib.request
from typing import Any


def post_json(url: str, payload: dict[str, Any], *, timeout: int = 180) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def chat(base_url: str, model: str, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    data = post_json(f"{base_url.rstrip('/')}/v1/chat/completions", payload)
    return str(data["choices"][0]["message"]["content"])
