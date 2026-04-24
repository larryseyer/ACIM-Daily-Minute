#!/usr/bin/env python3
"""
cost_tracker.py — API cost tracking for ACIM Daily Minute.

Tracks ElevenLabs TTS costs per day using daily JSON files.
Provides monthly estimates from a rolling 30-day history.
Modeled after the JTFNews cost tracking system.

Usage:
    from cost_tracker import log_api_usage, get_api_costs_today, get_month_estimate

    # After an ElevenLabs API call:
    log_api_usage("elevenlabs", {"characters": len(text)})

    # Get today's costs for monitor.json:
    costs = get_api_costs_today()
    estimate = get_month_estimate()
"""
from __future__ import annotations

import calendar
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")

# Monthly budget (used to calculate daily budget and budget %)
MONTHLY_BUDGET = float(os.getenv("MONTHLY_BUDGET", "10.00"))

# Cost rates
API_COSTS = {
    "elevenlabs": {"per_character": 0.00003},  # ~$0.03 per 1,000 characters
}


def _daily_file_path(date_str: str = None) -> Path:
    """Path to today's (or a specific date's) cost file."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return DATA_DIR / f"api_usage_{date_str}.json"


def _history_file_path() -> Path:
    """Path to the rolling 30-day cost history."""
    return DATA_DIR / "daily_costs.json"


def _load_daily(date_str: str = None) -> dict:
    """Load today's cost data, or create empty structure."""
    path = _daily_file_path(date_str)
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "date": date_str or datetime.now().strftime("%Y-%m-%d"),
        "services": {},
        "total_cost_usd": 0.0,
    }


def _save_daily(data: dict):
    """Save today's cost data."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _daily_file_path(data["date"])
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def log_api_usage(service: str, usage: dict):
    """Log an API call's usage and compute cost.

    Args:
        service: Service name (e.g., "elevenlabs").
        usage: Dict with usage details.
            For elevenlabs: {"characters": int}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    data = _load_daily(today)

    svc = data["services"].setdefault(service, {
        "calls": 0,
        "cost_usd": 0.0,
        "details": {},
    })
    svc["calls"] += 1

    cost = 0.0
    if service == "elevenlabs":
        chars = usage.get("characters", 0)
        cost = chars * API_COSTS["elevenlabs"]["per_character"]
        svc["details"]["characters"] = svc["details"].get("characters", 0) + chars

    svc["cost_usd"] += cost
    data["total_cost_usd"] = sum(
        s.get("cost_usd", 0) for s in data["services"].values()
    )

    _save_daily(data)
    log.debug(f"API cost logged: {service} +${cost:.4f} ({usage})")


def get_api_costs_today() -> dict:
    """Get today's cost data for monitor.json."""
    today = datetime.now().strftime("%Y-%m-%d")
    return _load_daily(today)


def get_daily_budget() -> float:
    """Calculate today's daily budget from monthly budget."""
    now = datetime.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    return MONTHLY_BUDGET / days_in_month


def get_month_estimate() -> float:
    """Estimate monthly cost from rolling 30-day history."""
    history = _load_history()
    now = datetime.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]

    if not history["days"]:
        # No history yet — extrapolate from today
        today = get_api_costs_today()
        return today.get("total_cost_usd", 0) * days_in_month

    total = sum(day["cost_usd"] for day in history["days"])
    avg_daily = total / len(history["days"])
    return avg_daily * days_in_month


def archive_yesterday_cost():
    """Archive yesterday's cost to the rolling 30-day history.

    Call this once per day (e.g., at pipeline startup).
    """
    from datetime import timedelta

    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_data = _load_daily(yesterday)
    cost = yesterday_data.get("total_cost_usd", 0)

    if cost == 0:
        return  # Nothing to archive

    history = _load_history()

    # Don't duplicate
    existing_dates = {d["date"] for d in history["days"]}
    if yesterday in existing_dates:
        return

    history["days"].append({"date": yesterday, "cost_usd": round(cost, 4)})
    history["days"].sort(key=lambda d: d["date"])

    # Keep only last 30 days
    if len(history["days"]) > 30:
        history["days"] = history["days"][-30:]

    history["last_updated"] = datetime.now(timezone.utc).isoformat()
    _save_history(history)
    log.info(f"Archived cost for {yesterday}: ${cost:.4f}")


def _load_history() -> dict:
    """Load the rolling 30-day cost history."""
    path = _history_file_path()
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"days": [], "last_updated": ""}


def _save_history(data: dict):
    """Save the rolling 30-day cost history."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_history_file_path(), "w") as f:
        json.dump(data, f, indent=2)
