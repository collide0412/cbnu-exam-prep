"""Build the IELTS Reading practice dataset from PDFs in the ielts folder."""
from __future__ import annotations

import json
import re
from pathlib import Path
import fitz

ROOT = Path(__file__).parent
PDF_DIR = ROOT / "ielts"
OUTPUT = ROOT / "ielts_extracted_data.json"
HEADING = re.compile(r"^\s*Questions?\s+(\d{1,2})\s*[-\u2013\u2014]\s*(\d{1,2})\s*$", re.I)
KEY = re.compile(r"\bKEY\b", re.I)
NUMBERED = re.compile(r"^\s*(\d{1,2})(?:\s*[.]\s*|\s+)(.*\S)?\s*$")
NOISE = re.compile(r"Mr\.\s*ZenicNguyen|Tel\s*:\s*\+?[\d.()\s-]{7,}|www\.facebook\.com/IELTSstepbystep|IELTS\s+step[- ]by[- ]step|Your\s+Success\s+is\s+our\s+Mission", re.I)
PAGE_FURNITURE = re.compile(r"^(?:IELTS Reading Recent Actual Tests.*|Test\s*\d+|Reading Passage\s*\d+|Page\s*\d+|\d{1,3})$", re.I)


def pdf_text(path: Path) -> str:
    with fitz.open(path) as doc:
        text = "\n\f\n".join(page.get_text("text") for page in doc)
        if len(text.strip()) >= 20000:
            return text
        print(f"OCR {path.name} ({len(doc)} pages)")
        pages = []
        for index, page in enumerate(doc, 1):
            try:
                tp = page.get_textpage_ocr(language="eng", dpi=220, full=True)
                pages.append(page.get_text("text", textpage=tp))
            except RuntimeError as error:
                raise RuntimeError("Install Tesseract OCR and add it to PATH.") from error
            if index % 20 == 0:
                print(f"  {index}/{len(doc)} pages")
        return "\n".join(pages)


def clean(raw: str) -> list[str]:
    raw = NOISE.sub("", raw.replace("\r", "").replace("\u00a0", " "))
    result = []
    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if (not line or line == "\f" or PAGE_FURNITURE.match(line)
            or re.search(r"zenic|face\s*book|sacebook|success\s*is\s*our|your\s*success|tel\s*:", line, re.I)):
            continue
        line = re.sub(r"(?i)(_{2,}|\.{3,}|(?:\s_\s){2,})", "[blank]", line)
        if result and result[-1].endswith("-") and line[:1].islower():
            result[-1] = result[-1][:-1] + line
        else:
            result.append(line)
    return result


def key_values(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    in_key = False
    for line in lines:
        if KEY.search(line):
            in_key = True
        if not in_key:
            continue
        for match in re.finditer(r"(?:^|\s)(\d{1,2})\s*[.)]?\s*((?:TR\s*UE|TRUE|FALSE|NOT\s*GIVEN|YES|NO|N0T\s*GIVEN|[A-H](?:\s*,\s*[A-H])*|[A-Za-z]+))", line, re.I):
            value = re.sub(r"\s+", " ", match.group(2).upper()).replace("TR UE", "TRUE").replace("N0T", "NOT")
            result[match.group(1)] = value
    return result


def blocks(lines: list[str], answers: dict[str, str]) -> list[dict]:
    output = []
    current = None
    question = None
    in_key = False

    def finish_question():
        nonlocal question
        if current is not None and question is not None:
            question["q_text"] = re.sub(r"\s+", " ", question["q_text"]).strip()
            if question["q_text"]:
                if question["q_number"] in answers:
                    question["correct_answer"] = answers[question["q_number"]]
                current["items"].append(question)
        question = None

    def finish_block():
        nonlocal current
        finish_question()
        if current is not None and current["items"]:
            output.append(current)
        current = None

    for line in lines:
        if KEY.match(line):
            in_key = True
            finish_block()
            continue
        match = HEADING.match(line)
        if match:
            in_key = False
            finish_block()
            current = {"block_name": f"Questions {match.group(1)}-{match.group(2)}", "items": []}
            continue
        if in_key or current is None:
            continue
        numbered = NUMBERED.match(line)
        if numbered and 1 <= int(numbered.group(1)) <= 40:
            finish_question()
            question = {"q_number": numbered.group(1), "q_text": numbered.group(2) or ""}
        elif question is not None:
            question["q_text"] += " " + line
    finish_block()
    return output


def main() -> None:
    data = {}
    for path in sorted(PDF_DIR.glob("Ielts Reading Recent Actual Tests Vol *.pdf"), key=lambda p: int(re.search(r"Vol (\d+)", p.name).group(1))):
        volume_number = re.search(r"Vol (\d+)", path.name).group(1)
        volume = f"Volume_{volume_number}"
        lines = clean(pdf_text(path))
        answers = key_values(lines)
        sections = blocks(lines, answers)
        data[volume] = {"source_pdf": f"ielts/{path.name}", "answer_key": answers, "sections": sections}
        print(f"{volume}: {len(sections)} sections, {sum(len(s['items']) for s in sections)} questions, {len(answers)} answers")
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
