import json

from clean import clean, load_intents, reject_reason

INTENTS = load_intents()
GOOD = json.dumps({"intent": "weather_query", "date": None, "time": None, "place": "london"})


def test_each_rejection_reason():
    text = "what is the weather in london"
    assert reject_reason(text, "```json {}```", INTENTS) == "a"
    assert reject_reason(text, '{"intent": "weather_query"}', INTENTS) == "b"
    assert reject_reason(text, '{"intent": "x", "date": null, "time": null, "place": null}', INTENTS) == "c"
    assert reject_reason(text, '{"intent": "weather_query", "date": null, "time": null, "place": "paris"}',
                         INTENTS) == "d"
    assert reject_reason(text, '{"intent": "weather_query", "date": 7, "time": null, "place": null}', INTENTS) == "d"
    assert reject_reason(text, GOOD, INTENTS) is None


def test_duplicates_keep_smallest_id_and_counts_add_up():
    recs = [
        {"id": "C0003", "text": "what is the weather in london", "teacher_raw": GOOD},
        {"id": "C0001", "text": "what is the weather in london", "teacher_raw": GOOD},
        {"id": "C0002", "text": "what is the weather in london today", "teacher_raw": "oops"},
    ]
    kept, counts = clean(recs, INTENTS)
    assert [r["id"] for r in kept] == ["C0001"]
    assert counts["e_duplicates"] == 1 and counts["a_invalid_json"] == 1 and counts["kept"] == 1
    assert counts["input"] == sum(v for k, v in counts.items() if k != "input")


def test_output_sorted_by_id_with_canonical_target():
    raw = '{"place": "london", "intent": "weather_query", "time": null, "date": null}'
    recs = [{"id": "C0009", "text": "weather in london", "teacher_raw": raw},
            {"id": "C0004", "text": "weather london now", "teacher_raw": raw}]
    kept, _ = clean(recs, INTENTS)
    assert [r["id"] for r in kept] == ["C0004", "C0009"]
    assert list(json.loads(kept[0]["target"]).keys()) == ["intent", "date", "time", "place"]
    assert kept[0]["teacher_raw"] == raw  # the teacher reply is stored unedited
