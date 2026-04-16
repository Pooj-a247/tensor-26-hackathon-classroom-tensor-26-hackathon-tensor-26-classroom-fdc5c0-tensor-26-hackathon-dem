

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import math

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Learning Gap Detector API",
    description="Detects student learning gaps and generates a 7-day study plan.",
    version="1.0.0",
)

# Allow your HTML frontend (on any origin) to call this API during the hackathon
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request / Response schemas ─────────────────────────────────────────────────

class Topic(BaseModel):
    name: str
    accuracy: float       # 0.0 – 1.0  (e.g. 0.5 = 50% correct)
    time_spent: int       # minutes spent studying this topic

class AnalyzeRequest(BaseModel):
    student_id: int
    topics: List[Topic]

# ── Core logic ─────────────────────────────────────────────────────────────────

ACCURACY_THRESHOLD = 0.6   # below this → topic is "weak"
TIME_THRESHOLD = 60        # minutes; spending a lot of time AND still failing = strong gap

def detect_gaps(topics: List[Topic]) -> List[dict]:
    """
    Rule-based gap detection:
    - Weak topic   : accuracy < 0.6
    - Strong gap   : accuracy < 0.6 AND time_spent > 60 min
                     (student is investing time but still struggling → urgent)
    Returns a list of weak topic dicts with severity label.
    """
    gaps = []
    for t in topics:
        is_weak = t.accuracy < ACCURACY_THRESHOLD

        if not is_weak:
            continue  # topic is fine, skip

        # Classify severity for this individual topic
        if t.accuracy < 0.4 and t.time_spent > TIME_THRESHOLD:
            severity = "high"    # really struggling despite effort
        elif t.accuracy < 0.6 and t.time_spent > TIME_THRESHOLD:
            severity = "medium"  # struggling + spending time
        else:
            severity = "low"     # weak but not yet critical

        gaps.append({
            "topic": t.name,
            "accuracy": round(t.accuracy, 2),
            "time_spent": t.time_spent,
            "severity": severity,
        })

    return gaps


def overall_severity(gaps: List[dict]) -> str:
    """
    Roll up individual gap severities into one overall label for the student.
    High if any single topic is high; medium if medium exists; else low.
    """
    severities = [g["severity"] for g in gaps]
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def build_study_plan(gaps: List[dict]) -> List[dict]:
    """
    Build a 7-day study plan dynamically from the detected gaps.

    Strategy:
    - Day slots are shared across all weak topics in round-robin order.
    - Each day gets one focus topic and a session type that cycles:
        Day 1: Concept revision
        Day 2: Guided practice
        Day 3: Timed quiz
        (then repeats for the next topic block)
    - If there are no gaps, we still return a generic revision week.
    """

    # If no weak topics, return a generic maintenance plan
    if not gaps:
        return [
            {"day": f"Day {i+1}", "topic": "General Review",
             "session_type": stype, "duration_minutes": 30}
            for i, stype in enumerate([
                "Recap all topics", "Mixed practice set", "Timed quiz",
                "Error analysis", "Concept revision", "Full mock test", "Rest & reflect"
            ])
        ]

    # Session types cycle: revision → practice → quiz
    SESSION_CYCLE = ["Concept revision", "Guided practice", "Timed quiz"]

    plan = []
    num_gaps = len(gaps)

    for day_num in range(7):
        # Which gap topic gets focus today (round-robin)
        gap = gaps[day_num % num_gaps]

        # Which session type for today
        session = SESSION_CYCLE[day_num % len(SESSION_CYCLE)]

        # Allocate more time to high-severity gaps
        duration = 60 if gap["severity"] == "high" else 45 if gap["severity"] == "medium" else 30

        plan.append({
            "day": f"Day {day_num + 1}",
            "topic": gap["topic"],
            "session_type": session,
            "duration_minutes": duration,
            "note": _session_note(session, gap["topic"]),
        })

    return plan


def _session_note(session_type: str, topic: str) -> str:
    """Return a short human-readable instruction for each session type."""
    notes = {
        "Concept revision": f"Re-read core {topic} concepts. Focus on definitions and formulas.",
        "Guided practice": f"Solve 10 structured {topic} problems, checking each answer.",
        "Timed quiz": f"Complete a 20-minute {topic} quiz under exam conditions.",
    }
    return notes.get(session_type, "Study session")


# ── Endpoint ───────────────────────────────────────────────────────────────────

@app.post("/analyze")
def analyze_student(request: AnalyzeRequest):
    """
    Main analysis endpoint.

    1. Detect weak topics using rule-based thresholds.
    2. Compute an overall gap severity score.
    3. Generate a personalised 7-day study plan.
    """

    # Step 1 — find gaps
    gaps = detect_gaps(request.topics)

    # Step 2 — overall severity
    severity = overall_severity(gaps) if gaps else "none"

    # Step 3 — build the plan
    study_plan = build_study_plan(gaps)

    return {
        "student_id": request.student_id,
        "total_topics_analyzed": len(request.topics),
        "weak_topics": gaps,
        "gap_severity": severity,
        "study_plan": study_plan,
    }


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "message": "Learning Gap Detector API is running."}
