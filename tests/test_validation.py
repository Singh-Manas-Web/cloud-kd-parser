from inference import format_prompt, trim_output
from validation import load_schema, validate_output

SCHEMA = load_schema()


def test_valid_output_is_accepted():
    raw = '{"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": null}'
    assert validate_output(raw, SCHEMA) == {"intent": "alarm_set", "date": "tomorrow", "time": "seven am",
                                             "place": None}


def test_invalid_outputs_are_rejected():
    for raw in ["not json", '{"intent": "alarm_set"}', '{"intent": "nope", "date": null, "time": null, "place": null}',
                '{"intent": "alarm_set", "date": null, "time": null, "place": null, "extra": 1}',
                '{"intent": "alarm_set", "date": 5, "time": null, "place": null}', "[1, 2]"]:
        assert validate_output(raw, SCHEMA) is None, raw


def test_prompt_and_trim():
    assert format_prompt("  set   an alarm ") == "Command: set an alarm\nJSON:"
    assert trim_output(' {"a": 1} Command: more') == '{"a": 1}'
