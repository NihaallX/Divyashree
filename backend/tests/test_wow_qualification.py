from shared.wow_qualification import infer_wow_from_conversation, normalize_wow_analysis


def test_infer_wow_hot_like_case():
    text = (
        "User wants investment in Nandi valley, confirms budget works, "
        "and is okay with 2029 phased timeline."
    )
    result = infer_wow_from_conversation(text)
    assert result["intent_category"] == "INVESTMENT"
    assert result["budget_fit"] in {"YES", "MAYBE"}
    assert result["geography_fit"] in {"YES", "HESITANT"}
    assert result["timeline_fit"] in {"YES", "HESITANT"}
    assert result["overall_grade"] in {"HOT", "WARM"}


def test_normalize_wow_analysis_fills_invalid_values():
    llm_data = {
        "intent_category": "unknown",
        "budget_fit": "idk",
        "geography_fit": "x",
        "timeline_fit": "",
        "overall_grade": "meh",
        "next_action": "call",
        "checkpoint_json": {"c1_intent": "ok"},
    }
    text = "Caller is looking for a weekend home, budget maybe, unsure location, 2029 is acceptable."
    result = normalize_wow_analysis(llm_data, text)
    assert result["intent_category"] in {"SELF_USE", "INVESTMENT", "UNCLEAR"}
    assert result["budget_fit"] in {"YES", "MAYBE", "NO", "HESITANT"}
    assert result["geography_fit"] in {"YES", "MAYBE", "NO", "HESITANT"}
    assert result["timeline_fit"] in {"YES", "MAYBE", "NO", "HESITANT"}
    assert result["overall_grade"] in {"HOT", "WARM", "COLD"}
    assert result["next_action"] in {"BOOK_EXPERT_CALL", "SEND_BROCHURE", "DO_NOT_CONTACT"}
    assert set(result["checkpoint_json"].keys()) == {"c1_intent", "c2_geography", "c3_budget", "c4_timeline"}
