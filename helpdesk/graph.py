"""ประกอบ agent ทั้งหมดเป็น workflow ด้วย LangGraph

    Router ──out_of_scope──▶ ปฏิเสธสุภาพ
       │
       ▼
    Retriever ──ไม่เจอเอกสารที่เกี่ยวข้อง──▶ Ticket agent
       │
       ▼
    Knowledge agent ──ขอค้นซ้ำด้วยคำค้นใหม่ (ได้สูงสุด MAX_EXTRA_SEARCHES ครั้ง)──▶ กลับไป Retriever
       │        └──ตอบจากคู่มือไม่ได้──▶ Ticket agent
       │
       ▼
    ตอบพร้อมอ้างอิง
"""
import operator
import time
from functools import lru_cache
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from . import config
from .agents.knowledge import answer as knowledge_answer
from .agents.knowledge import propose_query
from .agents.router import route
from .agents.ticket import create_ticket
from .index import search


class HelpdeskState(TypedDict, total=False):
    question: str
    save_ticket: bool
    intent: str
    module: str
    search_query: str
    tried_queries: list[str]   # คำค้นทั้งหมดที่ใช้ไปแล้ว (รอบแรกมาจาก Router รอบถัดไปมาจาก Knowledge agent)
    next_query: str            # คำค้นที่ Knowledge agent ขอให้ค้นซ้ำ ("" = ไม่ขอ)
    hits: list[dict]
    top_score: float
    grounded: bool
    answer: str
    citations: list[str]
    evidence: str              # ประโยคจากคู่มือที่ใช้เป็นหลักฐาน (ผ่านการตรวจด้วยโค้ดแล้ว)
    ticket: dict
    ticket_reason: str
    outcome: str  # answer | ticket | out_of_scope
    reply: str
    trace: Annotated[list[dict], operator.add]


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def router_node(state: HelpdeskState) -> dict:
    t0 = time.perf_counter()
    out, how = route(state["question"])
    detail = f"intent={out['intent']}  module={out['module']}"
    if out["rewritten_query"] != state["question"]:
        detail += f"\nคำค้นใหม่: {out['rewritten_query']}"
    if out.get("error"):
        detail += f"\n⚠ {out['error']}"
    # ไม่ให้ Router ปฏิเสธคำถามเพียงลำพัง: ถ้าคลังความรู้มีเอกสารที่ตรงกับคำถามมาก แปลว่าเป็นเรื่องของระบบ
    # (เช่น "มีแอปบนไอโฟนไหม" ไม่เอ่ยชื่อระบบเลย แต่ตรงกับ FAQ)
    if out["intent"] == "out_of_scope":
        best = search(state["question"], None, 1)
        if best and best[0]["score"] >= config.SCOPE_RESCUE_SCORE:
            out = {**out, "intent": "how_to", "module": "UNKNOWN", "rewritten_query": state["question"]}
            detail += f"\nRouter บอกนอกขอบเขต แต่ตรงกับ {best[0]['id']} ({best[0]['score']:.2f}) → ถือว่าอยู่ในขอบเขต"
    return {"intent": out["intent"], "module": out["module"], "search_query": out["rewritten_query"],
            "tried_queries": [], "next_query": "",
            "trace": [{"agent": "Router", "how": how, "ms": _ms(t0), "detail": detail}]}


def retrieve_node(state: HelpdeskState) -> dict:
    t0 = time.perf_counter()
    module = state.get("module")
    hits = search(state["search_query"], module)
    note = "ค้นทุกโมดูล"
    # Router อาจเดาโมดูลผิด (หรือคำถามคาบเกี่ยวสองโมดูล) จึงค้นทั้งในโมดูลที่เลือกและทุกโมดูล แล้วรวมผล
    if module not in (None, "GENERAL", "UNKNOWN"):
        merged = {h["id"]: h for h in hits + search(state["search_query"], None)}
        ranked = sorted(merged.values(), key=lambda h: h["score"], reverse=True)[:config.TOP_K + 2]
        outside = sum(h["module"] not in (module, "GENERAL") for h in ranked)
        hits, note = ranked, f"ค้นในโมดูล {module} + ทุกโมดูล แล้วรวมผล (มาจากโมดูลอื่น {outside} รายการ)"
    tried = state.get("tried_queries", [])
    if tried:  # รอบค้นซ้ำ: เอาผลของคำค้นใหม่ขึ้นก่อน แล้วเก็บเอกสารเด่นของรอบก่อนไว้ 2 ชิ้นเผื่อคำตอบอยู่ตรงนั้น
        new_ids = {h["id"] for h in hits[:config.TOP_K]}
        hits = hits[:config.TOP_K] + [h for h in state.get("hits", []) if h["id"] not in new_ids][:2]
        note = f"ค้นซ้ำรอบที่ {len(tried) + 1} ด้วยคำค้นของ Knowledge agent: {state['search_query']}\n" + note
    top = max((h["score"] for h in hits), default=0.0)
    detail = note + "\n" + "\n".join(f"{h['score']:.3f}  {h['id']:10s} {h['title']}" for h in hits)
    return {"hits": hits, "top_score": top, "tried_queries": tried + [state["search_query"]], "next_query": "",
            "trace": [{"agent": "Retriever", "how": "vector search", "ms": _ms(t0), "detail": detail}]}


def answer_node(state: HelpdeskState) -> dict:
    t0 = time.perf_counter()
    tried = state.get("tried_queries", [])
    res, how = knowledge_answer(state["question"], state["intent"], state["hits"])
    update = {"grounded": res["grounded"], "answer": res["answer"], "citations": res["citations"],
              "evidence": res.get("evidence", ""), "next_query": ""}
    # ค้นซ้ำได้เฉพาะคำถามวิธีใช้ (how_to) ที่ยังมีโควตา — ถ้าเป็นการแจ้งปัญหาแล้วคู่มือไม่มีวิธีแก้ ให้เปิด Ticket เลย
    # เพราะการค้นต่อจนเจอเอกสาร "ใกล้เคียง" คือทางที่ทำให้ตอบมั่วได้ง่ายที่สุด
    if (not res["grounded"] and not res.get("error") and state["intent"] == "how_to"
            and len(tried) <= config.MAX_EXTRA_SEARCHES):  # tried นับรอบแรกด้วย
        update["next_query"] = propose_query(state["question"], state["hits"], tried)
    if res["grounded"]:
        update |= {"outcome": "answer", "reply": res["answer"]}
        detail = "ตอบได้จากเอกสาร " + ", ".join(res["citations"])
    elif update["next_query"]:
        update["search_query"] = update["next_query"]
        detail = f"เอกสารยังไม่ตรง → ขอค้นซ้ำด้วยคำค้นใหม่: {update['next_query']}"
    else:
        update["ticket_reason"] = "เอกสารที่ค้นเจอไม่มีวิธีแก้ปัญหานี้"
        detail = "ตอบจากคู่มือไม่ได้ → ส่งต่อ Ticket agent"
    if res.get("error"):
        detail += f"\n⚠ {res['error']}"
    update["trace"] = [{"agent": "Knowledge", "how": how, "ms": _ms(t0), "detail": detail}]
    return update


def ticket_node(state: HelpdeskState) -> dict:
    t0 = time.perf_counter()
    reason = state.get("ticket_reason") or f"ไม่พบเอกสารที่เกี่ยวข้อง (คะแนนสูงสุด {state.get('top_score', 0):.2f} < {config.MIN_SCORE})"
    ticket, how = create_ticket(state["question"], state.get("intent", ""), state.get("module", "UNKNOWN"),
                                state.get("hits", []), save=state.get("save_ticket", True))
    reply = (f"ยังไม่พบวิธีแก้ในคู่มือ จึงเปิด Ticket {ticket['ticket_id']} ให้{ticket['assigned_team']}แล้ว "
             f"(ความเร่งด่วน: {ticket['priority']})")
    if ticket.get("info_needed"):
        reply += "\nเพื่อให้แก้ได้เร็วขึ้น กรุณาเตรียม: " + ", ".join(ticket["info_needed"])
    return {"ticket": ticket, "ticket_reason": reason, "outcome": "ticket", "reply": reply,
            "trace": [{"agent": "Ticket", "how": how, "ms": _ms(t0), "detail": f"เหตุผล: {reason}"}]}


def out_of_scope_node(state: HelpdeskState) -> dict:
    return {"outcome": "out_of_scope",
            "reply": "ขออภัย ผู้ช่วยนี้ตอบเฉพาะเรื่องการใช้งานโปรแกรม SiteERP เช่น ใบขอซื้อ ใบสั่งซื้อ รับสินค้า เจ้าหนี้ และงบประมาณโครงการ",
            "trace": [{"agent": "Guard", "how": "rule", "ms": 0, "detail": "นอกขอบเขต ไม่ค้นเอกสาร"}]}


def after_router(state: HelpdeskState) -> str:
    return "out_of_scope" if state["intent"] == "out_of_scope" else "retrieve"


def after_retrieve(state: HelpdeskState) -> str:
    if len(state.get("tried_queries", [])) > 1:  # รอบค้นซ้ำผ่านด่านคะแนนมาแล้วตั้งแต่รอบแรก
        return "answer"
    return "answer" if state.get("top_score", 0) >= config.MIN_SCORE else "ticket"


def after_answer(state: HelpdeskState) -> str:
    if state.get("grounded"):
        return END
    return "retrieve" if state.get("next_query") else "ticket"


@lru_cache(maxsize=1)
def build_graph():
    g = StateGraph(HelpdeskState)
    g.add_node("router", router_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("answer", answer_node)
    g.add_node("ticket", ticket_node)
    g.add_node("out_of_scope", out_of_scope_node)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", after_router, ["retrieve", "out_of_scope"])
    g.add_conditional_edges("retrieve", after_retrieve, ["answer", "ticket"])
    g.add_conditional_edges("answer", after_answer, ["retrieve", "ticket", END])  # retrieve = วนกลับไปค้นซ้ำ
    g.add_edge("ticket", END)
    g.add_edge("out_of_scope", END)
    return g.compile()


def run(question: str, save_ticket: bool = True) -> HelpdeskState:
    return build_graph().invoke({"question": question, "save_ticket": save_ticket, "trace": []})
