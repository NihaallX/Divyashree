import asyncio

from shared.database import get_db

AGENT_ID = "c4083449-3d67-4696-9822-15770d9c0371"


async def main():
    db = get_db()

    agent = await db.get_agent(AGENT_ID)
    if not agent:
        raise RuntimeError("Priya agent not found")

    call = await db.create_call(
        agent_id=AGENT_ID,
        to_number="+911234567890",
        from_number="+910000000000",
        user_id=agent.get("user_id"),
        status="in-progress",
        direction="outbound",
    )

    transcript = await db.save_transcript(
        call_id=call["id"],
        speaker="user",
        text="I am interested in investment near Nandi Hills",
        audio_duration=1.2,
        confidence_score=0.98,
        metadata={"smoke": True},
    )

    analysis = await db.save_call_analysis(
        call_id=call["id"],
        summary="Smoke test analysis row",
        key_points=["investment intent captured"],
        user_sentiment="positive",
        outcome="interested",
        next_action="BOOK_EXPERT_CALL",
        intent_category="INVESTMENT",
        budget_fit="YES",
        geography_fit="YES",
        timeline_fit="YES",
        overall_grade="HOT",
        checkpoint_json={
            "c1_intent": "PASS",
            "c2_geography": "PASS",
            "c3_budget": "PASS",
            "c4_timeline": "PASS",
        },
        metadata={"smoke": True},
    )

    print(f"CALL_OK={bool(call.get('id'))}")
    print(f"TRANSCRIPT_OK={bool(transcript.get('id'))}")
    print(f"ANALYSIS_OK={bool(analysis.get('id'))}")
    print(f"SMOKE_CALL_ID={call['id']}")


if __name__ == "__main__":
    asyncio.run(main())
