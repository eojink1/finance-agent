"""Generates mvp.svg and product.svg. Run: python3 make.py
PNGs (macOS): qlmanage -t -s 2000 -o . mvp.svg product.svg && mv mvp.svg.png mvp.png && mv product.svg.png product.png
"""
C = {  # fill, stroke
    "llm": ("#EEEDFE", "#534AB7"), "code": ("#E1F5EE", "#0F6E56"), "store": ("#E6F1FB", "#185FA5"),
    "guard": ("#FAEEDA", "#854F0B"), "ui": ("#F1EFE8", "#5F5E5A"),
}
def box(x, y, w, h, title, sub="", kind="ui"):
    f, s = C[kind]
    ty = y + h / 2 + (-4 if sub else 5)
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{f}" stroke="{s}" stroke-width="1.5"/>'
    out += f'<text x="{x+w/2}" y="{ty}" class="t">{title}</text>'
    if sub: out += f'<text x="{x+w/2}" y="{ty+18}" class="s">{sub}</text>'
    return out
def arrow(x1, y1, x2, y2, both=False):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#5F5E5A" stroke-width="1.5" marker-end="url(#a)"{" marker-start=\"url(#a)\"" if both else ""}/>'
def group(x, y, w, h, label):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="none" stroke="#888780" stroke-dasharray="6 4"/>'
            f'<text x="{x+16}" y="{y+22}" class="g">{label}</text>')
def legend(y, items):
    out, x = "", 60
    for kind, label in items:
        f, s = C[kind]
        out += f'<rect x="{x}" y="{y}" width="14" height="14" rx="3" fill="{f}" stroke="{s}"/><text x="{x+20}" y="{y+12}" class="l">{label}</text>'
        x += 30 + 7.5 * len(label)
    return out
def svg(w, h, title, body):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" font-family="-apple-system, Helvetica, Arial, sans-serif">
<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#5F5E5A"/></marker></defs>
<style>.t{{font-size:15px;font-weight:600;fill:#2C2C2A;text-anchor:middle}} .s{{font-size:12px;fill:#5F5E5A;text-anchor:middle}}
.g{{font-size:12px;font-weight:700;fill:#5F5E5A;letter-spacing:1px}} .l{{font-size:12px;fill:#5F5E5A}} .h{{font-size:22px;font-weight:700;fill:#2C2C2A}} .hs{{font-size:13px;fill:#5F5E5A}}</style>
<rect width="{w}" height="{h}" fill="#FFFFFF"/>
<text x="60" y="44" class="h">{title[0]}</text><text x="60" y="66" class="hs">{title[1]}</text>
{body}</svg>'''

# ---------- MVP ----------
b = ""
b += box(370, 95, 200, 50, "CLI", "you ask a question", "ui")
b += arrow(470, 145, 470, 185)
b += box(290, 185, 360, 80, "Agent loop (plain Python)", "plan → call tool → observe → repeat → answer", "llm")
b += box(720, 195, 200, 60, "LLM", "OpenRouter · openai SDK", "llm")
b += arrow(650, 225, 720, 225, both=True)
b += arrow(470, 265, 470, 305)
b += box(320, 305, 300, 64, "run_python", "subprocess · timeout · output cap · scratch folder", "code")
b += arrow(470, 369, 470, 415)
b += box(345, 415, 250, 58, "DABstep data", "CSV · JSON · Markdown docs", "store")
b += group(60, 510, 880, 100, "EVALUATION RUNNER")
xs = [90, 305, 520, 735]
for x, (t, s, k) in zip(xs, [("DABstep questions", "dev set · 50-task samples", "store"), ("Agent", "same loop as above", "llm"),
                             ("Scorer", "DABstep answer matching", "code"), ("Results", "score + JSONL traces", "store")]):
    b += box(x, 545, 175, 50, t, s, k)
for x in xs[:-1]: b += arrow(x + 175, 570, x + 215, 570)
b += '<text x="60" y="650" class="l">Stack: Python 3.12 · uv · openai SDK (OpenRouter) · pydantic · pandas · Hugging Face datasets · no framework, no database</text>'
b += legend(672, [("llm", "LLM-driven"), ("code", "plain code"), ("store", "data / results"), ("ui", "interface")])
open("mvp.svg", "w").write(svg(1000, 1000, ("MVP — analysis agent on DABstep", "Goal: a working investigation loop with a benchmark score"), b))

# ---------- Product phase ----------
b = ""
for x, t, s in [(60, "CLI", ""), (280, "Claude Desktop", ""), (500, "React dashboard", "Vite"), (720, "Scheduler", "monthly report · alerts")]:
    b += box(x, 95, 200 if x == 720 else 190, 50, t, s, "ui")
b += box(280, 165, 190, 44, "MCP server", "official mcp SDK", "ui")
b += box(500, 165, 190, 44, "FastAPI", "REST API · approvals", "code")
b += arrow(155, 145, 155, 245); b += arrow(375, 145, 375, 165); b += arrow(375, 209, 375, 245)
b += arrow(595, 145, 595, 165); b += arrow(595, 209, 595, 245); b += arrow(820, 145, 820, 245)
b += group(60, 245, 880, 265, "AGENT CORE")
b += box(90, 280, 250, 62, "Model router", "cheap model ↔ reasoning model", "llm")
b += box(375, 280, 250, 62, "Agent loop", "plain loop → LangGraph", "llm")
b += box(660, 280, 250, 62, "Verifier agent", "other model family · spot-check", "llm")
b += arrow(340, 311, 375, 311); b += arrow(625, 311, 660, 311)
b += '<line x1="215" y1="360" x2="785" y2="360" stroke="#5F5E5A" stroke-width="1.5"/><line x1="500" y1="342" x2="500" y2="360" stroke="#5F5E5A" stroke-width="1.5"/>'
for t, s, x in [("run_python", "Docker · read-only DB role", 90), ("get_subscriptions", "precomputed", 375), ("memory", "user-stated facts", 660)]:
    b += arrow(x + 125, 360, x + 125, 378)
    b += box(x, 378, 250, 52, t, s, "code")
b += box(90, 448, 820, 44, "Guardrails", "untrusted transaction text · private network, no internet · approval gate for outbound actions", "guard")
b += arrow(215, 510, 215, 550); b += arrow(500, 510, 500, 550); b += arrow(785, 510, 785, 550)
b += box(90, 550, 535, 62, "PostgreSQL", "transactions · rules · subscriptions · memories · approvals · LangGraph checkpoints", "store")
b += box(660, 550, 250, 62, "Traces &amp; cost", "Langfuse", "store")
b += group(60, 650, 880, 120, "INGESTION — plain Python, no agent")
steps = [("Bank data", "CSV export · SimpleFIN", "ui"), ("Normalize + mask", "remove card numbers", "code"),
         ("Categorize", "rules → LLM fallback", "code"), ("Subscriptions", "interval + amount detection", "code")]
for i, (t, s, k) in enumerate(steps):
    x = 90 + i * 210
    b += box(x, 690, 190, 60, t, s, k)
    if i < 3: b += arrow(x + 190, 720, x + 210, 720)
b += arrow(215, 650, 215, 612)
b += box(60, 800, 880, 46, "Evaluation", "DABstep · own golden questions · prompt-injection tests · memory tests · pass^k · evals in CI", "code")
b += '<text x="60" y="880" class="l">Stack: Python · FastAPI · SQLAlchemy + Alembic · PostgreSQL · Docker · LangGraph · mcp SDK · Langfuse · React + Vite · SimpleFIN</text>'
b += legend(900, [("llm", "LLM-driven"), ("code", "plain code"), ("store", "data / storage"), ("guard", "guardrails"), ("ui", "interface")])
open("product.svg", "w").write(svg(1000, 1000, ("Product phase — personal finance agent", "Same agent core + FastAPI backend, PostgreSQL, memory, verifier, guardrails"), b))
