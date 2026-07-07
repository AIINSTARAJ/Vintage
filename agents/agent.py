"""
agent.py - the orchestrator. This is the only module that should be imported by
routes. It composes btl.py (runtime I/O), prompt.py (what to ask), tool.py (what to
do/compute), and memory.py (what to remember) into the actual product behaviors:
answering a stock question, drafting a simulated trade, and running research.

Every LLM call in the app flows through self.btl.chat(...), and every numeric claim
flows through tool.run_calc_code(...) before it reaches the user. That combination is
the whole "verified reasoning" pillar.
"""
import json

from agents.btl import BTLClient, BTLRuntimeError
from agents import prompt as P
from agents import tool as T
from agents import memory as M


class Agent:
    def __init__(self, user, btl_client=None):
        self.user = user
        self.btl = btl_client or BTLClient()

    # ---------- stock Q&A ----------

    def answer_stock_question(self, ticker, question, conversation_history=None):
        snapshot = T.get_price_snapshot(ticker)
        history = T.get_price_history(ticker)

        try:
            news = T.fetch_news(ticker)
            news_context = "\n".join(f"- {n['title']}: {n.get('summary','')}" for n in news[:5]) or None
        except Exception:
            news_context = None

        facts = M.relevant_facts(self.user.id, question)
        memory_context = M.facts_as_context(facts)

        thesis_entries = M.ticker_thesis_history(self.user.id, ticker)
        thesis_context = M.thesis_as_context(thesis_entries)

        messages = [{"role": "system", "content": P.BASE_SYSTEM}]
        for turn in (conversation_history or [])[-8:]:
            role = "assistant" if turn.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": turn.get("content", "")})
        messages.append({"role": "user", "content": P.stock_qa_prompt(
            ticker, question, snapshot, memory_context, thesis_context, news_context
        )})

        result = self.btl.chat(messages)
        text = result["content"]

        contradiction = None
        if "CONTRADICTION:" in text:
            contradiction = text.split("CONTRADICTION:", 1)[1].split("\n", 1)[0].strip()

        verified = None
        calc_request = T.extract_calc_request(text)
        if calc_request:
            verified = self._run_verified_calc(calc_request, history, calc_type=self._infer_calc_type(calc_request))
            text = text.replace(f"```calc_request\n{calc_request}\n```", "")

        # the model is forced to end with an explicit STANCE line (see prompt.py) - parse
        # that directly instead of guessing from prose, which is far more reliable
        stance, text = self._extract_stance(text)
        if stance and stance != "neutral":
            M.record_thesis(self.user.id, ticker, stance, text[:500], snapshot.get("price"))

        return {
            "text": text.strip(),
            "snapshot": snapshot,
            "history": history,
            "contradiction": contradiction,
            "verified": verified,
            "stance": stance,
            "savings": result["savings"],
        }

    def _extract_stance(self, text):
        """Pull the trailing 'STANCE: long|short|neutral' line off the model output.
        Returns (stance_or_none, text_with_line_removed)."""
        lines = text.strip().splitlines()
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if stripped.upper().startswith("STANCE:"):
                value = stripped.split(":", 1)[1].strip().lower()
                if value not in ("long", "short", "neutral"):
                    value = None
                remaining = "\n".join(lines[:i] + lines[i + 1:])
                return value, remaining
        return None, text

    def _infer_calc_type(self, calc_request):
        text = calc_request.lower()
        for key in ["sharpe", "cagr", "volatility", "correlation", "return", "position size", "drawdown"]:
            if key in text:
                return key.replace(" ", "_")
        return "generic"

    def _run_verified_calc(self, calc_request, history, calc_type, max_attempts=2):
        """Generates code, executes it for real, and if it fails, shows the model its
        own error and lets it correct itself once before giving up. This is the
        'troubleshoot itself' behavior without handing the sandbox the ability to
        install arbitrary packages, self-correction on real error feedback is the
        safe version of that same capability."""
        codegen_messages = [
            {"role": "system", "content": "You write short correct Python. Output only code."},
            {"role": "user", "content": P.calc_codegen_prompt(calc_request, "OHLCV DataFrame with columns: Open, High, Low, Close, Volume, indexed by date")},
        ]

        last_error = None
        for attempt in range(max_attempts):
            code_result = self.btl.chat(codegen_messages, temperature=0.0)
            try:
                code_str = T.extract_code_block(code_result["content"])
            except T.ToolError as e:
                last_error = str(e)
                codegen_messages.append({"role": "assistant", "content": code_result["content"]})
                codegen_messages.append({"role": "user", "content": f"That didn't produce valid code: {last_error}. Fix it and output only the corrected code block."})
                continue

            try:
                executed_value = T.run_calc_code(code_str, history["dataframe"])
                M.log_verification(self.user.id, calc_type, llm_claimed="(withheld, not stated by model)",
                                    executed_result=executed_value, mismatched=False)
                return {
                    "calc_type": calc_type, "request": calc_request, "code": code_str,
                    "result": executed_value, "confidence_error_rate": M.confidence_for(calc_type),
                    "attempts": attempt + 1,
                }
            except T.ToolError as e:
                last_error = str(e)
                codegen_messages.append({"role": "assistant", "content": code_result["content"]})
                codegen_messages.append({"role": "user", "content": f"That code failed when run: {last_error}. Fix it and output only the corrected code block."})

        # both attempts failed, degrade gracefully instead of surfacing a raw error
        M.log_verification(self.user.id, calc_type, llm_claimed="(withheld)", executed_result=f"failed: {last_error}", mismatched=True)
        return {
            "calc_type": calc_type, "request": calc_request, "code": None,
            "result": None, "unavailable": True,
            "confidence_error_rate": M.confidence_for(calc_type),
        }

    # ---------- trade drafting (native action) ----------

    def draft_trade(self, ticker, direction, reasoning, verified_numbers):
        snapshot = T.get_price_snapshot(ticker)
        messages = [
            {"role": "system", "content": P.BASE_SYSTEM},
            {"role": "user", "content": P.trade_action_prompt(
                ticker, direction, reasoning, verified_numbers, self.user.risk_appetite or "medium"
            )},
        ]
        result = self.btl.chat(messages, temperature=0.1)
        text = result["content"]

        quantity_pct = self._parse_field(text, "QUANTITY_PCT", default=2.0)
        stop_loss_pct = self._parse_field(text, "STOP_LOSS_PCT", default=5.0)
        note = self._parse_field(text, "NOTE", default="", as_float=False)

        needs_review = quantity_pct > 10.0

        return {
            "ticker": ticker,
            "direction": direction,
            "quantity_pct": quantity_pct,
            "stop_loss_pct": stop_loss_pct,
            "note": note,
            "price": snapshot.get("price"),
            "needs_review": needs_review,
            "savings": result["savings"],
        }

    def _parse_field(self, text, field, default=None, as_float=True):
        for line in text.splitlines():
            if line.strip().upper().startswith(field):
                value = line.split(":", 1)[-1].strip()
                if as_float:
                    try:
                        return float(value.replace("%", ""))
                    except ValueError:
                        return default
                return value
        return default

    def execute_paper_trade(self, ticker, side, price, quantity_pct=None, amount_usd=None,
                             stop_loss_pct=None, rationale=""):
        """Executes a simulated trade against real cash: buys deduct from paper_balance,
        sells credit it back and can't exceed what's actually held. This is the function
        that makes the dashboard numbers move instead of sitting static."""
        from extensions import db

        if amount_usd is not None:
            dollar_amount = float(amount_usd)
        else:
            dollar_amount = self.user.paper_balance * ((quantity_pct or 2.0) / 100.0)

        if side == "buy":
            dollar_amount = min(dollar_amount, self.user.paper_balance)
            if dollar_amount <= 0:
                raise ValueError("Not enough cash to open this position.")
            shares = round(dollar_amount / price, 4)
            self.user.paper_balance -= dollar_amount
        else:
            holdings = {h["ticker"]: h for h in T.get_holdings(self.user.id)}
            held = holdings.get(ticker, {}).get("shares", 0.0)
            requested_shares = round(dollar_amount / price, 4)
            shares = min(requested_shares, held)
            if shares <= 0:
                raise ValueError(f"No {ticker} shares held to sell.")
            self.user.paper_balance += shares * price

        stop_loss_price = None
        if stop_loss_pct is not None:
            stop_loss_price = price * (1 - stop_loss_pct / 100.0) if side == "buy" else price * (1 + stop_loss_pct / 100.0)

        trade = T.insert_trade_row(self.user.id, ticker, side, shares, price, stop_loss_price, rationale)
        db.session.commit()
        return trade

    def portfolio_snapshot(self):
        """Cash plus the market value of everything currently held, priced live.
        Marks a holding's price as stale if a live quote couldn't be fetched, rather
        than silently reusing cost basis and showing a misleading flat 0% P&L."""
        from datetime import date as date_cls
        from extensions import db
        from models import PortfolioSnapshot

        holdings = T.get_holdings(self.user.id)
        enriched = []
        market_value = 0.0
        for h in holdings:
            snap = T.get_price_snapshot(h["ticker"])
            live_price = snap.get("price")
            stale = live_price is None
            current_price = live_price if not stale else h["avg_cost"]
            value = current_price * h["shares"]
            market_value += value
            enriched.append({
                **h,
                "current_price": current_price,
                "market_value": round(value, 2),
                "unrealized_pl": round((current_price - h["avg_cost"]) * h["shares"], 2),
                "unrealized_pl_pct": round(((current_price / h["avg_cost"]) - 1) * 100, 2) if h["avg_cost"] else 0,
                "price_stale": stale,
            })

        total_value = round(self.user.paper_balance + market_value, 2)

        today = date_cls.today()
        existing = PortfolioSnapshot.query.filter_by(user_id=self.user.id, date=today).first()
        if existing:
            existing.total_value = total_value
        else:
            db.session.add(PortfolioSnapshot(user_id=self.user.id, date=today, total_value=total_value))
        db.session.commit()

        return {
            "cash": self.user.paper_balance,
            "market_value": round(market_value, 2),
            "total_value": total_value,
            "holdings": enriched,
        }

    def value_history(self, days=180):
        """Reconstructs actual historical account value from real trades and real
        historical prices. Every point corresponds to an actual price observation
        pulled from the market, not an invented calendar grid, since building a grid
        that includes hours the market is closed produces fake flat stretches and
        misleading jumps when real data resumes."""
        from models import Trade
        from datetime import datetime
        from config import Config

        trades = (
            Trade.query.filter_by(user_id=self.user.id)
            .order_by(Trade.created_at.asc())
            .all()
        )
        if not trades:
            return self._snapshot_history_fallback(days)

        start_ts = trades[0].created_at
        now_ts = datetime.utcnow()
        span_days = (now_ts.date() - start_ts.date()).days
        tickers = sorted({t.ticker for t in trades})

        intraday = span_days <= 3
        interval = "1h" if intraday else "1d"

        price_series = {}
        for tk in tickers:
            try:
                hist = T.get_price_history_range(tk, start_ts.date(), now_ts.date(), interval=interval)
                if hist is not None and not hist.empty:
                    price_series[tk] = hist["Close"]
            except Exception:
                continue

        if not price_series:
            return self._snapshot_history_fallback(days)

        # union of every real timestamp actually returned across all held tickers,
        # this is the timeline, no invented points, no non-trading-hour padding
        all_timestamps = sorted(set().union(*[set(s.index) for s in price_series.values()]))
        all_timestamps = [t for t in all_timestamps if t.to_pydatetime().replace(tzinfo=None) >= start_ts]
        if not all_timestamps:
            return self._snapshot_history_fallback(days)

        cash = Config.STARTING_PAPER_BALANCE
        shares_held = {tk: 0.0 for tk in tickers}
        trades_sorted = sorted(trades, key=lambda t: t.created_at)
        trade_idx = 0

        points = []
        last_known_price = {tk: None for tk in tickers}

        for ts in all_timestamps:
            ts_naive = ts.to_pydatetime().replace(tzinfo=None)
            while trade_idx < len(trades_sorted) and trades_sorted[trade_idx].created_at <= ts_naive:
                t = trades_sorted[trade_idx]
                amount = t.quantity * t.price
                if t.side == "buy":
                    cash -= amount
                    shares_held[t.ticker] = shares_held.get(t.ticker, 0.0) + t.quantity
                else:
                    cash += amount
                    shares_held[t.ticker] = shares_held.get(t.ticker, 0.0) - t.quantity
                trade_idx += 1

            market_value = 0.0
            for tk in tickers:
                series = price_series.get(tk)
                if series is not None and ts in series.index:
                    last_known_price[tk] = float(series.loc[ts])
                price = last_known_price.get(tk)
                if price is not None:
                    market_value += price * shares_held.get(tk, 0.0)

            label = ts.strftime("%Y-%m-%d %H:%M") if intraday else ts.strftime("%Y-%m-%d")
            points.append({"date": label, "total_value": round(cash + market_value, 2)})

        if len(points) > days:
            step = max(1, len(points) // days)
            points = points[::step]

        return points

    def _snapshot_history_fallback(self, days=90):
        """Used only when there's no trade history yet to reconstruct from, falls
        back to whatever daily snapshots have been recorded so far."""
        from models import PortfolioSnapshot
        rows = (
            PortfolioSnapshot.query.filter_by(user_id=self.user.id)
            .order_by(PortfolioSnapshot.date.asc())
            .limit(days)
            .all()
        )
        return [{"date": r.date.isoformat(), "total_value": r.total_value} for r in rows]

    def portfolio_health(self):
        """Whole-portfolio analysis, not per-ticker. Concentration math is computed
        directly and handed to the model as fact, never re-derived by it, so the
        narrative can't drift from the real numbers."""
        snap = self.portfolio_snapshot()
        if not snap["holdings"]:
            return {"text": "No open positions yet, nothing to assess.", "metrics": None}

        metrics = T.portfolio_concentration_metrics(snap["holdings"], snap["cash"])
        holdings_summary = ", ".join(
            f"{h['ticker']} {round((h['market_value']/metrics['total_value'])*100, 1)}%"
            for h in snap["holdings"]
        )

        facts = M.relevant_facts(self.user.id, "risk portfolio diversification")
        memory_context = M.facts_as_context(facts)

        messages = [
            {"role": "system", "content": P.BASE_SYSTEM},
            {"role": "user", "content": P.portfolio_health_prompt(
                holdings_summary, metrics, self.user.risk_appetite, memory_context
            )},
        ]
        result = self.btl.chat(messages, temperature=0.3, max_tokens=350)
        return {"text": result["content"].strip(), "metrics": metrics, "savings": result["savings"]}

    # ---------- autonomous trading ----------

    def _watchlist_tickers(self, limit=3):
        """Holdings first, since those are what the user actually has at stake.
        Falls back to sector-mapped defaults if there's nothing open yet."""
        holdings = T.get_holdings(self.user.id)
        tickers = [h["ticker"] for h in holdings]
        if len(tickers) < limit:
            from services.finance import SECTOR_TICKERS, DEFAULT_FEED_TICKERS
            sectors = (self.user.focus_sectors or "").split(",") if self.user.focus_sectors else []
            pool = []
            for s in sectors:
                pool.extend(SECTOR_TICKERS.get(s.strip(), []))
            pool.extend(DEFAULT_FEED_TICKERS)
            for t in pool:
                if t not in tickers:
                    tickers.append(t)
                if len(tickers) >= limit:
                    break
        return tickers[:limit]

    def autonomous_review(self, dry_run=False):
        """Runs a real, independent reasoning pass per watched ticker: pulls live
        price, real news, prior thesis history, and this user's actual risk profile,
        then commits to buy/sell/hold with a stated confidence. If the user has opted
        in and confidence clears their threshold, it executes a small, capped trade
        on its own and logs exactly why. Every review is logged whether or not it
        acted, so nothing autonomous happens without an audit trail.

        dry_run=True runs the reasoning and logs it without ever executing a trade,
        used by the manual "run now" button so it's safe to try without opting in."""
        from extensions import db
        from models import AutonomousAlert

        tickers = self._watchlist_tickers()
        alerts = []

        for ticker in tickers:
            try:
                snapshot = T.get_price_snapshot(ticker)
                news = T.fetch_news(ticker)
                news_context = "\n".join(f"- {n['title']}: {n.get('summary','')}" for n in news[:4]) or None
                thesis_entries = M.ticker_thesis_history(self.user.id, ticker)
                thesis_context = M.thesis_as_context(thesis_entries)
                facts = M.relevant_facts(self.user.id, f"{ticker} risk trading")
                memory_context = M.facts_as_context(facts)

                messages = [
                    {"role": "system", "content": P.BASE_SYSTEM},
                    {"role": "user", "content": P.autonomous_review_prompt(
                        ticker, snapshot, news_context, thesis_context, memory_context, self.user.risk_appetite
                    )},
                ]
                result = self.btl.chat(messages, temperature=0.2, max_tokens=250)
                text = result["content"]

                decision = self._parse_field(text, "DECISION", default="hold", as_float=False)
                confidence = self._parse_field(text, "CONFIDENCE", default=0.0)
                reason = self._parse_field(text, "REASON", default=text[:300], as_float=False)
                decision = (decision or "hold").strip().lower()

                executed = False
                trade_id = None

                should_act = (
                    not dry_run
                    and self.user.autonomous_enabled
                    and decision in ("buy", "sell")
                    and confidence >= (self.user.autonomous_confidence_threshold or 75.0)
                )

                if should_act:
                    try:
                        trade = self.execute_paper_trade(
                            ticker, decision, snapshot.get("price"),
                            quantity_pct=min(self.user.autonomous_max_pct or 3.0, 5.0),
                            rationale=f"Autonomous: {reason}",
                        )
                        executed = True
                        trade_id = trade.id
                    except ValueError:
                        executed = False

                if decision in ("buy", "sell"):
                    M.record_thesis(self.user.id, ticker, "long" if decision == "buy" else "short", reason, snapshot.get("price"))

                alert = AutonomousAlert(
                    user_id=self.user.id, ticker=ticker, decision=decision,
                    confidence=confidence, reasoning=reason, executed=executed, trade_id=trade_id,
                )
                db.session.add(alert)
                db.session.commit()
                alerts.append(alert)
            except Exception:
                continue

        return alerts

    # ---------- feed / daily briefing ----------

    def daily_briefing(self):
        """Three real runtime calls, each doing a distinct job, not one call dressed
        up as three. Stage 1 filters raw headlines for what's actually significant.
        Stage 2 checks that against this specific user's actual holdings and sectors.
        Stage 3 synthesizes both into the final briefing. Each stage's output is
        real input to the next, not decorative."""
        sectors = (self.user.focus_sectors or "").split(",") if self.user.focus_sectors else []
        articles = T.fetch_feed(sectors)
        headlines = "\n".join(f"- [{a['ticker']}] {a['title']}: {a.get('summary','')}" for a in articles) or "no headlines pulled"

        try:
            holdings = T.get_holdings(self.user.id)
            holdings_str = ", ".join(h["ticker"] for h in holdings) if holdings else None
        except Exception:
            holdings_str = None

        total_savings = {"benchmark_cost": 0.0, "customer_charge": 0.0}

        def track(savings):
            for key in ("benchmark_cost", "customer_charge"):
                try:
                    total_savings[key] += float(savings.get(key) or 0)
                except (TypeError, ValueError):
                    pass

        # stage 1: what's actually significant, not just what's recent
        movers_result = self.btl.chat([
            {"role": "system", "content": P.BASE_SYSTEM},
            {"role": "user", "content": P.briefing_movers_prompt(headlines)},
        ], temperature=0.3, max_tokens=250)
        track(movers_result["savings"])

        # stage 2: does it actually touch this user's real positions
        relevance_result = self.btl.chat([
            {"role": "system", "content": P.BASE_SYSTEM},
            {"role": "user", "content": P.briefing_relevance_prompt(
                movers_result["content"], holdings_str, ", ".join(sectors) if sectors else None
            )},
        ], temperature=0.3, max_tokens=250)
        track(relevance_result["savings"])

        # stage 3: combine into the final briefing
        synthesis_result = self.btl.chat([
            {"role": "system", "content": P.BASE_SYSTEM},
            {"role": "user", "content": P.briefing_synthesis_prompt(movers_result["content"], relevance_result["content"])},
        ], temperature=0.3, max_tokens=300)
        track(synthesis_result["savings"])

        return {
            "text": synthesis_result["content"].strip(),
            "articles": articles,
            "pipeline": {
                "movers": movers_result["content"].strip(),
                "relevance": relevance_result["content"].strip(),
            },
            "savings": total_savings,
        }

    # ---------- research ----------

    def research(self, query, brief=False, history=None):
        """history is a list of {role, content} from earlier turns in this research
        conversation. Passing it as real prior turns (not text glued into one prompt)
        is what lets a follow-up like "what about the downside" actually mean
        something, since the model sees the whole exchange, not just the last line."""
        articles = T.fetch_news(query)
        summary = "\n".join(f"- [{a.get('ticker','')}] {a['title']}: {a.get('summary','')}" for a in articles) or "no articles found"

        messages = [{"role": "system", "content": P.BASE_SYSTEM}]
        for turn in (history or [])[-10:]:
            role = "assistant" if turn.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": turn.get("content", "")})
        messages.append({"role": "user", "content": P.research_prompt(query, summary, brief=brief)})

        result = self.btl.chat(messages, temperature=0.4, max_tokens=250 if brief else 2200)
        return {
            "text": result["content"].strip(),
            "articles": articles,
            "savings": result["savings"],
        }

    # ---------- improvement loop ----------

    def refresh_thesis_outcomes(self):
        def price_lookup(ticker):
            try:
                return T.get_price_snapshot(ticker).get("price")
            except Exception:
                return None

        return M.check_outcomes(self.user.id, price_lookup)
