from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


STATE_PATH = Path(".llm-runpod/state.json")


@dataclass(frozen=True)
class LastLaunch:
    pod_id: str
    model: str
    base_url: str
    openai_base_url: str
    gpu_id: str
    cost_per_hour: float | None = None
    volume_id: str | None = None


def save_last_launch(state: LastLaunch, *, path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")


def load_last_launch(*, path: Path = STATE_PATH) -> LastLaunch | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return LastLaunch(
        pod_id=str(data["pod_id"]),
        model=str(data["model"]),
        base_url=str(data["base_url"]),
        openai_base_url=str(data["openai_base_url"]),
        gpu_id=str(data["gpu_id"]),
        cost_per_hour=data.get("cost_per_hour"),
        volume_id=data.get("volume_id"),
    )
