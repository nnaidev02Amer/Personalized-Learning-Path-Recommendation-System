"""AI learning assistant grounded in the student's real data and model outputs.

Two modes, chosen automatically:

* **rules** (default, no API key needed): detects the question's intent and
  answers from the ML outputs with fixed templates -- every number comes from
  the models / database.
* **claude**: when ``ANTHROPIC_API_KEY`` is set (and ``ASSISTANT_PROVIDER`` is not
  ``rules``), the same grounding context is sent to Claude with instructions to
  answer only from it. Any API error or refusal falls back to the rules answer.

Environment: ``ANTHROPIC_API_KEY``, ``ANTHROPIC_MODEL`` (default claude-opus-5-5),
``ASSISTANT_PROVIDER`` = auto | rules | claude.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("backend.assistant")
DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are the learning assistant inside PathWise, a personalised learning app.
Answer the student's question using ONLY the JSON context provided: their progress numbers and the
outputs of the app's models (course recommendations, Bayesian Knowledge Tracing skill mastery,
adaptive difficulty suggestion, predicted quiz scores, learning-style prediction) together with each
model's measured evaluation. Rules:
- Do not invent courses, numbers or facts that are not in the context. If the context does not
  contain the answer, say so briefly and suggest where in the app to look.
- When you cite a model output, mention its uncertainty or evaluation where relevant (for example a
  predicted score's typical error, or that the learning-style model is not reliable).
- The seeded students' histories are synthetic; if the context marks the history as synthetic and
  the student asks about accuracy, say so.
- Be encouraging, specific and brief: at most about 150 words, plain text, short bullet points allowed."""

INTENTS = {
    "recommend": ("recommend", "next", "course", "learn next", "should i take", "suggest"),
    "skills": ("weak", "gap", "struggl", "skill", "improve", "mastery", "practice"),
    "difficulty": ("difficult", "hard", "easy", "level", "challenge"),
    "prediction": ("predict", "score", "pass", "quiz", "exam", "expect"),
    "style": ("style", "visual", "auditory", "kinesthetic", "reading"),
    "progress": ("progress", "doing", "how am i", "streak", "time", "stat"),
}


def detect_intent(message: str) -> str:
    text = message.lower()
    scores = {intent: sum(k in text for k in keys) for intent, keys in INTENTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "overview"


# --------------------------------------------------------------- rules mode
def _recs(ctx) -> str:
    items = ctx["recommendations"]["items"][:3]
    if not items:
        return "You have no unlocked courses left to recommend right now - finish your active courses first."
    lines = [f"- {i['title']} ({i['code']}): {i['reasons'][0]}" for i in items]
    return "Top recommended next courses (hybrid recommender):\n" + "\n".join(lines)


def _skills(ctx) -> str:
    s = ctx["skills"]
    if s["gaps"]:
        lines = [f"- {g['skill'].replace('-', ' ')} ({g['topic']}): estimated mastery {g['mastery']:.0%} "
                 f"from {g['observations']} answers" for g in s["gaps"][:4]]
        text = "Skills to strengthen (Bayesian Knowledge Tracing):\n" + "\n".join(lines)
    else:
        text = "All skills assessed so far are above the mastery threshold."
    if s["not_yet_assessed"]:
        text += f"\nNot yet assessed in your active courses: {', '.join(x.replace('-', ' ') for x in s['not_yet_assessed'][:4])}."
    return text


def _difficulty(ctx) -> str:
    d = ctx["difficulty"]
    best = max(d["arms"], key=lambda a: a["expected_success"])
    text = (f"Suggested next difficulty: {d['recommended_difficulty']}. The bandit estimates a "
            f"{best['expected_success']:.0%} chance of a 'productive' quiz result (60-89%) at {best['difficulty']} level.")
    if d["exploring"]:
        text += " This suggestion is partly exploratory because there is little data at that level."
    return text


def _prediction(ctx) -> str:
    items = [i for i in ctx["predictions"]["items"] if i["status"] == "active"] or ctx["predictions"]["items"]
    if not items:
        return "There is no course quiz to predict yet - enrol in a course first."
    lines = [f"- {i['course_title']}: about {i['predicted_score']:.0f}% (typical error +/- {i['expected_error_mae']:.0f}), "
             f"pass outlook {i['pass_probability_hint']}" for i in items[:3]]
    return "Predicted quiz scores (gradient-boosting model):\n" + "\n".join(lines)


def _style(ctx) -> str:
    st = ctx["learning_style"]
    text = f"The model predicts '{st['predicted_style']}'; your self-reported style is '{st['self_reported_style'] or 'not set'}'."
    if not st["reliable"]:
        ev = st["evaluation"]
        text += (f" Note: this model is not reliable on the current data (cross-validated accuracy "
                 f"{ev['cv_accuracy_mean']:.0%} vs {ev['baseline_majority_accuracy']:.0%} for always guessing the most "
                 f"common style), so your self-reported style is used.")
    return text


def _progress(ctx) -> str:
    p = ctx["summary"]
    avg = f"{p['average_quiz_score']:.0f}%" if p["average_quiz_score"] is not None else "no quizzes yet"
    return (f"You have completed {p['completed_courses']} course(s), have {p['active_courses']} active, "
            f"{p['lessons_pending']} lessons pending, average quiz score {avg}, and studied "
            f"{p['minutes_last_7_days']:.0f} minutes in the last 7 days (streak: {p['current_streak_days']} days).")


RULES = {"recommend": _recs, "skills": _skills, "difficulty": _difficulty, "prediction": _prediction,
         "style": _style, "progress": _progress}


def rules_answer(intent: str, ctx: dict) -> str:
    if intent == "overview":
        return "\n\n".join([_progress(ctx), _recs(ctx), _skills(ctx)])
    return RULES[intent](ctx)


# -------------------------------------------------------------- claude mode
def _claude_answer(message: str, ctx: dict) -> tuple[str, str]:
    import anthropic

    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    client = anthropic.Anthropic(timeout=60.0, max_retries=2)
    response = client.beta.messages.create(
        model=model,
        max_tokens=2048,   # short chat answers by design
        system=SYSTEM_PROMPT,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content":
                   f"<context>\n{json.dumps(ctx, default=str)}\n</context>\n\nStudent question: {message}"}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to answer")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise RuntimeError("Empty response from Claude")
    return text, response.model


def provider() -> str:
    choice = os.environ.get("ASSISTANT_PROVIDER", "auto").lower()
    if choice == "rules":
        return "rules"
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return "claude" if (choice == "claude" or has_key) else "rules"


def answer(message: str, ctx: dict) -> dict:
    intent = detect_intent(message)
    fallback = rules_answer(intent, ctx)
    result = {"intent": intent, "source": "rules", "model": None, "answer": fallback, "note": None}
    if provider() != "claude":
        return result
    try:
        import anthropic
    except ImportError:
        result["note"] = "The 'anthropic' package is not installed; showing the built-in answer."
        return result
    try:
        text, model = _claude_answer(message, ctx)
        result.update(source="claude", model=model, answer=text)
    except anthropic.AuthenticationError:
        result["note"] = "The Claude API key was rejected; showing the built-in answer."
    except anthropic.RateLimitError:
        result["note"] = "The Claude API is rate-limited right now; showing the built-in answer."
    except anthropic.APIStatusError as exc:
        log.warning("Claude API error %s: %s", exc.status_code, exc.message)
        result["note"] = f"Claude API error ({exc.status_code}); showing the built-in answer."
    except anthropic.APIConnectionError:
        result["note"] = "Could not reach the Claude API; showing the built-in answer."
    except RuntimeError as exc:     # refusal or empty answer
        result["note"] = f"{exc}; showing the built-in answer."
    return result
