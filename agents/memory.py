"""
memory.py - persistent context layer.

Two kinds of memory, kept deliberately distinct because they get used differently:

1. MemoryFact - durable facts about the USER (preferences, constraints, risk appetite
   drift over time). Retrieved by simple relevance scoring against the current query.
2. ThesisEntry - durable facts about calls WE made on a TICKER. Used for live
   contradiction-checking (pillar: native action / judgment) and, once an outcome is
   known, for the confidence-scoring improvement loop.

This module intentionally avoids a heavyweight vector store for the hackathon window -
retrieval here is recency + keyword overlap, which is honest about what it is and easy
to swap for embedding-based retrieval later without touching callers.
"""
from datetime import datetime
from models import MemoryFact, ThesisEntry, CalcTypeConfidence, VerificationLog
from extensions import db


def add_fact(user_id, content, kind="fact", source="chat"):
    fact = MemoryFact(user_id=user_id, kind=kind, content=content, source=source)
    db.session.add(fact)
    db.session.commit()
    return fact


def relevant_facts(user_id, query_text, limit=6):
    """Cheap relevance: keyword overlap + recency bias. Good enough for a single-user
    session store; swap for embedding cosine similarity when moving past hackathon scope."""
    facts = MemoryFact.query.filter_by(user_id=user_id, active=True).order_by(MemoryFact.created_at.desc()).all()
    if not facts:
        return []

    query_words = set(query_text.lower().split())
    scored = []
    for f in facts:
        overlap = len(query_words & set(f.content.lower().split()))
        scored.append((overlap, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [f for _, f in scored[:limit]]
    return top


def facts_as_context(facts):
    if not facts:
        return ""
    return "; ".join(f.content for f in facts)


def record_thesis(user_id, ticker, direction, reasoning, price_at_call):
    entry = ThesisEntry(
        user_id=user_id, ticker=ticker, direction=direction,
        reasoning=reasoning, price_at_call=price_at_call,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def ticker_thesis_history(user_id, ticker, limit=5):
    return (
        ThesisEntry.query.filter_by(user_id=user_id, ticker=ticker)
        .order_by(ThesisEntry.created_at.desc())
        .limit(limit)
        .all()
    )


def thesis_as_context(entries):
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"[{e.created_at.date()}] {e.direction.upper()} at {e.price_at_call}: {e.reasoning[:200]}")
    return " | ".join(lines)


def check_outcomes(user_id, current_price_fn, min_age_hours=0):
    """Walk unresolved thesis entries and, if we can get a current price, score whether
    the call was directionally right. This is what makes 'continuous improvement' visible
    across a demo instead of theoretical."""
    unresolved = ThesisEntry.query.filter_by(user_id=user_id, outcome_checked=False).all()
    updated = []
    for entry in unresolved:
        price_now = current_price_fn(entry.ticker)
        if price_now is None:
            continue
        moved_up = price_now > entry.price_at_call
        correct = moved_up if entry.direction == "long" else (not moved_up if entry.direction == "short" else None)
        entry.outcome_checked = True
        entry.outcome_correct = correct
        entry.price_at_check = price_now
        updated.append(entry)
    if updated:
        db.session.commit()
    return updated


# ---- verification / confidence loop (works alongside tool.run_calc_code) ----

def log_verification(user_id, calc_type, llm_claimed, executed_result, mismatched):
    log = VerificationLog(
        user_id=user_id, calc_type=calc_type,
        llm_claimed=str(llm_claimed), executed_result=str(executed_result),
        mismatched=mismatched,
    )
    db.session.add(log)

    conf = CalcTypeConfidence.query.filter_by(calc_type=calc_type).first()
    if not conf:
        conf = CalcTypeConfidence(calc_type=calc_type, total_checks=0, mismatches=0)
        db.session.add(conf)
    conf.total_checks += 1
    if mismatched:
        conf.mismatches += 1

    db.session.commit()
    return conf


def confidence_for(calc_type):
    conf = CalcTypeConfidence.query.filter_by(calc_type=calc_type).first()
    if not conf:
        return 0.0
    return conf.error_rate
