"""ทดสอบเส้นทางของ workflow ทั้งหมด โดยใช้โมเดลปลอมที่กำหนดคำตอบได้

แต่ละข้อเช็กว่า "ระบบตัดสินใจถูกเส้นทางไหม" และ "เรียกโมเดลกี่ครั้ง ครั้งไหนบ้าง"
ซึ่งเป็นกติกาที่บังคับด้วยโค้ด ไม่ได้ขึ้นกับว่าโมเดลจริงฉลาดแค่ไหน
"""
import itertools

from conftest import doc

from helpdesk import config
from helpdesk.agents.router import route
from helpdesk.agents.ticket import create_ticket
from helpdesk.graph import run
from helpdesk.llm import LLMError

PO_TEXT = ("[ใบสั่งซื้อ (PO) > การแก้ไขใบสั่งซื้อหลังอนุมัติ]\n"
           "PO ที่อนุมัติแล้วแก้ไขตรงไม่ได้ ให้กดปุ่ม ขอแก้ไข แล้วระบบจะส่งกลับไปให้ผู้อนุมัติอีกครั้ง")
EVIDENCE = "PO ที่อนุมัติแล้วแก้ไขตรงไม่ได้ ให้กดปุ่ม ขอแก้ไข"
OTHER_TEXT = "[ใบสั่งซื้อ (PO) > ภาพรวม]\nใบสั่งซื้อสร้างจากใบขอซื้อที่อนุมัติแล้ว"


def agents(state) -> list[str]:
    return [t["agent"] for t in state["trace"]]


def step(state, agent: str) -> dict:
    return next(t for t in state["trace"] if t["agent"] == agent)


# ---------- เส้นทางตอบได้ ----------

def test_answer_with_verified_evidence(fake_ollama, fake_search):
    fake_search.default = [doc("PO-4", PO_TEXT, 0.82)]
    fake_ollama.replies["evidence"] = {"evidence": EVIDENCE, "doc_id": "PO-4", "answer": "กดปุ่มขอแก้ไข แล้วรออนุมัติใหม่"}
    s = run("PO อนุมัติแล้วแก้ยังไง", save_ticket=False)
    assert s["outcome"] == "answer"
    assert s["citations"] == ["PO-4"]
    assert s["evidence"] == EVIDENCE
    assert fake_ollama.calls == ["router", "evidence"]
    assert agents(s) == ["Router", "Retriever", "Knowledge"]


def test_citation_comes_from_code_check_not_from_model(fake_ollama, fake_search):
    """โมเดลบอก doc_id ผิด แต่ระบบอ้างเอกสารที่หาประโยคหลักฐานเจอจริง"""
    fake_search.default = [doc("PO-1", OTHER_TEXT, 0.7), doc("PO-4", PO_TEXT, 0.65)]
    fake_ollama.replies["evidence"] = {"evidence": EVIDENCE, "doc_id": "PO-1", "answer": "กดขอแก้ไข"}
    s = run("PO อนุมัติแล้วแก้ยังไง", save_ticket=False)
    assert s["citations"] == ["PO-4"]


def test_invented_evidence_is_not_used(fake_ollama, fake_search):
    """โมเดลยกประโยคที่ไม่มีในคู่มือ → ไม่ใช้คำตอบนั้น และส่งต่อ Ticket"""
    fake_search.default = [doc("PO-4", PO_TEXT, 0.82)]
    invented = "หัวหน้าโครงการแก้ไข PO ที่อนุมัติแล้วได้ทันทีโดยไม่ต้องขออนุมัติใหม่"
    fake_ollama.replies["evidence"] = {"evidence": invented, "doc_id": "PO-4", "answer": "แก้ได้ทันที"}
    s = run("PO อนุมัติแล้วแก้ยังไง", save_ticket=False)
    assert s["outcome"] == "ticket"
    assert "แก้ได้ทันที" not in s["reply"]
    assert fake_ollama.calls == ["router", "evidence", "retry", "ticket"]


# ---------- ด่านที่บังคับด้วยโค้ด ----------

def test_unknown_error_code_skips_the_model(fake_ollama, fake_search):
    """รหัส error ที่ไม่มีในเอกสารที่ค้นได้ → ไม่ให้โมเดลมีโอกาสเดาวิธีแก้เลย"""
    fake_search.default = [doc("PO-4", PO_TEXT, 0.8)]
    fake_ollama.replies["router"] = {"intent": "problem", "module": "PO", "rewritten_query": "อนุมัติ PO ไม่ผ่าน"}
    s = run("อนุมัติ PO แล้วขึ้น PO-E99", save_ticket=False)
    assert s["outcome"] == "ticket"
    assert "evidence" not in fake_ollama.calls
    assert step(s, "Knowledge")["how"].startswith("rule")


def test_router_keeps_error_code_in_search_query(fake_ollama, fake_search):
    """โมเดลเขียนคำค้นใหม่แล้วทำรหัส error หาย → โค้ดเติมกลับ เพราะรหัสคือสิ่งที่ค้นได้แม่นที่สุด"""
    fake_ollama.replies["router"] = {"intent": "problem", "module": "AP", "rewritten_query": "ตั้งหนี้ไม่ได้"}
    out, how = route("ตั้งหนี้แล้วขึ้นap-e01")
    assert how == "llm"
    assert "AP-E01" in out["rewritten_query"]


def test_known_error_code_goes_to_the_model(fake_ollama, fake_search):
    text = "[เจ้าหนี้ (AP) > รหัสข้อผิดพลาด]\nAP-E01 ยอดใบแจ้งหนี้ไม่ตรงกับใบรับสินค้า ให้ตรวจจำนวนที่รับจริงก่อนตั้งหนี้"
    fake_search.default = [doc("AP-6", text, 0.8)]
    fake_ollama.replies["router"] = {"intent": "problem", "module": "AP", "rewritten_query": ""}
    fake_ollama.replies["evidence"] = {"evidence": "AP-E01 ยอดใบแจ้งหนี้ไม่ตรงกับใบรับสินค้า", "doc_id": "AP-6",
                                       "answer": "ตรวจจำนวนที่รับจริงก่อนตั้งหนี้"}
    s = run("ตั้งหนี้ขึ้น AP-E01", save_ticket=False)
    assert s["outcome"] == "answer"
    assert s["citations"] == ["AP-6"]


def test_low_score_goes_to_ticket_without_asking_knowledge(fake_ollama, fake_search):
    fake_search.default = [doc("PO-1", OTHER_TEXT, config.MIN_SCORE - 0.1)]
    s = run("ทำไมหน้าจอเป็นสีขาว", save_ticket=False)
    assert s["outcome"] == "ticket"
    assert agents(s) == ["Router", "Retriever", "Ticket"]
    assert fake_ollama.calls == ["router", "ticket"]


# ---------- การค้นซ้ำ ----------

def test_problem_never_retries(fake_ollama, fake_search):
    """แจ้งปัญหาแล้วคู่มือไม่มีวิธีแก้ → เปิด Ticket เลย ไม่ค้นต่อจนเจอเอกสาร 'ใกล้เคียง'"""
    fake_search.default = [doc("PO-4", PO_TEXT, 0.8)]
    fake_ollama.replies["router"] = {"intent": "problem", "module": "PO", "rewritten_query": ""}
    s = run("PO ค้างตอนกดอนุมัติ", save_ticket=False)
    assert s["outcome"] == "ticket"
    assert "retry" not in fake_ollama.calls


def test_retry_finds_the_answer(fake_ollama, fake_search):
    fake_search.default = [doc("PO-1", OTHER_TEXT, 0.6)]
    fake_search.results["เมนูขอแก้ไขใบสั่งซื้อ"] = [doc("PO-4", PO_TEXT, 0.7)]
    fake_ollama.replies["retry"] = {"retry": True, "new_query": "เมนูขอแก้ไขใบสั่งซื้อ"}
    fake_ollama.replies["evidence"] = lambda user: (
        {"evidence": EVIDENCE, "doc_id": "PO-4", "answer": "กดขอแก้ไข"} if "PO-4" in user
        else {"evidence": "", "doc_id": "", "answer": ""})
    s = run("แก้ PO หลังอนุมัติ", save_ticket=False)
    assert s["outcome"] == "answer"
    assert s["citations"] == ["PO-4"]
    assert agents(s).count("Retriever") == 2
    assert fake_ollama.calls == ["router", "evidence", "retry", "evidence"]


def test_retry_is_capped(fake_ollama, fake_search):
    """โมเดลขอค้นใหม่ไม่หยุด → โค้ดหยุดให้ที่ MAX_EXTRA_SEARCHES รอบ"""
    fake_search.default = [doc("PO-1", OTHER_TEXT, 0.6)]
    n = itertools.count(1)
    fake_ollama.replies["retry"] = lambda user: {"retry": True, "new_query": f"คำค้นใหม่ {next(n)}"}
    s = run("แก้ PO หลังอนุมัติ", save_ticket=False)
    assert s["outcome"] == "ticket"
    assert agents(s).count("Retriever") == 1 + config.MAX_EXTRA_SEARCHES
    assert fake_ollama.calls.count("retry") == config.MAX_EXTRA_SEARCHES


def test_retry_with_same_query_is_ignored(fake_ollama, fake_search):
    fake_search.default = [doc("PO-1", OTHER_TEXT, 0.6)]
    fake_ollama.replies["retry"] = {"retry": True, "new_query": "แก้ PO หลังอนุมัติ"}
    s = run("แก้ PO หลังอนุมัติ", save_ticket=False)
    assert s["outcome"] == "ticket"
    assert agents(s).count("Retriever") == 1


def test_retry_can_be_disabled(fake_ollama, fake_search, monkeypatch):
    monkeypatch.setattr(config, "MAX_EXTRA_SEARCHES", 0)
    fake_search.default = [doc("PO-1", OTHER_TEXT, 0.6)]
    fake_ollama.replies["retry"] = {"retry": True, "new_query": "คำค้นอื่น"}
    s = run("แก้ PO หลังอนุมัติ", save_ticket=False)
    assert "retry" not in fake_ollama.calls
    assert agents(s).count("Retriever") == 1


# ---------- ขอบเขต ----------

def test_out_of_scope_is_refused_without_retrieval(fake_ollama, fake_search):
    fake_ollama.replies["router"] = {"intent": "out_of_scope", "module": "UNKNOWN", "rewritten_query": ""}
    fake_search.default = [doc("PO-1", OTHER_TEXT, 0.2)]
    s = run("ช่วยแต่งกลอนวันแม่ให้หน่อย", save_ticket=False)
    assert s["outcome"] == "out_of_scope"
    assert agents(s) == ["Router", "Guard"]
    assert fake_ollama.calls == ["router"]


def test_scope_rescue_when_question_matches_the_kb(fake_ollama, fake_search):
    """Router บอกนอกขอบเขต แต่คำถามตรงกับ FAQ มาก → ถือว่าอยู่ในขอบเขต"""
    faq = "[FAQ ทั่วไป (GENERAL)]\nถาม: มีแอปบนมือถือไหม\nตอบ: ใช้ผ่านเว็บเบราว์เซอร์บนมือถือได้ ยังไม่มีแอปแยก"
    fake_search.default = [doc("FAQ-9", faq, 0.75, module="GENERAL")]
    fake_ollama.replies["router"] = {"intent": "out_of_scope", "module": "UNKNOWN", "rewritten_query": ""}
    fake_ollama.replies["evidence"] = {"evidence": "ใช้ผ่านเว็บเบราว์เซอร์บนมือถือได้ ยังไม่มีแอปแยก",
                                       "doc_id": "FAQ-9", "answer": "ยังไม่มีแอป ใช้ผ่านเว็บบนมือถือได้"}
    s = run("มีแอปบนไอโฟนไหม", save_ticket=False)
    assert s["intent"] == "how_to"
    assert s["outcome"] == "answer"
    assert "ถือว่าอยู่ในขอบเขต" in step(s, "Router")["detail"]


# ---------- เมื่อโมเดลใช้ไม่ได้ ----------

def test_router_falls_back_to_rules_when_model_fails(fake_ollama):
    fake_ollama.replies["router"] = LLMError("Ollama ไม่ตอบ")
    out, how = route("ใบสั่งซื้อ อนุมัติไม่ได้")
    assert how == "rules (fallback)"
    assert out["module"] == "PO"
    assert out["intent"] == "problem"


def test_router_rejects_values_outside_the_schema(fake_ollama):
    fake_ollama.replies["router"] = {"intent": "question", "module": "PO", "rewritten_query": ""}
    _, how = route("PO แก้ยังไง")
    assert how == "rules (fallback)"


def test_knowledge_error_goes_to_ticket(fake_ollama, fake_search):
    fake_search.default = [doc("PO-4", PO_TEXT, 0.8)]
    fake_ollama.replies["evidence"] = LLMError("หลุด")
    s = run("PO อนุมัติแล้วแก้ยังไง", save_ticket=False)
    assert s["outcome"] == "ticket"
    assert "retry" not in fake_ollama.calls  # error ไม่ใช่เหตุผลให้ค้นซ้ำ


def test_ticket_falls_back_to_rules(fake_ollama):
    fake_ollama.replies["ticket"] = LLMError("หลุด")
    ticket, how = create_ticket("จ่ายเงินไม่ได้ทั้งบริษัท", "problem", "AP", [], save=False)
    assert how == "rules (fallback)"
    assert ticket["priority"] == "urgent"
    assert ticket["assigned_team"] == "ทีม Support งานบัญชีการเงิน"


def test_ticket_is_saved_to_ticket_dir(fake_ollama, fake_search):
    fake_search.default = []
    s = run("หน้าจอค้าง", save_ticket=True)
    saved = list(config.TICKET_DIR.glob("*.json"))
    assert [p.stem for p in saved] == [s["ticket"]["ticket_id"]]


# ---------- สถิติการเรียกโมเดลต่อขั้น ----------

def test_trace_records_model_usage_per_stage(fake_ollama, fake_search):
    fake_search.default = [doc("PO-4", PO_TEXT, 0.82)]
    fake_ollama.replies["evidence"] = {"evidence": EVIDENCE, "doc_id": "PO-4", "answer": "กดขอแก้ไข"}
    s = run("PO อนุมัติแล้วแก้ยังไง", save_ticket=False)
    router, retriever, knowledge = (step(s, a)["llm"] for a in ("Router", "Retriever", "Knowledge"))
    assert router["chat_calls"] == 1 and router["prompt_tokens"] == 800 and router["output_tokens"] == 40
    assert router["prefill_ms"] == 300 and router["decode_ms"] == 900
    assert retriever["chat_calls"] == 0
    assert knowledge["chat_calls"] == 1
