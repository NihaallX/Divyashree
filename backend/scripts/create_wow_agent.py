#!/usr/bin/env python3
"""Create Divyasree WOW Priya agent prompt seed."""

import sys
sys.path.append('/app')
import os

from shared.database import get_db
from shared.prompts.wow_prompt import PRIYA_SYSTEM_PROMPT


def main():
    db = get_db()

    wow_user_id = os.getenv("WOW_USER_ID")
    if not wow_user_id:
        users = db.client.table("users").select("id").limit(1).execute()
        if users.data:
            wow_user_id = users.data[0]["id"]
    if not wow_user_id:
        raise ValueError("No user_id found. Set WOW_USER_ID in environment or create a user first.")

    prompt = PRIYA_SYSTEM_PROMPT

    agent = {
        "name": "Priya",
        "prompt_text": prompt,
        "template_source": "WOW Consultant",
        "llm_model": "llama-3.3-70b-versatile",
        "temperature": 0.6,
        "max_tokens": 180,
        "is_active": True,
        "user_id": wow_user_id,
    }

    result = db.client.table("agents").insert(agent).execute()
    print("Created agent: Priya")
    print(f"ID: {result.data[0]['id']}")


if __name__ == "__main__":
    main()
