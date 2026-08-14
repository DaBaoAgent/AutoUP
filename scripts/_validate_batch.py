# -*- coding: utf-8 -*-
"""Validate autoyy batch deliverables in F:\16 监狱2."""
import os, re, sys, glob

ROOT = r"F:\16 监狱2"

def cn_len(s):
    return len(re.sub(r"\s+", "", s))

results = []
for d in sorted(os.listdir(ROOT)):
    full = os.path.join(ROOT, d)
    if not os.path.isdir(full):
        continue
    r = {"dir": d, "script": None, "pub": None, "cover": None}
    script = os.path.join(full, "爆款口播稿.txt")
    pub = os.path.join(full, "发布信息.txt")
    cover = os.path.join(full, "封面提示词-即梦.txt")
    if os.path.exists(script):
        with open(script, encoding="utf-8") as f:
            t = f.read()
        n = cn_len(t)
        r["script"] = f"OK({n}字)" if 4500 <= n <= 5500 else f"FAIL({n}字)"
    else:
        r["script"] = "MISSING"
    if os.path.exists(pub):
        with open(pub, encoding="utf-8") as f:
            lines = [l.rstrip("\r\n") for l in f.readlines()]
        nonempty = [l for l in lines if l.strip()]
        title = nonempty[0] if nonempty else ""
        tags = nonempty[1].split() if len(nonempty) > 1 else []
        tl = len(title)
        r["pub"] = f"{'OK' if (len(nonempty)==2 and tl<=25 and len(tags)==5) else 'FAIL'}(行{len(nonempty)} 标题{tl}字 标签{len(tags)})"
        r["title"] = title
        r["tags"] = tags
    else:
        r["pub"] = "MISSING"
    if os.path.exists(cover):
        with open(cover, encoding="utf-8") as f:
            c = f.read().strip()
        paras = [p for p in re.split(r"\n\s*\n", c) if p.strip()]
        r["cover"] = f"{'OK' if len(paras)==2 else 'FAIL'}({len(paras)}段)"
    else:
        r["cover"] = "MISSING"
    results.append(r)

print(f"{'目录':<30} {'口播稿':<16} {'发布信息':<38} {'封面提示词':<10}")
for r in results:
    print(f"{r['dir']:<30} {r['script']:<16} {r['pub']:<38} {r['cover']:<10}")
    if r.get("title"):
        print(f"{'':<30} 标题: {r['title']}  标签: {' '.join(r['tags'])}")

ok = sum(1 for r in results if r["script"].startswith("OK") and r["pub"].startswith("OK") and r["cover"].startswith("OK"))
print(f"\n完成: {ok}/{len(results)}")
