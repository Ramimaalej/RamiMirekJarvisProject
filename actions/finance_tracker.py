import logging
import os
from typing import Any

logger = logging.getLogger("finance_tracker")


class FinanceClient:
    def __init__(self, client_id: str = "", secret: str = "", access_token: str = ""):
        self._client_id = client_id or os.environ.get("PLAID_CLIENT_ID", "")
        self._secret = secret or os.environ.get("PLAID_SECRET", "")
        self._access_token = access_token or os.environ.get("PLAID_ACCESS_TOKEN", "")
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import plaid
            from plaid.api import plaid_api
        except ImportError as exc:
            raise ValueError("Plaid support is missing — install plaid-python") from exc

        if not self._client_id or not self._secret:
            raise ValueError(
                "Plaid credentials required — set PLAID_CLIENT_ID, PLAID_SECRET env vars"
            )

        configuration = plaid.Configuration(
            host=plaid.Environment.Sandbox,
            api_key={
                "clientId": self._client_id,
                "secret": self._secret,
                "plaidVersion": "2020-09-14",
            },
        )
        api_client = plaid.ApiClient(configuration)
        self._client = plaid_api.PlaidApi(api_client)
        return self._client

    def get_accounts(self) -> list[dict[str, Any]]:
        if not self._access_token:
            return []
        client = self._get_client()
        try:
            response = client.accounts_get(
                {"access_token": self._access_token}
            )
            return [
                {
                    "id": a.account_id,
                    "name": a.name,
                    "type": a.type,
                    "subtype": a.subtype,
                    "balance": a.balances.current,
                    "currency": a.balances.iso_currency_code or "USD",
                }
                for a in response.accounts
            ]
        except Exception as e:
            logger.warning("get_accounts error: %s", e)
            return []

    def get_transactions(
        self, start_date: str, end_date: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        if not self._access_token:
            return []
        client = self._get_client()
        try:
            response = client.transactions_sync(
                {
                    "access_token": self._access_token,
                    "count": limit,
                }
            )
            return [
                {
                    "id": t.transaction_id,
                    "name": t.name,
                    "amount": t.amount,
                    "date": str(t.date),
                    "category": t.category[0] if t.category else "",
                    "merchant": t.merchant_name or "",
                }
                for t in (response.added or [])[:limit]
            ]
        except Exception as e:
            logger.warning("get_transactions error: %s", e)
            return []

    def get_spending_summary(self, days: int = 30) -> dict[str, Any]:
        from datetime import datetime, timedelta, timezone
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        txns = self.get_transactions(
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
        )
        if not txns:
            return {"total": 0, "categories": {}, "count": 0}

        total = sum(abs(t["amount"]) for t in txns)
        categories: dict[str, float] = {}
        for t in txns:
            cat = t["category"] or "Other"
            categories[cat] = categories.get(cat, 0) + abs(t["amount"])

        return {
            "total": round(total, 2),
            "count": len(txns),
            "categories": {k: round(v, 2) for k, v in sorted(categories.items(), key=lambda x: -x[1])},
            "period_days": days,
        }

    def get_account_balances(self) -> list[dict[str, Any]]:
        return self.get_accounts()


# ── Convenience ──────────────────────────────────────────────────────────

_client_cache: FinanceClient | None = None


def _get_client() -> FinanceClient:
    global _client_cache
    if _client_cache is None:
        _client_cache = FinanceClient()
    return _client_cache
