"""เช็กความพร้อมก่อนรันจริง — รันอันนี้ก่อน prep.py ทุกครั้งที่ตั้งเครื่องใหม่

ตรวจ: Python, แพ็กเกจ, Ollama เปิดอยู่ไหม, เวอร์ชันรองรับ structured output ไหม, pull โมเดลครบไหม,
embedding กับแชตแบบบังคับ JSON ใช้งานได้จริงไหม และใช้เวลาเท่าไหร่

รัน: python tools/check_setup.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OK, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"
problems = 0


def report(status: str, msg: str, fix: str = "") -> None:
    global problems
    if status == FAIL:
        problems += 1
    print(f"{status} {msg}")
    if fix:
        print(f"       วิธีแก้: {fix}")


def version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in v.split("-")[0].split(".")[:3] if x.isdigit())


def main():
    if sys.version_info < (3, 10):
        report(FAIL, f"Python {sys.version.split()[0]}", "ใช้ Python 3.10 ขึ้นไป")
        return
    report(OK, f"Python {sys.version.split()[0]}")

    missing = []
    for pkg in ("langgraph", "chromadb", "rich"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        report(FAIL, f"ยังไม่ได้ติดตั้ง {', '.join(missing)}", "pip install -r requirements.txt")
        return
    report(OK, "ติดตั้งแพ็กเกจครบ")

    from helpdesk import config
    from helpdesk.llm import LLMError, chat_json, embed, get

    if config.BACKEND != "ollama":
        report(WARN, f"LLM_BACKEND={config.BACKEND} — ตัวเลขที่ได้ไม่ใช่ผลของโมเดลจริง", "ลบตัวแปร LLM_BACKEND ออก")
        return

    try:
        ver = get("/api/version").get("version", "0")
    except LLMError as e:
        report(FAIL, str(e), "เปิดแอป Ollama หรือรัน `ollama serve` ในอีกหน้าต่าง")
        return
    if version_tuple(ver) < (0, 5, 0):
        report(FAIL, f"Ollama {ver} เก่าเกินไป ยังไม่รองรับการบังคับ JSON schema", "อัปเดต Ollama เป็น 0.5 ขึ้นไป")
        return
    report(OK, f"Ollama {ver} ที่ {config.OLLAMA_URL}")

    names = {m.get("name", "") for m in get("/api/tags").get("models", [])}
    have_all = True
    for model in (config.CHAT_MODEL, config.EMBED_MODEL):
        if model in names or f"{model}:latest" in names:
            report(OK, f"มีโมเดล {model}")
        else:
            have_all = False
            report(FAIL, f"ยังไม่มีโมเดล {model}", f"ollama pull {model}")
    if not have_all:
        return

    try:
        t0 = time.perf_counter()
        vec = embed(["ใบสั่งซื้อที่อนุมัติแล้วแก้ไขได้อย่างไร"])[0]
        report(OK, f"embedding ใช้ได้ ({len(vec)} มิติ, {time.perf_counter() - t0:.1f} วินาทีรวมโหลดโมเดล)")
    except LLMError as e:
        report(FAIL, f"embedding ไม่สำเร็จ: {e}")
        return

    schema = {"type": "object", "properties": {"module": {"type": "string", "enum": ["PR", "PO", "AP"]}},
              "required": ["module"]}
    for label in ("ครั้งแรก (รวมโหลดโมเดล)", "ครั้งที่สอง"):
        try:
            t0 = time.perf_counter()
            out = chat_json("ตอบเป็น JSON ว่าข้อความเกี่ยวกับโมดูลไหน PR=ใบขอซื้อ PO=ใบสั่งซื้อ AP=เจ้าหนี้",
                            "แก้ราคาในใบสั่งซื้อ", schema)
            dt = time.perf_counter() - t0
        except LLMError as e:
            report(FAIL, f"แชตไม่สำเร็จ: {e}")
            return
        status = OK if out.get("module") == "PO" else WARN
        report(status, f"แชตแบบบังคับ JSON {label}: {out} ใน {dt:.1f} วินาที")

    print()
    if problems:
        print(f"เจอปัญหา {problems} ข้อ แก้ตามวิธีข้างบนแล้วรันใหม่")
    else:
        print("พร้อมแล้ว ขั้นต่อไป: python prep.py → python eval.py --sweep")
        print("ถ้าแชตครั้งที่สองช้ากว่า ~5 วินาที ให้เช็กว่าโมเดลรันบน GPU: `ollama ps` ช่อง PROCESSOR ควรเป็น 100% GPU")


if __name__ == "__main__":
    main()
