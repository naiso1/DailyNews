import re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

text = open('news_data.js', encoding='utf-8').read()

def is_chinese(s):
    # Simplified Chinese specific patterns (not found in Japanese)
    simp_cn = re.search(r'[车辆来产时为动这与发让国从]', s)  # Simplified Chinese chars
    cjk = sum(1 for c in s if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf')
    kana = sum(1 for c in s if '\u3041' <= c <= '\u309f' or '\u30a1' <= c <= '\u30ff')
    if cjk < 3 or kana > 0:
        return False
    # Must have simplified Chinese chars OR common Chinese-only punctuation
    return bool(simp_cn) or bool(re.search(r'[，。！？；：]', s))

pos = 0
found = []
while True:
    m = re.search(r'id:\s*"(cn\d+)"', text[pos:])
    if not m:
        break
    abs_start = pos + m.start()
    brace_start = text.rfind('{', 0, abs_start)
    depth = 0
    brace_end = brace_start
    for i in range(brace_start, min(brace_start + 5000, len(text))):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                brace_end = i + 1
                break
    block = text[brace_start:brace_end]
    nid = m.group(1)
    tm = re.search(r'title:\s*"((?:[^"\\]|\\.)*)"', block)
    dm = re.search(r'desc:\s*"((?:[^"\\]|\\.)*)"', block)
    if tm and dm:
        title = tm.group(1)
        desc = dm.group(1)
        tc = is_chinese(title)
        dc = is_chinese(desc)
        if tc or dc:
            found.append((nid, title, desc, tc, dc))
    pos = abs_start + 1

for nid, title, desc, tc, dc in found:
    flags = 'title+desc' if tc and dc else ('title' if tc else 'desc')
    print(nid + ' [' + flags + ']')
    print('  T: ' + title[:100])
    print('  D: ' + desc[:120])
    print()
print('Total: ' + str(len(found)) + '件')
