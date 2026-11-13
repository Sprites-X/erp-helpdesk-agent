"""ขั้นที่ 2: คุยกับ Helpdesk agent ในเทอร์มินัล พร้อมแสดงว่าแต่ละ agent ทำอะไร

รัน:  python chat.py                 โหมดพิมพ์ถามเอง (พิมพ์ q เพื่อออก)
      python chat.py -q "คำถาม"      ถามครั้งเดียว
      python chat.py --demo          เล่นสถานการณ์สาธิต 4 แบบ กด Enter เพื่อไปข้อถัดไป
      python chat.py --no-trace      ซ่อนขั้นตอนของ agent
"""
import argparse
import json
import time

from rich.console import Console
from rich.panel import Panel

from helpdesk import config
from helpdesk.graph import run
from helpdesk.llm import LLMError

console = Console()

DEMO = [
    ("คำถามวิธีใช้ → ตอบพร้อมอ้างอิง", "PO อนุมัติไปแล้ว อยากเพิ่มจำนวนต้องทำยังไง"),
    ("แจ้ง error ที่มีในคู่มือ → บอกวิธีแก้", "บันทึกรับของไม่ได้ ขึ้น RCV-E01"),
    ("ปัญหาที่คู่มือไม่มี → เปิด Ticket", "กดปุ่มพิมพ์เช็คแล้วโปรแกรมค้าง หน้าจอขาว ต้องปิดทิ้งทุกครั้ง"),
    ("ไม่เกี่ยวกับระบบ → ปฏิเสธ", "แนะนำร้านกาแฟแถวไซต์งานบางนาหน่อย"),
]
COLORS = {"Router": "cyan", "Retriever": "magenta", "Knowledge": "green", "Ticket": "yellow", "Guard": "red"}


def show(question: str, trace: bool = True) -> None:
    console.print(f"\n[bold]ผู้ใช้:[/bold] {question}")
    t0 = time.perf_counter()
    try:
        state = run(question)
    except (LLMError, RuntimeError) as e:
        console.print(Panel(str(e), title="ระบบขัดข้อง", border_style="red"))
        return
    total = time.perf_counter() - t0

    if trace:
        for step in state.get("trace", []):
            c = COLORS.get(step["agent"], "white")
            console.print(f"[{c}]▶ {step['agent']}[/{c}] [dim]({step['how']}, {step['ms']} ms)[/dim]")
            for line in step["detail"].split("\n"):
                console.print(f"    [dim]{line}[/dim]")

    outcome = state.get("outcome")
    if outcome == "answer":
        body = state["reply"] + f"\n\n[dim]อ้างอิง: {', '.join(state['citations'])}[/dim]"
        if state.get("evidence"):
            body += f"\n[dim]หลักฐานจากคู่มือ: “{state['evidence']}”[/dim]"
        console.print(Panel(body, title="คำตอบ", border_style="green"))
    elif outcome == "ticket":
        console.print(Panel(state["reply"], title="เปิด Ticket", border_style="yellow"))
        if trace:
            console.print_json(json.dumps(state["ticket"], ensure_ascii=False))
    else:
        console.print(Panel(state.get("reply", ""), title="นอกขอบเขต", border_style="red"))
    console.print(f"[dim]ใช้เวลารวม {total:.2f} วินาที | backend={config.BACKEND} model={config.CHAT_MODEL}[/dim]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--question")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--no-trace", action="store_true")
    args = parser.parse_args()
    trace = not args.no_trace

    if args.question:
        show(args.question, trace)
        return
    if args.demo:
        for i, (label, q) in enumerate(DEMO, 1):
            console.rule(f"[bold]สถานการณ์ {i}/{len(DEMO)}: {label}")
            show(q, trace)
            if i < len(DEMO):
                input("\n[Enter] ข้อถัดไป ")
        return

    console.print("[bold]SiteERP Helpdesk Agent[/bold] — พิมพ์คำถาม (q เพื่อออก)")
    while True:
        try:
            q = console.input("\n[bold]> [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"q", "quit", "exit"}:
            break
        if q:
            show(q, trace)


if __name__ == "__main__":
    main()
