"""Convert a Squish xml3 test report into a single self-contained HTML file.

Why this exists instead of `squishrunner --reportgen html,<dir>`:

  * `--reportgen` is only valid inside squishrunner's --testsuite / --testcase
    execution modes. squishrunner has no standalone report-conversion mode, so it
    cannot re-render an xml3 report that has already been written.
  * Generating html directly at run time also fails on this machine. Squish is
    split across two installs: the executables and squishrunnerlib.dll live in
    C:\\Program Files (x86)\\squish_runtime\\bin, while the data files live in
    C:\\Program Files (x86)\\Squish for Windows 9.2.2. The html generator resolves
    its templates relative to the DLL, looking for
    squish_runtime\\lib\\webreport, which does not exist -- squish_runtime has no
    lib directory at all. It then kills the process at generator init with exit
    code 0 and an empty data/ directory. SQUISH_PREFIX does not redirect it.

    The permanent fix is to make the templates reachable under the runtime
    prefix, which needs an elevated shell:
        mklink /J "C:\\Program Files (x86)\\squish_runtime\\lib" ^
                  "C:\\Program Files (x86)\\Squish for Windows 9.2.2\\lib"
    After that, REPORT_FORMAT = "html" works natively and this script is
    redundant.

Usage:
    python xml3_to_html.py <results.xml | report-dir> [-o output.html]

Defaults to the demo-mosaiq report directory and writes report.html beside the
input.
"""

import argparse
import html
import os
import sys
from datetime import datetime
from xml.etree import ElementTree

NS = {"s": "http://www.froglogic.com/resources/schemas/xml3"}
DEFAULT_INPUT = r"C:\solver_automation\test-results\demo-mosaiq"


def _text(node, path):
    found = node.find(path, NS)
    return (found.text or "").strip() if found is not None else ""


def _parse_time(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _fmt_clock(raw):
    parsed = _parse_time(raw)
    return parsed.strftime("%H:%M:%S") if parsed else (raw or "")


class Node:
    """A section or test case, holding its own entries and child sections."""

    def __init__(self, kind, name, start, end):
        self.kind = kind
        self.name = name
        self.start = start
        self.end = end
        self.entries = []   # verifications and messages, in document order
        self.children = []

    @property
    def duration(self):
        a, b = _parse_time(self.start), _parse_time(self.end)
        return (b - a).total_seconds() if a and b else None

    def tally(self):
        passed = sum(1 for e in self.entries if e.get("result") == "PASS")
        failed = sum(1 for e in self.entries if e.get("result") == "FAIL")
        fatal = sum(1 for e in self.entries if e.get("type") == "FATAL")
        for child in self.children:
            cp, cf, cx = child.tally()
            passed, failed, fatal = passed + cp, failed + cf, fatal + cx
        return passed, failed, fatal


def parse_test(elem):
    node = Node(
        kind=elem.get("type", "test"),
        name=_text(elem, "s:prolog/s:name") or "(unnamed)",
        start=(elem.find("s:prolog", NS).get("time") if elem.find("s:prolog", NS) is not None else ""),
        end=(elem.find("s:epilog", NS).get("time") if elem.find("s:epilog", NS) is not None else ""),
    )

    for child in elem:
        tag = child.tag.split("}")[-1]

        if tag == "test":
            node.children.append(parse_test(child))

        elif tag == "verification":
            for res in child.findall("s:scriptedVerificationResult", NS):
                shot = res.find("s:screenshot/s:uri", NS)
                node.entries.append({
                    "result": res.get("type", ""),
                    "time": res.get("time", ""),
                    "text": _text(res, "s:text"),
                    "detail": _text(res, "s:detail"),
                    "uri": _text(res, "s:scriptedLocation/s:uri"),
                    "line": _text(res, "s:scriptedLocation/s:lineNo"),
                    "screenshot": (shot.text or "").strip() if shot is not None else "",
                })

        elif tag == "message":
            node.entries.append({
                "type": child.get("type", "LOG"),
                "time": child.get("time", ""),
                "text": _text(child, "s:text"),
                "uri": _text(child, "s:location/s:uri"),
                "line": _text(child, "s:location/s:lineNo"),
            })

    return node


CSS = """
:root {
  --bg:#f6f7f9; --card:#fff; --ink:#1a1d21; --muted:#666e79; --line:#e3e6ea;
  --pass:#0f7b3f; --pass-bg:#e8f6ed; --fail:#b3261e; --fail-bg:#fdeceb;
  --fatal:#8a1c17; --accent:#2b5cd9;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#14171a; --card:#1c2024; --ink:#e8eaed; --muted:#9aa4b0; --line:#2c3238;
    --pass:#5cd68f; --pass-bg:#14301f; --fail:#ff8a80; --fail-bg:#331816;
    --fatal:#ff6b5e; --accent:#7aa2f7;
  }
}
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
.wrap { max-width:1100px; margin:0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
.sub { color:var(--muted); font-size:.9rem; margin-bottom:1.5rem; }
.cards { display:flex; flex-wrap:wrap; gap:.75rem; margin-bottom:1.75rem; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:.85rem 1.1rem; min-width:120px; }
.card .n { font-size:1.6rem; font-weight:650; line-height:1.1; }
.card .l { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; }
.card.ok .n { color:var(--pass); } .card.bad .n { color:var(--fail); }
details.sec { background:var(--card); border:1px solid var(--line); border-radius:10px;
  margin-bottom:.75rem; overflow:hidden; }
details.sec > summary { cursor:pointer; padding:.8rem 1.1rem; font-weight:600;
  display:flex; align-items:center; gap:.6rem; list-style:none; }
details.sec > summary::-webkit-details-marker { display:none; }
details.sec > summary::before { content:"▸"; color:var(--muted); font-weight:400; }
details.sec[open] > summary::before { content:"▾"; }
.body { padding:0 1.1rem 1rem; }
.pill { font-size:.72rem; padding:.15rem .5rem; border-radius:999px; font-weight:700; letter-spacing:.03em; }
.pill.pass { color:var(--pass); background:var(--pass-bg); }
.pill.fail { color:var(--fail); background:var(--fail-bg); }
.t { margin-left:auto; color:var(--muted); font-weight:400; font-size:.82rem; }
.row { border-top:1px solid var(--line); padding:.7rem 0; display:flex; gap:.7rem; align-items:flex-start; }
.row:first-child { border-top:none; }
.row .main { flex:1; min-width:0; }
.row .msg { font-weight:550; }
.row .det { color:var(--muted); font-size:.86rem; margin-top:.2rem;
  font-family:ui-monospace,Consolas,monospace; word-break:break-word; }
.row .loc { color:var(--muted); font-size:.76rem; margin-top:.2rem; }
.row.log .msg { font-weight:400; color:var(--muted); font-size:.88rem; }
.row.fatal { background:var(--fail-bg); margin:0 -1.1rem; padding:.7rem 1.1rem; }
.row.fatal .msg { color:var(--fatal); font-weight:650; }
.clock { color:var(--muted); font-size:.76rem; font-variant-numeric:tabular-nums; padding-top:.15rem; }
a { color:var(--accent); }
.nested { margin-top:.75rem; }
"""


def render_entry(e):
    if "result" in e:
        ok = e["result"] == "PASS"
        pill = f'<span class="pill {"pass" if ok else "fail"}">{e["result"]}</span>'
        loc = ""
        if e["uri"]:
            loc = f'<div class="loc">{html.escape(e["uri"])}'
            if e["line"]:
                loc += f':{html.escape(e["line"])}'
            loc += "</div>"
        shot = ""
        if e["screenshot"]:
            shot = (f'<div class="loc">screenshot: '
                    f'<a href="{html.escape(e["screenshot"])}">{html.escape(e["screenshot"])}</a></div>')
        return (
            f'<div class="row">'
            f'<div class="clock">{_fmt_clock(e["time"])}</div>{pill}'
            f'<div class="main"><div class="msg">{html.escape(e["text"])}</div>'
            f'<div class="det">{html.escape(e["detail"])}</div>{loc}{shot}</div>'
            f'</div>'
        )

    fatal = e.get("type") == "FATAL"
    return (
        f'<div class="row log{" fatal" if fatal else ""}">'
        f'<div class="clock">{_fmt_clock(e["time"])}</div>'
        f'<div class="main"><div class="msg">{"FATAL: " if fatal else ""}'
        f'{html.escape(e["text"])}</div></div>'
        f'</div>'
    )


def render_node(node, top=False):
    passed, failed, fatal = node.tally()
    bad = failed or fatal
    pill = f'<span class="pill {"fail" if bad else "pass"}">{"FAIL" if bad else "PASS"}</span>'
    dur = node.duration
    meta = f'<span class="t">{passed} passed'
    if failed:
        meta += f', {failed} failed'
    if fatal:
        meta += f', {fatal} fatal'
    if dur is not None:
        meta += f' &middot; {dur:.1f}s'
    meta += "</span>"

    inner = "".join(render_entry(e) for e in node.entries)
    kids = "".join(render_node(c) for c in node.children)
    if kids:
        kids = f'<div class="nested">{kids}</div>'

    return (
        f'<details class="sec"{" open" if (top or bad) else " open"}>'
        f'<summary>{pill}{html.escape(node.name)}{meta}</summary>'
        f'<div class="body">{inner}{kids}</div>'
        f'</details>'
    )


def build_html(root, source):
    passed, failed, fatal = root.tally()
    total = passed + failed
    dur = root.duration
    started = _parse_time(root.start)
    verdict = "FAILED" if (failed or fatal) else "PASSED"

    cards = [
        ("total", "Verifications", str(total), ""),
        ("ok", "Passed", str(passed), "ok"),
        ("bad" if failed else "", "Failed", str(failed), "bad" if failed else ""),
    ]
    if fatal:
        cards.append(("bad", "Fatal", str(fatal), "bad"))
    if dur is not None:
        cards.append(("", "Duration", f"{dur:.0f}s", ""))

    card_html = "".join(
        f'<div class="card {cls}"><div class="n">{val}</div><div class="l">{label}</div></div>'
        for _, label, val, cls in cards
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(root.name)} - Squish report</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<h1>{html.escape(root.name)}</h1>
<div class="sub">{verdict} &middot;
{started.strftime("%Y-%m-%d %H:%M:%S") if started else "unknown start"} &middot;
source: {html.escape(source)}</div>
<div class="cards">{card_html}</div>
{render_node(root, top=True)}
</div></body></html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Convert a Squish xml3 report to HTML.")
    ap.add_argument("input", nargs="?", default=DEFAULT_INPUT,
                    help="results.xml, or a directory containing one")
    ap.add_argument("-o", "--output", help="output HTML file (default: report.html beside input)")
    args = ap.parse_args(argv)

    src = args.input
    if os.path.isdir(src):
        src = os.path.join(src, "results.xml")
    if not os.path.isfile(src):
        ap.error(f"no xml3 report found at: {src}")

    tree = ElementTree.parse(src)
    testcases = tree.getroot().findall("s:test", NS)
    if not testcases:
        ap.error(f"{src} contains no <test> elements -- is it an xml3 report?")

    out = args.output or os.path.join(os.path.dirname(os.path.abspath(src)), "report.html")
    root = parse_test(testcases[0])

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_html(root, os.path.abspath(src)))

    passed, failed, fatal = root.tally()
    print(f"Wrote {out}")
    print(f"  {passed} passed, {failed} failed" + (f", {fatal} fatal" if fatal else ""))
    return 1 if (failed or fatal) else 0


if __name__ == "__main__":
    sys.exit(main())
