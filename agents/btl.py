"""
btl.py - low-level interface to the BTL Runtime gateway.

This module knows ONLY how to talk to the runtime: build the request, send it,
parse the response, surface the savings/cache headers. It has no idea what a
"stock" or a "trade" is - that reasoning lives in agent.py. Keeping this
narrow means every call in the app, chat, verification, research, all funnel
through one place, which is what actually lets us prove heavy runtime usage
for judging.
"""
import os
import json
import requests


class BTLRuntimeError(Exception):
    pass


class BTLClient:
    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.environ.get("GATEWAY_API_KEY", "")
        self.base_url = (base_url or os.environ.get("GATEWAY_BASE_URL", "https://api.badtheorylabs.com/v1")).rstrip("/")
        self.model = model or os.environ.get("GATEWAY_MODEL", "gpt-4.1-mini")
        self.last_headers = {}

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages, temperature=0.3, max_tokens=1200, tools=None, response_format=None):
        """Single call point for every LLM interaction in the app.

        messages: list[{"role": ..., "content": ...}]
        Returns dict: {content, raw, savings: {cache_tier, benchmark_cost, charge, saved}}
        """
        if not self.api_key:
            raise BTLRuntimeError(
                "GATEWAY_API_KEY is not set. Add your BTL workspace key to .env before running live."
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        if response_format:
            payload["response_format"] = response_format

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            data=json.dumps(payload),
            timeout=60,
        )

        # Capture Runtime's proof-of-work headers regardless of status, useful for
        # showing "best use of runtime" evidence in the demo.
        self.last_headers = {
            "request_id": resp.headers.get("x-btl-request-id"),
            "cache_tier": resp.headers.get("x-btl-cache-tier"),
            "benchmark_cost": resp.headers.get("x-btl-benchmark-cost"),
            "customer_charge": resp.headers.get("x-btl-customer-charge"),
            "saved": resp.headers.get("x-btl-saved"),
        }

        if resp.status_code != 200:
            raise BTLRuntimeError(self._clean_error(resp))

        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})

        return {
            "content": message.get("content", ""),
            "raw": data,
            "savings": self.last_headers,
        }

    def _clean_error(self, resp):
        """Turn the runtime's JSON error body into one clean sentence instead of a
        raw JSON dump, and add specific guidance for the cases people actually hit."""
        try:
            body = resp.json()
            err = body.get("error", {})
            message = err.get("message", "").strip()
            code = err.get("code", "")
        except Exception:
            message = ""
            code = ""

        if resp.status_code == 402 or code == "gateway_insufficient_credits":
            return (
                "The workspace is out of runtime credits. Add credits from the BTL "
                "dashboard, connect your own provider key, or set GATEWAY_MODEL in .env "
                "to an explicitly free route (one ending in :free) which stays free at "
                "zero upstream cost."
            )
        if resp.status_code == 500:
            return "The runtime had an internal error on that request. This is on their end, try again in a moment."
        if message:
            return f"Runtime error {resp.status_code}: {message}"
        return f"Runtime error {resp.status_code}, no further detail returned."
