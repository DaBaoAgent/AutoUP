# -*- coding: utf-8 -*-
"""Convert SRT files to plain text transcripts (strip indexes/timestamps)."""
import os, re, sys

ROOT = r"F:\16 监狱2"

def srt_to_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        raw = f.read()
    # Remove BOM, split blocks
    blocks = re.split(r"\n\s*\n", raw)
    lines = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        parts = b.split("\n")
        # parts[0] = index, parts[1] = timestamp, rest = text
        text_parts = []
        for p in parts:
            if re.match(r"^\d+$", p.strip()):
                continue
            if "-->" in p:
                continue
            text_parts.append(p.strip())
        if text_parts:
            lines.append(" ".join(text_parts))
    return "\n".join(lines)

for d in sorted(os.listdir(ROOT)):
    full = os.path.join(ROOT, d)
    if not os.path.isdir(full):
        continue
    srt = None
    for f in os.listdir(full):
        if f.lower().endswith(".srt"):
            srt = os.path.join(full, f)
            break
    if not srt:
        print(f"[SKIP] no srt in {d}")
        continue
    text = srt_to_text(srt)
    out = os.path.join(full, "_transcript.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[OK] {d}: {len(text)} chars -> {out}")
print("DONE")
