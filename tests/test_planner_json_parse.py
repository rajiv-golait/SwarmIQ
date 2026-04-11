"""Planner _parse_llm_json repairs common malformed Groq planner output."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.roles.planner import PlannerNode


def test_parse_valid_json():
    raw = '{"questions": [{"id": "q1", "text": "t", "queries": ["a", "b"]}]}'
    out = PlannerNode._parse_llm_json(raw)
    assert len(out) == 1
    assert out[0]["queries"] == ["a", "b"]


def test_parse_queries_key_typo():
    # "queries:[" instead of "queries": [
    raw = r'''
    {"questions":[{"id":"q1","text":"What?","queries:[\n            \'one\',\n            \'two\'\n         ]"
    }]}
    '''
    out = PlannerNode._parse_llm_json(raw)
    assert len(out) == 1
    assert out[0]["id"] == "q1"
    assert "one" in out[0]["queries"][0] or out[0]["queries"][0] == "one"


def test_parse_queries_equals_syntax():
    raw = r'''{"questions":[{"id":"q1","text":"t","queries=[\n            \'a\',\n            \'b\'\n         ]"}]}'''
    out = PlannerNode._parse_llm_json(raw)
    assert len(out) == 1
    assert len(out[0]["queries"]) >= 2
