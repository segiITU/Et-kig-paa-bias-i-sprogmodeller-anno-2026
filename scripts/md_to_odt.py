"""Convert a Markdown file with tables into a .odt with REAL Writer tables.

Markdown pipe-tables are not tables to LibreOffice — pasting them into Writer
gives you monospaced text with pipes. This renders the Markdown to HTML (where
a table is a real <table>) and hands that to LibreOffice's headless converter,
which turns <table> into a genuine Writer table you can restyle, sort and
reference like any other.

Usage:
    python scripts/md_to_odt.py docs/tables-for-article.md
    python scripts/md_to_odt.py docs/tables-for-article.md --out-dir results/report

Requires LibreOffice. The script looks for soffice on PATH and at the default
Windows install location; pass --soffice to point it elsewhere.

Only the Markdown subset this project actually uses is supported: headings,
paragraphs, pipe tables, bold/italic/inline code, horizontal rules and
blockquotes. It is deliberately small rather than a general Markdown engine.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

SOFFICE_FALLBACKS = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]

CSS = """
body { font-family: 'Liberation Serif', Georgia, serif; font-size: 11pt; }
h1 { font-size: 20pt; } h2 { font-size: 15pt; } h3 { font-size: 12pt; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #808080; padding: 4pt 6pt; text-align: left;
         vertical-align: top; font-size: 10pt; }
th { background: #e8e8e8; font-weight: bold; }
code { font-family: 'Liberation Mono', monospace; font-size: 9.5pt; }
blockquote { margin-left: 18pt; font-style: italic; }
"""


def _inline(text: str) -> str:
    """Escape, then re-apply the inline marks we support."""
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)
    # a literal <br> in a cell is a deliberate line break, not text to escape
    out = re.sub(r"&lt;br\s*/?&gt;", "<br/>", out)
    return out


def _is_divider(line: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", line.strip())) and "-" in line


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_to_html(md: str) -> str:
    lines = md.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # table: a pipe row followed by a divider row
        if (stripped.startswith("|") and i + 1 < len(lines)
                and _is_divider(lines[i + 1])):
            header = _cells(stripped)
            i += 2
            body = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                body.append(_cells(lines[i].strip()))
                i += 1
            out.append("<table><thead><tr>"
                       + "".join(f"<th>{_inline(c)}</th>" for c in header)
                       + "</tr></thead><tbody>")
            for row in body:
                row += [""] * (len(header) - len(row))
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>"
                                            for c in row[:len(header)]) + "</tr>")
            out.append("</tbody></table>")
            continue

        if not stripped:
            i += 1
            continue
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            out.append("<hr/>")
            i += 1
            continue
        m = re.match(r"(#{1,6})\s+(.*)", stripped)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if stripped.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{_inline(' '.join(buf))}</blockquote>")
            continue

        # paragraph: consume until a blank line or a block-level marker
        buf = []
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("|", "#", ">")):
            if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", lines[i].strip()):
                break
            buf.append(lines[i].strip())
            i += 1
        if buf:
            out.append(f"<p>{_inline(' '.join(buf))}</p>")

    return ("<html><head><meta charset='utf-8'/><style>" + CSS
            + "</style></head><body>" + "\n".join(out) + "</body></html>")


def find_soffice(explicit: str | None) -> str:
    if explicit:
        return explicit
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for cand in SOFFICE_FALLBACKS:
        if Path(cand).exists():
            return cand
    raise SystemExit(
        "LibreOffice (soffice) not found. Install it, or pass --soffice <path>.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("markdown", help="the .md file to convert")
    ap.add_argument("--out-dir", default=None, help="output directory (default: alongside the input)")
    ap.add_argument("--soffice", default=None, help="path to soffice/libreoffice")
    ap.add_argument("--keep-html", action="store_true", help="keep the intermediate .html")
    args = ap.parse_args()

    src = Path(args.markdown)
    if not src.exists():
        raise SystemExit(f"not found: {src}")
    out_dir = Path(args.out_dir) if args.out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = out_dir / (src.stem + ".html")
    html_path.write_text(md_to_html(src.read_text(encoding="utf-8")), encoding="utf-8")

    soffice = find_soffice(args.soffice)
    subprocess.run(
        [soffice, "--headless", "--convert-to", "odt", "--outdir", str(out_dir), str(html_path)],
        check=True, capture_output=True, timeout=180)

    odt = out_dir / (src.stem + ".odt")
    if not odt.exists():
        raise SystemExit("conversion ran but produced no .odt")
    if not args.keep_html:
        html_path.unlink()
    n_tables = src.read_text(encoding="utf-8").count("\n|---")
    print(f"{odt}  ({odt.stat().st_size:,} bytes, ~{n_tables} tables)")


if __name__ == "__main__":
    main()
