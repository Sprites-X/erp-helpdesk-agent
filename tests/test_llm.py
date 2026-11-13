"""ทดสอบชั้นที่คุยกับ Ollama: การบันทึกเวลา/จำนวน token และ embedding แบบแบ่งชุด"""
import pytest

from helpdesk import config, llm


def fake_post(calls):
    def post(path, payload, timeout=180):
        calls.append((path, payload))
        if path == "/api/embed":
            return {"embeddings": [[1.0, 0.0] for _ in payload["input"]], "total_duration": 5_000_000}
        return {"message": {"content": '{"ok": true}'}, "prompt_eval_count": 812,
                "prompt_eval_duration": 310_000_000, "eval_count": 64, "eval_duration": 1_250_000_000,
                "load_duration": 2_000_000}
    return post


def test_chat_json_records_ollama_timings(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_post", fake_post(calls))
    llm.take_calls()
    assert llm.chat_json("sys", "user", {"type": "object", "properties": {}}) == {"ok": True}
    payload = calls[0][1]
    assert payload["options"]["seed"] == config.SEED and payload["options"]["temperature"] == 0.0
    [stat] = llm.take_calls()
    assert stat["kind"] == "chat"
    assert (stat["prompt_tokens"], stat["output_tokens"]) == (812, 64)
    assert (stat["prefill_ms"], stat["decode_ms"], stat["load_ms"]) == (310.0, 1250.0, 2.0)
    assert llm.take_calls() == []   # อ่านแล้วล้าง


def test_embed_sends_batches_of_32(monkeypatch):
    calls = []
    monkeypatch.setattr(config, "BACKEND", "ollama")
    monkeypatch.setattr(llm, "_post", fake_post(calls))
    llm.take_calls()
    vectors = llm.embed([f"ข้อความ {i}" for i in range(70)])
    assert len(vectors) == 70
    assert [len(p["input"]) for _, p in calls] == [32, 32, 6]
    assert [s["kind"] for s in llm.take_calls()] == ["embed"] * 3


def test_stub_embed_needs_no_server(monkeypatch):
    monkeypatch.setattr(config, "BACKEND", "stub")
    monkeypatch.setattr(llm, "_post", lambda *a, **k: pytest.fail("stub ต้องไม่เรียก Ollama"))
    a, b, c = llm.embed(["ใบสั่งซื้อ", "ใบสั่งซื้อ", "งบประมาณ"])
    assert a == b and a != c
    assert abs(sum(v * v for v in a) - 1.0) < 1e-9


def test_parse_json_tolerates_text_around_the_object():
    assert llm.parse_json('ผลคือ {"grounded": false} ครับ') == {"grounded": False}
    with pytest.raises(llm.LLMError):
        llm.parse_json("ไม่ใช่ JSON")


def test_default_url_avoids_localhost(monkeypatch):
    # บน Windows ชื่อ localhost ทำให้ทุกการเรียก Ollama ช้าขึ้นราว 2 วินาที (ดู tools/probe_ollama.py)
    import importlib
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    fresh = importlib.reload(config)
    try:
        assert fresh.OLLAMA_URL == "http://127.0.0.1:11434"
    finally:
        importlib.reload(config)
