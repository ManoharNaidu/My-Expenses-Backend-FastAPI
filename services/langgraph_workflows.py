from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from core.database import supabase
from core.ml_classifier import _normalize_description, ml_service


def _normalize_type(raw: Optional[str]) -> str:
    value = (raw or "").strip().lower()
    if value in {"income", "credit"}:
        return "income"
    return "expense"


class ReviewGraphState(TypedDict, total=False):
    user_id: str
    staging_ids: list[str]
    staging_rows: list[dict[str, Any]]
    existing_rows: list[dict[str, Any]]
    reviewed_transactions: list[dict[str, Any]]
    summary: dict[str, Any]


class BudgetCoachState(TypedDict, total=False):
    user_id: str
    year: int
    month: int
    budget_goal: dict[str, Any]
    transactions: list[dict[str, Any]]
    recurring_transactions: list[dict[str, Any]]
    category_totals: list[dict[str, Any]]
    budget_status: dict[str, Any]
    coach_response: dict[str, Any]


def run_review_staging_graph(user_id: str, staging_ids: Optional[list[str]] = None) -> dict[str, Any]:
    state = review_staging_graph.invoke({"user_id": user_id, "staging_ids": staging_ids or []})
    return {
        "graph": "review_staging",
        "summary": state["summary"],
        "transactions": state["reviewed_transactions"],
    }


def run_budget_coach_graph(user_id: str, year: int, month: int) -> dict[str, Any]:
    state = budget_coach_graph.invoke({"user_id": user_id, "year": year, "month": month})
    return {
        "graph": "budget_coach",
        "period": {"year": year, "month": month},
        "budget_goal": state["budget_goal"],
        "budget_status": state["budget_status"],
        "category_totals": state["category_totals"],
        "recurring_transactions": state["recurring_transactions"],
        "coach_response": state["coach_response"],
    }


def _load_staging_transactions(state: ReviewGraphState) -> ReviewGraphState:
    query = (
        supabase.table("transactions_staging")
        .select("*")
        .eq("user_id", state["user_id"])
        .eq("is_confirmed", False)
    )
    if state.get("staging_ids"):
        query = query.in_("id", state["staging_ids"])
    rows = query.execute().data or []
    return {"staging_rows": rows}


def _load_existing_transactions(state: ReviewGraphState) -> ReviewGraphState:
    rows = (
        supabase.table("transactions")
        .select("id,date,description,amount,type,category")
        .eq("user_id", state["user_id"])
        .execute()
        .data
        or []
    )
    return {"existing_rows": rows}


def _review_transactions(state: ReviewGraphState) -> ReviewGraphState:
    existing_rows = state.get("existing_rows", [])
    fingerprint_index = {
        (
            row.get("date"),
            float(row.get("amount") or 0),
            _normalize_description(row.get("description") or ""),
        ): row
        for row in existing_rows
    }

    reviewed = []
    for row in state.get("staging_rows", []):
        description = row.get("description") or ""
        normalized_description = _normalize_description(description)
        predicted_type = row.get("predicted_type")
        predicted_category = row.get("predicted_category")

        if not predicted_type or not predicted_category or predicted_category == "unknown":
            predicted_type, predicted_category = ml_service.predict(
                user_id=state["user_id"],
                description=description,
                fallback_statement_type=row.get("predicted_type"),
            )

        fingerprint = (
            row.get("date"),
            float(row.get("amount") or 0),
            normalized_description,
        )
        duplicate_match = fingerprint_index.get(fingerprint)

        review_flags = []
        confidence = "high"

        if duplicate_match:
            review_flags.append("possible_duplicate")
            confidence = "low"
        if not normalized_description:
            review_flags.append("missing_description")
            confidence = "low"
        if predicted_category == "unknown":
            review_flags.append("needs_category_confirmation")
            confidence = "low"

        reviewed.append(
            {
                "id": row.get("id"),
                "date": row.get("date"),
                "description": description,
                "amount": row.get("amount"),
                "suggested_type": _normalize_type(predicted_type),
                "suggested_category": predicted_category,
                "existing_prediction": {
                    "type": row.get("predicted_type"),
                    "category": row.get("predicted_category"),
                },
                "duplicate_of_transaction_id": duplicate_match.get("id") if duplicate_match else None,
                "review_flags": review_flags,
                "confidence": confidence,
            }
        )

    return {"reviewed_transactions": reviewed}


def _summarize_review(state: ReviewGraphState) -> ReviewGraphState:
    reviewed = state.get("reviewed_transactions", [])
    duplicate_count = sum(1 for txn in reviewed if "possible_duplicate" in txn["review_flags"])
    low_confidence_count = sum(1 for txn in reviewed if txn["confidence"] == "low")
    ready_count = len(reviewed) - low_confidence_count
    return {
        "summary": {
            "transactions_found": len(reviewed),
            "ready_to_confirm": ready_count,
            "needs_review": low_confidence_count,
            "possible_duplicates": duplicate_count,
        }
    }


def _load_budget_context(state: BudgetCoachState) -> BudgetCoachState:
    start = f"{state['year']}-{str(state['month']).zfill(2)}-01"
    end = f"{state['year']}-{str(state['month']).zfill(2)}-31"

    budget_rows = (
        supabase.table("budget_goals")
        .select("*")
        .eq("user_id", state["user_id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    budget_goal = budget_rows[0] if budget_rows else {"monthly_limit": 0, "alerts_enabled": True}

    transactions = (
        supabase.table("transactions")
        .select("id,date,description,amount,type,category")
        .eq("user_id", state["user_id"])
        .gte("date", start)
        .lte("date", end)
        .execute()
        .data
        or []
    )

    recurring_transactions = (
        supabase.table("recurring_transactions")
        .select("id,amount,type,category,description,start_date,day_of_month,is_active")
        .eq("user_id", state["user_id"])
        .eq("is_active", True)
        .execute()
        .data
        or []
    )

    return {
        "budget_goal": budget_goal,
        "transactions": transactions,
        "recurring_transactions": recurring_transactions,
    }


def _analyze_spending(state: BudgetCoachState) -> BudgetCoachState:
    totals: dict[str, float] = defaultdict(float)
    expense_spent = 0.0

    for tx in state.get("transactions", []):
        tx_type = _normalize_type(tx.get("type"))
        amount = float(tx.get("amount") or 0)
        if tx_type != "expense":
            continue
        expense_spent += amount
        category = (tx.get("category") or "uncategorized").strip() or "uncategorized"
        totals[category] += amount

    monthly_limit = float(state.get("budget_goal", {}).get("monthly_limit") or 0)
    progress = (expense_spent / monthly_limit) if monthly_limit > 0 else 0.0
    remaining = max(monthly_limit - expense_spent, 0.0) if monthly_limit > 0 else 0.0

    category_totals = [
        {"category": category, "amount": round(amount, 2)}
        for category, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]

    return {
        "category_totals": category_totals,
        "budget_status": {
            "monthly_limit": monthly_limit,
            "expense_spent": round(expense_spent, 2),
            "progress": round(progress, 4),
            "remaining": round(remaining, 2),
            "is_over_budget": monthly_limit > 0 and expense_spent > monthly_limit,
        },
    }


def _compose_coach_response(state: BudgetCoachState) -> BudgetCoachState:
    budget_status = state.get("budget_status", {})
    category_totals = state.get("category_totals", [])
    recurring = state.get("recurring_transactions", [])

    headline = "Budget looks under control."
    if budget_status.get("is_over_budget"):
        headline = "You are over budget for this month."
    elif budget_status.get("progress", 0) >= 0.85:
        headline = "You are close to your monthly budget limit."

    top_category = category_totals[0] if category_totals else None
    recommendations = []

    if top_category:
        recommendations.append(
            f"Review {top_category['category']} first because it is your highest expense category this month."
        )
    if recurring:
        recommendations.append(
            f"You have {len(recurring)} active recurring transactions. Check whether any should be paused or reduced."
        )
    if budget_status.get("monthly_limit", 0) == 0:
        recommendations.append("Set a monthly budget goal so progress and over-budget warnings become meaningful.")
    elif budget_status.get("is_over_budget"):
        recommendations.append(
            f"Reduce another {round(budget_status.get('expense_spent', 0) - budget_status.get('monthly_limit', 0), 2)} to get back within budget."
        )
    else:
        recommendations.append(
            f"You still have {budget_status.get('remaining', 0)} left in this month's budget."
        )

    return {
        "coach_response": {
            "headline": headline,
            "top_category": top_category,
            "recommendations": recommendations,
            "generated_for": date(state["year"], state["month"], 1).isoformat(),
            "next_step": "Swap the final response node with an LLM later if you want natural-language coaching.",
        }
    }


def _build_review_graph():
    graph = StateGraph(ReviewGraphState)
    graph.add_node("load_staging", _load_staging_transactions)
    graph.add_node("load_existing", _load_existing_transactions)
    graph.add_node("review", _review_transactions)
    graph.add_node("summarize", _summarize_review)
    graph.add_edge(START, "load_staging")
    graph.add_edge("load_staging", "load_existing")
    graph.add_edge("load_existing", "review")
    graph.add_edge("review", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


def _build_budget_coach_graph():
    graph = StateGraph(BudgetCoachState)
    graph.add_node("load_budget_context", _load_budget_context)
    graph.add_node("analyze_spending", _analyze_spending)
    graph.add_node("compose_coach_response", _compose_coach_response)
    graph.add_edge(START, "load_budget_context")
    graph.add_edge("load_budget_context", "analyze_spending")
    graph.add_edge("analyze_spending", "compose_coach_response")
    graph.add_edge("compose_coach_response", END)
    return graph.compile()


review_staging_graph = _build_review_graph()
budget_coach_graph = _build_budget_coach_graph()
