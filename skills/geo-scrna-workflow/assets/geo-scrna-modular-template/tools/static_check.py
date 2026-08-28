#!/usr/bin/env python3
from pathlib import Path
import re, sys
root = Path(__file__).resolve().parents[1]
files = sorted((root / "R").glob("*.R")) + sorted((root / "config").glob("*.R")) + [root / "run_pipeline.R"]
errors=[]
funcs={}
for path in files:
    text=path.read_text(encoding="utf-8")
    if "\u00a0" in text:
        errors.append(f"NBSP remains: {path}")
    if not text.endswith("\n"):
        errors.append(f"No trailing newline: {path}")
    for name in re.findall(r"(?m)^([A-Za-z.][A-Za-z0-9._]*)\s*<-\s*function\s*\(", text):
        funcs.setdefault(name, []).append(str(path.relative_to(root)))
    # Lightweight delimiter scan that ignores strings and line comments.
    stack=[]; quote=None; esc=False; comment=False
    pairs={')':'(',']':'[','}':'{'}
    for i,ch in enumerate(text):
        if comment:
            if ch=='\n': comment=False
            continue
        if quote:
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch==quote: quote=None
            continue
        if ch in ('"', "'"):
            quote=ch; continue
        if ch=='#': comment=True; continue
        if ch in '([{': stack.append((ch,i))
        elif ch in ')]}':
            if not stack or stack[-1][0] != pairs[ch]:
                errors.append(f"Delimiter mismatch in {path} near character {i}")
                break
            stack.pop()
    if stack: errors.append(f"Unclosed delimiter in {path}: {stack[-1]}")
for name, locations in funcs.items():
    if len(locations)>1:
        errors.append(f"Duplicate function {name}: {locations}")
if errors:
    print("STATIC CHECK FAILED")
    print("\n".join(errors))
    sys.exit(1)
print(f"STATIC CHECK PASSED: {len(files)} R files, {len(funcs)} functions")
