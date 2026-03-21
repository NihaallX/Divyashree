"""
Compatibility module for scripts importing `database` from backend root.
"""

import os
import psycopg2
from shared.database import get_db


def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


def save_call_analysis(call_id: str, payload: dict):
    db = get_db()

    return __import__("asyncio").run(
        db.save_call_analysis(
            call_id=call_id,
            summary=payload.get("summary", ""),
            key_points=payload.get("key_points", [payload.get("summary", "")]),
            user_sentiment=payload.get("user_sentiment") or payload.get("sentiment", "neutral"),
            outcome=payload.get("outcome", "unknown"),
            next_action=payload.get("next_action"),
            intent_category=payload.get("intent_category"),
            budget_fit=payload.get("budget_fit"),
            geography_fit=payload.get("geography_fit"),
            timeline_fit=payload.get("timeline_fit"),
            overall_grade=payload.get("overall_grade"),
            checkpoint_json=payload.get("checkpoint_json"),
            metadata=payload.get("metadata") or {},
        )
    )
