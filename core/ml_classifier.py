from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.linear_model import SGDClassifier

from core.database import supabase


def _normalize_description(description: str) -> str:
    text = (description or "").lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _map_statement_type(value: Optional[str]) -> str:
    if not value:
        return "expense"
    v = value.lower().strip()
    if v in {"credit", "income"}:
        return "income"
    if v in {"debit", "expense"}:
        return "expense"
    return "expense"


@dataclass
class UserModel:
    vectorizer: HashingVectorizer
    type_classifier: Optional[SGDClassifier]
    category_classifier: Optional[SGDClassifier]
    fallback_type: str
    fallback_category: str
    total_samples: int


class TransactionMLService:
    """
    Lightweight per-user text classifier trained from:
      1) confirmed transactions table
      2) ml_feedback corrections
    """

    def __init__(self):
        self._cache: dict[str, UserModel] = {}

    def refresh_user_model(self, user_id: str) -> UserModel:
        model = self._train_model(user_id)
        self._cache[user_id] = model
        return model

    def _get_user_model(self, user_id: str) -> UserModel:
        model = self._cache.get(user_id)
        if model:
            return model
        return self.refresh_user_model(user_id)

    def _train_model(self, user_id: str) -> UserModel:
        transactions = (
            supabase.table("transactions")
            .select("description,type,category")
            .eq("user_id", user_id)
            .execute()
            .data
            or []
        )

        feedback = (
            supabase.table("ml_feedback")
            .select("description,corrected_type,corrected_category")
            .eq("user_id", user_id)
            .execute()
            .data
            or []
        )

        x_text: list[str] = []
        y_type: list[str] = []
        y_category: list[str] = []

        for row in transactions:
            desc = _normalize_description(row.get("description", ""))
            txn_type = _map_statement_type(row.get("type"))
            category = (row.get("category") or "unknown").strip() or "unknown"
            if not desc:
                continue
            x_text.append(desc)
            y_type.append(txn_type)
            y_category.append(category)

        for row in feedback:
            desc = _normalize_description(row.get("description", ""))
            txn_type = _map_statement_type(row.get("corrected_type"))
            category = (row.get("corrected_category") or "unknown").strip() or "unknown"
            if not desc:
                continue
            x_text.append(desc)
            y_type.append(txn_type)
            y_category.append(category)

        vectorizer = HashingVectorizer(n_features=2**14, alternate_sign=False, ngram_range=(1, 2))

        # Defaults for cold-start users
        fallback_type = "expense"
        fallback_category = "unknown"

        if y_type:
            fallback_type = max(set(y_type), key=y_type.count)
        if y_category:
            fallback_category = max(set(y_category), key=y_category.count)

        type_classifier: Optional[SGDClassifier] = None
        category_classifier: Optional[SGDClassifier] = None

        if len(set(y_type)) >= 2 and x_text:
            x_vec = vectorizer.transform(x_text)
            type_classifier = SGDClassifier(loss="log_loss", max_iter=1000, tol=1e-3)
            type_classifier.fit(x_vec, y_type)

        if len(set(y_category)) >= 2 and x_text:
            x_vec = vectorizer.transform(x_text)
            category_classifier = SGDClassifier(loss="log_loss", max_iter=1000, tol=1e-3)
            category_classifier.fit(x_vec, y_category)

        return UserModel(
            vectorizer=vectorizer,
            type_classifier=type_classifier,
            category_classifier=category_classifier,
            fallback_type=fallback_type,
            fallback_category=fallback_category,
            total_samples=len(x_text),
        )

    def predict(self, user_id: str, description: str, fallback_statement_type: Optional[str] = None) -> tuple[str, str]:
        model = self._get_user_model(user_id)
        text = _normalize_description(description)
        if not text:
            return _map_statement_type(fallback_statement_type), "unknown"

        x_vec = model.vectorizer.transform([text])

        if model.type_classifier:
            predicted_type = model.type_classifier.predict(x_vec)[0]
        else:
            predicted_type = _map_statement_type(fallback_statement_type) if fallback_statement_type else model.fallback_type

        if model.category_classifier:
            predicted_category = model.category_classifier.predict(x_vec)[0]
        else:
            predicted_category = model.fallback_category

        # Keep category aligned with user-configured categories when available
        categories = (
            supabase.table("user_categories")
            .select("type,category")
            .eq("user_id", user_id)
            .execute()
            .data
            or []
        )
        allowed = [c["category"] for c in categories if c.get("type") == predicted_type]
        if allowed:
            if predicted_category not in allowed:
                predicted_category = allowed[0]

        return predicted_type, predicted_category


ml_service = TransactionMLService()
