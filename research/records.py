"""Normalized, point-in-time event records and their persistence.

An event record is written with ONLY what was known when the signal fired (the close of the event bar).
Forward outcomes are computed later and stored separately (keyed by event_id) so they can never leak
back into the event definition or its context.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

EVENTS_DIR = Path("data/research/events")
QUALITY = ("clean", "estimated", "degraded", "unknown", "unavailable")


@dataclass
class EventRecord:
    event_id: str
    timestamp: str          # signal time = close of the event bar (UTC ISO)
    bar_open: int           # unix seconds of the event bar's open
    symbol: str
    timeframe: str
    session: str            # RTH | ETH | CLOSED, judged at the bar's last instant
    event: str
    direction: str          # long | short | info
    hypothesis: str | None  # for info events: the direction being tested, e.g. "toward_level"
    price: float            # event bar close = the reference entry for the event study
    level: float | None
    context: dict = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)
    source: str = ""        # e.g. replay:yahoo-snapshot-2026-10-05, live:scanner
    detector: str = ""      # code version of the detector that produced it

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)


def make_id(source: str, symbol: str, timeframe: str, event: str, bar_open: int) -> str:
    return hashlib.sha1(f"{source}|{symbol}|{timeframe}|{event}|{bar_open}".encode()).hexdigest()[:16]


def signal_time(bar_open: int, bar_seconds: int) -> str:
    return datetime.fromtimestamp(bar_open + bar_seconds, timezone.utc).isoformat()


def check_quality(dq: dict) -> dict:
    bad = {k: v for k, v in dq.items() if v not in QUALITY}
    if bad:
        raise ValueError(f"unknown data-quality values: {bad}")
    return dq


def write_jsonl(records: list[EventRecord], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with (gzip.open(path, "wt") if path.suffix == ".gz" else path.open("w")) as f:
        for r in records:
            f.write(r.to_json() + "\n")
    return path


def append_jsonl(records: list[EventRecord], path: Path) -> Path:
    """Append, skipping event_ids already in the file (idempotent across scanner runs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if path.exists():
        seen = {json.loads(line)["event_id"] for line in path.read_text().splitlines() if line.strip()}
    with path.open("a") as f:
        for r in records:
            if r.event_id not in seen:
                f.write(r.to_json() + "\n")
                seen.add(r.event_id)
    return path


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    text = gzip.open(path, "rt").read() if path.suffix == ".gz" else path.read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def detector_version() -> str:
    """Hash of the detection code, so results can be tied to the exact logic that produced them."""
    root = Path(__file__).resolve().parent.parent / "ofcore"
    h = hashlib.sha1()
    for name in ("setups.py", "auction.py", "profile.py", "indicators.py", "sessions.py"):
        h.update((root / name).read_bytes())
    return h.hexdigest()[:12]
