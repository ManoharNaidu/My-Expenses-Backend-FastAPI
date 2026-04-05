from unittest.mock import MagicMock

from tests.conftest import auth_headers, make_user, mock_supabase


def _chain(data):
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.in_.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.limit.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.execute.return_value = MagicMock(data=data)
    return chain


def test_review_staging_graph_endpoint(client):
    user = make_user()
    users_chain = _chain([user])
    staging_chain = _chain(
        [
            {
                "id": "stg-1",
                "date": "2026-04-01",
                "description": "Coffee Shop",
                "amount": 6.5,
                "predicted_type": "expense",
                "predicted_category": "Food",
                "is_confirmed": False,
            }
        ]
    )
    transactions_chain = _chain([])

    mock_supabase.table.side_effect = [users_chain, staging_chain, transactions_chain]
    response = client.post(
        "/api/v1/ai/review-staging",
        headers=auth_headers(),
        json={"staging_ids": ["stg-1"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["graph"] == "review_staging"
    assert body["summary"]["transactions_found"] == 1
    assert body["transactions"][0]["suggested_category"] == "Food"


def test_budget_coach_graph_endpoint(client):
    user = make_user()
    users_chain = _chain([user])
    budget_chain = _chain([{"monthly_limit": 1000, "alerts_enabled": True}])
    transactions_chain = _chain(
        [
            {
                "id": "tx-1",
                "date": "2026-04-01",
                "description": "Groceries",
                "amount": 120,
                "type": "expense",
                "category": "Food",
            },
            {
                "id": "tx-2",
                "date": "2026-04-02",
                "description": "Salary",
                "amount": 2000,
                "type": "income",
                "category": "Salary",
            },
        ]
    )
    recurring_chain = _chain(
        [
            {
                "id": "rec-1",
                "amount": 30,
                "type": "expense",
                "category": "Subscriptions",
                "description": "Music",
                "start_date": "2026-01-01",
                "day_of_month": 2,
                "is_active": True,
            }
        ]
    )

    mock_supabase.table.side_effect = [
        users_chain,
        budget_chain,
        transactions_chain,
        recurring_chain,
    ]
    response = client.get(
        "/api/v1/ai/budget-coach?year=2026&month=4",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["graph"] == "budget_coach"
    assert body["budget_status"]["expense_spent"] == 120.0
    assert body["coach_response"]["headline"]
