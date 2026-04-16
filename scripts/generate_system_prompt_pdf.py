from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import textwrap

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "docs" / "deliverables" / "System_Prompt_Priya_WOW.pdf"


def load_prompt() -> str:
    sys.path.insert(0, str(ROOT))
    from shared.prompts.wow_prompt import PRIYA_SYSTEM_PROMPT

    return PRIYA_SYSTEM_PROMPT.strip()


def wrap_prompt_lines(prompt: str, width: int = 92) -> list[str]:
    wrapped_lines: list[str] = []

    for raw_line in prompt.splitlines():
        line = raw_line.rstrip()

        if not line:
            wrapped_lines.append("")
            continue

        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]

        if stripped.startswith("- "):
            bullet_prefix = indent + "- "
            bullet_body = stripped[2:].strip()
            bullet_lines = textwrap.wrap(
                bullet_body,
                width=max(10, width - len(bullet_prefix)),
                break_long_words=False,
                break_on_hyphens=False,
            )

            if not bullet_lines:
                wrapped_lines.append(bullet_prefix.rstrip())
                continue

            wrapped_lines.append(bullet_prefix + bullet_lines[0])
            continuation_prefix = indent + "  "
            for continuation in bullet_lines[1:]:
                wrapped_lines.append(continuation_prefix + continuation)
            continue

        normal_lines = textwrap.wrap(
            line,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        wrapped_lines.extend(normal_lines if normal_lines else [""])

    return wrapped_lines


def escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def paginate(lines: list[str], body_lines_per_page: int = 50) -> list[list[str]]:
    pages = [lines[i : i + body_lines_per_page] for i in range(0, len(lines), body_lines_per_page)]
    return pages if pages else [[]]


def build_content_stream(page_lines: list[str], page_number: int, total_pages: int) -> bytes:
    header_lines = [
        "Divyasree WOW - System Prompt (Priya)",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}   Page {page_number}/{total_pages}",
        "-" * 90,
        "",
    ]

    all_lines = header_lines + page_lines

    ops: list[str] = ["BT", "/F1 10 Tf", "12 TL", "50 760 Td"]

    if all_lines:
        first_line = all_lines[0]
        if first_line:
            ops.append(f"({escape_pdf_text(first_line)}) Tj")

        for line in all_lines[1:]:
            ops.append("T*")
            if line:
                ops.append(f"({escape_pdf_text(line)}) Tj")

    ops.append("ET")
    return "\n".join(ops).encode("latin-1", errors="replace")


def build_pdf(content_streams: list[bytes]) -> bytes:
    total_pages = len(content_streams)

    page_obj_ids: list[int] = []
    content_obj_ids: list[int] = []
    next_obj_id = 3

    for _ in range(total_pages):
        page_obj_ids.append(next_obj_id)
        content_obj_ids.append(next_obj_id + 1)
        next_obj_id += 2

    font_obj_id = next_obj_id

    objects: dict[int, bytes] = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    kids_ref = " ".join(f"{obj_id} 0 R" for obj_id in page_obj_ids)
    objects[2] = f"<< /Type /Pages /Count {total_pages} /Kids [ {kids_ref} ] >>".encode("ascii")

    for page_id, content_id in zip(page_obj_ids, content_obj_ids):
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        objects[page_id] = page_obj.encode("ascii")

    for content_id, stream in zip(content_obj_ids, content_streams):
        content_obj = b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        objects[content_id] = content_obj

    objects[font_obj_id] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"

    max_obj_id = max(objects.keys())
    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: list[int] = [0] * (max_obj_id + 1)

    for obj_id in range(1, max_obj_id + 1):
        offsets[obj_id] = len(pdf)
        pdf.extend(f"{obj_id} 0 obj\n".encode("ascii"))
        pdf.extend(objects[obj_id])
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {max_obj_id + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")

    for obj_id in range(1, max_obj_id + 1):
        pdf.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))

    trailer = (
        f"trailer\n<< /Size {max_obj_id + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_start}\n%%EOF\n"
    )
    pdf.extend(trailer.encode("ascii"))

    return bytes(pdf)


def main() -> None:
    prompt = load_prompt()
    wrapped_lines = wrap_prompt_lines(prompt, width=92)
    pages = paginate(wrapped_lines, body_lines_per_page=50)
    content_streams = [
        build_content_stream(page_lines, page_number=index + 1, total_pages=len(pages))
        for index, page_lines in enumerate(pages)
    ]

    pdf_bytes = build_pdf(content_streams)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(pdf_bytes)

    print(f"Generated PDF: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
