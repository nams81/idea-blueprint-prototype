import os
import streamlit as st
import urllib.request
import json
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from openai import OpenAI

# -----------------------------
# Configuration
# -----------------------------
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")

# -----------------------------
# Access Gate (protect API spend)
# -----------------------------
ACCESS_CODE = os.getenv("ACCESS_CODE", "")
if ACCESS_CODE:
    code = st.text_input("Access code", type="password")
    if code != ACCESS_CODE:
        st.stop()

# -----------------------------
# Structured output schema
# -----------------------------
Mode = Literal["DISCOVERY", "INTENT_LOCK", "BUILDER"]

class ToolState(BaseModel):
    mode: Mode = "DISCOVERY"
    convergence_ready: bool = False
    confidence: Dict[str, int] = Field(default_factory=dict)
    direction_thesis: str = ""
    next_user_prompt: str = "Share your idea in plain words."

class ToolResponse(BaseModel):
    assistant_message: str
    state: ToolState
    blueprint_md: Optional[str] = None

class Critique(BaseModel):
    issues: List[str] = Field(default_factory=list)

# -----------------------------
# System instructions (HARDENED)
# -----------------------------
SYSTEM_INSTRUCTIONS = """
You are an AI reasoning system that helps users turn vague business ideas into a clear, execution-ready business blueprint.

NON-NEGOTIABLE BEHAVIOR
- This is not a test or exam. You choose the best conversational path to reach clarity.
- The user may be inarticulate. Do not ask them to explain better. Offer interpretations to react to.
- Use a recognition loop: Propose → Contrast → Invite rejection → Refine.
- Avoid hedging. Never use: maybe, might, seems, possibly, could be.
- Ask at most ONE question per turn.

ASSUMPTION BOUNDARY (CRITICAL)
- Never present inferred information as fact.
- Label information explicitly as:
  (a) Confirmed (from user),
  (b) Assumed (your inference),
  (c) Open (WIP).

PROHIBITIONS
- Do NOT fabricate numbers, market sizes, competitors, pricing benchmarks, regulations, or best practices.
- If examples are used, keep them generic and label them as examples.

CONVERGENCE RULE
- Converge when signal is sufficient, not complete:
  (a) Direction stabilizes,
  (b) At least one real trade-off is accepted,
  (c) Emotional confirmation appears.
- When ready, set state.mode = "INTENT_LOCK".

INTENT_LOCK MODE
- Output 5–8 declarative sentences describing the business.
- No bullets, no frameworks, no hedging.
- Then ask exactly one question:
  "If we proceed on this basis, I will now design the full business blueprint. Is there anything here that feels fundamentally wrong or missing?"

BUILDER MODE
- Stop exploring. Synthesize decisively.
- Produce a Markdown blueprint with these sections:
  1. Business summary
  2. Customer and problem
  3. Value proposition and differentiation
  4. Product scope (MVP, included vs excluded)
  5. Go-to-market hypothesis
  6. Tech and build direction
  7. Operations and risks
  8. Revenue and pricing logic
  9. 90-day execution plan
  10. Open items (WIP, mandatory)
  11. Reality checks & risks
- Explicitly tag assumptions and open items.

OUTPUT FORMAT
Return valid JSON matching the ToolResponse schema.
"""

# -----------------------------
# Helper: contradiction scan
# -----------------------------
def run_contradiction_scan(blueprint_md: str) -> List[str]:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.responses.parse(
        model=DEFAULT_MODEL,
        reasoning={"effort": REASONING_EFFORT},
        input=[
            {"role": "system", "content": "Scan for internal contradictions, unrealistic assumptions, or logic mismatches. List only concrete issues."},
            {"role": "user", "content": blueprint_md},
        ],
        text_format=Critique,
    )
    return resp.output_parsed.issues
    
def log_to_gsheet(role: str, message: str):
    url = os.environ.get("GSHEET_WEBHOOK_URL")
    if not url:
        return  # logging is optional

    payload = {
        "timestamp_utc": __import__("datetime").datetime.utcnow().isoformat(),
        "session_id": st.session_state.get("session_id", ""),
        "role": role,
        "message": message,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:
        # Never break the app because logging failed
        pass

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Idea → Business Blueprint", layout="wide")
st.title("Idea → Business Blueprint")
st.caption("Turn a vague idea into a clear, execution-ready business")

st.info(
    "This tool structures thinking. Assumptions and risks are explicitly labelled. "
    "Validate them before execution."
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "prev_response_id" not in st.session_state:
    st.session_state.prev_response_id = None
if "tool_state" not in st.session_state:
    st.session_state.tool_state = ToolState().model_dump()
if "blueprint_md" not in st.session_state:
    st.session_state.blueprint_md = ""

# Sidebar
with st.sidebar:
    st.subheader("Session state")
    st.write("Mode:", st.session_state.tool_state.get("mode"))
    st.write("Converged:", st.session_state.tool_state.get("convergence_ready"))
    if st.button("Reset"):
        st.session_state.clear()
        st.rerun()

# Show conversation
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Chat input
user_input = st.chat_input(st.session_state.tool_state.get("next_user_prompt", "Describe your idea."))

def call_ai(user_text: str) -> ToolResponse:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Use previous_response_id for continuity if available
    if st.session_state.prev_response_id:
        resp = client.responses.create(
            model=DEFAULT_MODEL,
            previous_response_id=st.session_state.prev_response_id,
            instructions=SYSTEM_INSTRUCTIONS,
            input=[{"role": "user", "content": user_text}],
        )
    else:
        resp = client.responses.create(
            model=DEFAULT_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": user_text},
            ],
        )

    # Persist response id (so the thread continues)
    st.session_state.prev_response_id = resp.id

    # Manual text extraction (robust)
    assistant_text = resp.output_text or ""

    # For v0 testing, keep state as-is (no schema-based routing yet)
    current_state = ToolState(**st.session_state.tool_state)

    return ToolResponse(
        assistant_message=assistant_text,
        state=current_state,
        blueprint_md=None,
    )


if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    parsed = call_ai(user_input)
    st.session_state.tool_state = parsed.state.model_dump()

    if parsed.blueprint_md:
        bp = parsed.blueprint_md
        if st.session_state.tool_state.get("mode") == "BUILDER":
            issues = run_contradiction_scan(bp)
            bp += "\n\n## Consistency check (auto)\n"
            if issues:
                for i, issue in enumerate(issues, 1):
                    bp += f"{i}. {issue}\n"
            else:
                bp += "No internal contradictions detected.\n"
        st.session_state.blueprint_md = bp

    st.session_state.messages.append({"role": "assistant", "content": parsed.assistant_message})
    with st.chat_message("assistant"):
        st.markdown(parsed.assistant_message)

# Blueprint output
st.divider()
left, right = st.columns([1, 1])

with left:
    st.subheader("Blueprint")
    if st.session_state.blueprint_md:
        st.download_button(
            "Download blueprint.md",
            st.session_state.blueprint_md.encode(),
            "blueprint.md",
        )
        st.code(st.session_state.blueprint_md, language="markdown")
    else:
        st.info("Blueprint appears after Builder Mode.")

with right:
    st.subheader("Tester instructions")
    st.markdown(
        "• Type messy thoughts\n"
        "• React, don’t over-explain\n"
        "• Say what feels wrong\n"
        "• Stop when blueprint appears"
    )
