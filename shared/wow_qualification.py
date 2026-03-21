"""Deterministic WOW qualification helpers.

Used to normalize or backfill LLM extraction so downstream scoring remains stable.
"""

from __future__ import annotations

from typing import Any, Dict

INTENT_VALUES = {"SELF_USE", "INVESTMENT", "UNCLEAR"}
FIT_VALUES = {"YES", "MAYBE", "NO", "HESITANT"}
GRADE_VALUES = {"HOT", "WARM", "COLD"}
ACTION_VALUES = {"BOOK_EXPERT_CALL", "SEND_BROCHURE", "DO_NOT_CONTACT"}
CHECKPOINT_VALUES = {"PASS", "SKIP", "FAIL"}


def _to_upper(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def _contains_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def infer_wow_from_conversation(conversation_text: str) -> Dict[str, Any]:
    """Infer WOW fields from transcript text as a safety net."""
    text = (conversation_text or "").lower()

    # Intent
    if _contains_any(text, ["investment", "invest", "return", "appreciation"]):
        intent = "INVESTMENT"
    elif _contains_any(text, ["weekend home", "personal use", "family", "self use", "dream home"]):
        intent = "SELF_USE"
    else:
        intent = "UNCLEAR"

    # Budget fit
    if _contains_any(text, ["too high", "expensive", "not in my budget", "out of budget"]):
        budget_fit = "NO"
    elif _contains_any(text, ["maybe", "depends", "flexible", "payment plan", "emi"]):
        budget_fit = "MAYBE"
    elif _contains_any(text, ["fits", "works", "okay", "within budget", "afford"]):
        budget_fit = "YES"
    else:
        budget_fit = "MAYBE"

    # Geography fit
    if _contains_any(text, ["location mismatch", "not this location", "too far", "not nandi"]):
        geography_fit = "NO"
    elif _contains_any(text, ["not sure location", "hesitant", "not comfortable", "maybe location"]):
        geography_fit = "HESITANT"
    elif _contains_any(text, ["nandi", "devanahalli", "north bengaluru", "airport proximity"]):
        geography_fit = "YES"
    else:
        geography_fit = "HESITANT"

    # Timeline fit
    if _contains_any(text, ["ready to move", "immediate", "urgent", "now"]):
        timeline_fit = "NO"
    elif _contains_any(text, ["2029", "phased", "long-term", "pre-launch", "wait"]):
        timeline_fit = "YES"
    else:
        timeline_fit = "HESITANT"

    # Checkpoint status (best effort)
    checkpoint_json = {
        "c1_intent": "PASS" if intent != "UNCLEAR" else "FAIL",
        "c2_geography": "PASS" if geography_fit in {"YES", "HESITANT"} else "FAIL",
        "c3_budget": "PASS" if budget_fit in {"YES", "MAYBE"} else "FAIL",
        "c4_timeline": "PASS" if timeline_fit in {"YES", "HESITANT"} else "FAIL",
    }

    # Grade
    if checkpoint_json["c1_intent"] == "PASS" and budget_fit == "YES" and geography_fit == "YES" and timeline_fit == "YES":
        overall_grade = "HOT"
    elif budget_fit in {"YES", "MAYBE"} and geography_fit in {"YES", "HESITANT"}:
        overall_grade = "WARM"
    else:
        overall_grade = "COLD"

    # Next action
    if overall_grade == "HOT":
        next_action = "BOOK_EXPERT_CALL"
    elif overall_grade == "WARM":
        next_action = "SEND_BROCHURE"
    else:
        next_action = "DO_NOT_CONTACT"

    return {
        "intent_category": intent,
        "budget_fit": budget_fit,
        "geography_fit": geography_fit,
        "timeline_fit": timeline_fit,
        "overall_grade": overall_grade,
        "checkpoint_json": checkpoint_json,
        "next_action": next_action,
    }


def normalize_wow_analysis(llm_data: Dict[str, Any], conversation_text: str) -> Dict[str, Any]:
    """Normalize LLM output and backfill missing WOW fields with deterministic inference."""
    llm_data = llm_data or {}
    inferred = infer_wow_from_conversation(conversation_text)

    intent = _to_upper(llm_data.get("intent_category"))
    if intent not in INTENT_VALUES:
        intent = inferred["intent_category"]

    budget = _to_upper(llm_data.get("budget_fit"))
    if budget not in FIT_VALUES:
        budget = inferred["budget_fit"]

    geography = _to_upper(llm_data.get("geography_fit"))
    if geography not in FIT_VALUES:
        geography = inferred["geography_fit"]

    timeline = _to_upper(llm_data.get("timeline_fit"))
    if timeline not in FIT_VALUES:
        timeline = inferred["timeline_fit"]

    grade = _to_upper(llm_data.get("overall_grade"))
    if grade not in GRADE_VALUES:
        grade = inferred["overall_grade"]

    action = _to_upper(llm_data.get("next_action"))
    if action not in ACTION_VALUES:
        action = inferred["next_action"]

    checkpoint = llm_data.get("checkpoint_json")
    if not isinstance(checkpoint, dict):
        checkpoint = inferred["checkpoint_json"]
    else:
        normalized_checkpoint = {}
        for key in ["c1_intent", "c2_geography", "c3_budget", "c4_timeline"]:
            value = _to_upper(checkpoint.get(key))
            normalized_checkpoint[key] = value if value in CHECKPOINT_VALUES else inferred["checkpoint_json"][key]
        checkpoint = normalized_checkpoint

    result = dict(llm_data)
    result["intent_category"] = intent
    result["budget_fit"] = budget
    result["geography_fit"] = geography
    result["timeline_fit"] = timeline
    result["overall_grade"] = grade
    result["next_action"] = action
    result["checkpoint_json"] = checkpoint
    return result
