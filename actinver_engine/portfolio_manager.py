"""
actinver_engine/portfolio_manager.py
Gestor Patrimonial de Cartera Actinver (Bursanet).
Calcula la valuación total en MXN, plusvalías, asignación Core vs Satélite,
y lleva el control contable del Interés Compuesto mediante reinversión de dividendos y ganancias.
"""

from decimal import Decimal
import json
import logging
import os
import time
from typing import Dict, Any, List, Optional
from actinver_engine.config import (
    INITIAL_PORTFOLIO_SNAPSHOT,
    TICKER_MAP,
    CORE_TARGET_WEIGHT,
    SATELLITE_TARGET_WEIGHT,
    MAX_EMERGING_MARKET_WEIGHT,
    MIN_FIBRA_WEIGHT,
)

logger = logging.getLogger(__name__)


class ActinverPortfolioManager:
    """Manages holdings, valuations, journal of trade proofs, and dividend compounding in Actinver."""

    def __init__(self, storage_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.storage_dir = storage_dir or os.path.join(base_dir, "user_verifications")
        os.makedirs(self.storage_dir, exist_ok=True)

        self.portfolio_file = os.path.join(self.storage_dir, "actinver_portfolio.json")
        self.journal_file = os.path.join(self.storage_dir, "actinver_trade_journal.json")
        self.dividends_file = os.path.join(self.storage_dir, "actinver_dividends.json")

        self.portfolio_data = self._load_or_initialize_portfolio()

    def _load_or_initialize_portfolio(self) -> Dict[str, Any]:
        """Loads persistent portfolio JSON or initializes from initial verified snapshot."""
        if os.path.exists(self.portfolio_file):
            try:
                with open(self.portfolio_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error cargando portafolio guardado: {e}")

        # Initialize from snapshot
        snap = {
            "cash_mxn": float(INITIAL_PORTFOLIO_SNAPSHOT.get("cash_mxn", 2.50)),
            "divisas_mxn": float(INITIAL_PORTFOLIO_SNAPSHOT.get("divisas_mxn", 632.20)),
            "stocks_etfs": {
                k: {
                    "titles": v["titles"],
                    "entry_price": float(v["entry_price"]),
                    "current_price": float(v["current_price"]),
                    "pocket": v["pocket"]
                }
                for k, v in INITIAL_PORTFOLIO_SNAPSHOT["stocks_etfs"].items()
            },
            "debt_funds": {
                k: {
                    "titles": v["titles"],
                    "value_mxn": float(v["value_mxn"]),
                    "pocket": v["pocket"]
                }
                for k, v in INITIAL_PORTFOLIO_SNAPSHOT["debt_funds"].items()
            },
            "equity_funds": {
                k: {
                    "titles": v["titles"],
                    "value_mxn": float(v["value_mxn"]),
                    "pocket": v["pocket"]
                }
                for k, v in INITIAL_PORTFOLIO_SNAPSHOT["equity_funds"].items()
            },
            "total_realized_profit_mxn": 0.0,
            "total_dividends_collected_mxn": 0.0,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        }
        self._save_portfolio(snap)
        return snap

    def _save_portfolio(self, data: Optional[Dict[str, Any]] = None) -> None:
        """Saves portfolio state to disk."""
        target = data if data is not None else self.portfolio_data
        target["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        with open(self.portfolio_file, "w", encoding="utf-8") as f:
            json.dump(target, f, indent=2, ensure_ascii=False)

    def calculate_valuation(self, live_quotes: Optional[Dict[str, Decimal]] = None) -> Dict[str, Any]:
        """Calculates total portfolio value in MXN and pockets distribution."""
        quotes = live_quotes or {}
        stocks = self.portfolio_data.get("stocks_etfs", {})
        debt_funds = self.portfolio_data.get("debt_funds", {})
        equity_funds = self.portfolio_data.get("equity_funds", {})
        cash = float(self.portfolio_data.get("cash_mxn", 2.50))
        divisas = float(self.portfolio_data.get("divisas_mxn", 632.20))

        stocks_val = 0.0
        core_val = 0.0
        satellite_val = 0.0
        stock_breakdown = {}

        for name, item in stocks.items():
            titles = item["titles"]
            price = float(quotes.get(name, item["current_price"]))
            val = titles * price
            cost = titles * float(item["entry_price"])
            gain = val - cost
            pct_gain = (gain / cost * 100.0) if cost > 0 else 0.0
            stocks_val += val

            pocket = item.get("pocket", "SATELLITE")
            if pocket == "CORE":
                core_val += val
            else:
                satellite_val += val

            stock_breakdown[name] = {
                "titles": titles,
                "price": price,
                "value_mxn": val,
                "gain_mxn": gain,
                "pct_gain": pct_gain,
                "pocket": pocket
            }

        debt_val = sum(float(f["value_mxn"]) for f in debt_funds.values())
        eq_funds_val = sum(float(f["value_mxn"]) for f in equity_funds.values())
        core_val += eq_funds_val

        defensive_val = debt_val + divisas + cash
        total_portfolio_mxn = stocks_val + debt_val + eq_funds_val + cash + divisas

        core_pct = (core_val / total_portfolio_mxn * 100.0) if total_portfolio_mxn > 0 else 0.0
        satellite_pct = (satellite_val / total_portfolio_mxn * 100.0) if total_portfolio_mxn > 0 else 0.0
        defensive_pct = (defensive_val / total_portfolio_mxn * 100.0) if total_portfolio_mxn > 0 else 0.0

        return {
            "total_valuation_mxn": round(total_portfolio_mxn, 2),
            "cash_mxn": round(cash, 2),
            "divisas_mxn": round(divisas, 2),
            "stocks_etfs_val": round(stocks_val, 2),
            "debt_funds_val": round(debt_val, 2),
            "equity_funds_val": round(eq_funds_val, 2),
            "core_val": round(core_val, 2),
            "core_pct": round(core_pct, 1),
            "satellite_val": round(satellite_val, 2),
            "satellite_pct": round(satellite_pct, 1),
            "defensive_val": round(defensive_val, 2),
            "defensive_pct": round(defensive_pct, 1),
            "stock_breakdown": stock_breakdown,
            "total_dividends_collected_mxn": self.portfolio_data.get("total_dividends_collected_mxn", 0.0),
            "total_realized_profit_mxn": self.portfolio_data.get("total_realized_profit_mxn", 0.0),
        }

    def register_trade_execution(
        self,
        action: str,  # BUY or SELL
        symbol: str,
        titles: int,
        price_mxn: Decimal,
        pocket: str = "SATELLITE",
        proof_filename: Optional[str] = None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """Updates portfolio state after user executes and verifies a trade in Actinver (with strict idempotency)."""
        price_f = float(price_mxn)
        amount_mxn = titles * price_f
        action_u = action.upper()

        # Strict idempotency check: prevent duplicate trade executions
        processed_proofs = self.portfolio_data.setdefault("processed_proofs", [])
        trade_key = f"{action_u}:{symbol}:{titles}:{price_f}:{proof_filename or notes}"
        if proof_filename and proof_filename in processed_proofs:
            logger.info(f"Comprobante '{proof_filename}' ya procesado previamente. Cero duplicidad.")
            return {"status": "DUPLICADO_IGNORADO", "message": "Operación ya procesada previamente.", "symbol": symbol, "titles": titles}
        if trade_key in processed_proofs:
            logger.info(f"Operación '{trade_key}' ya registrada previamente. Cero duplicidad.")
            return {"status": "DUPLICADO_IGNORADO", "message": "Operación ya procesada previamente.", "symbol": symbol, "titles": titles}

        stocks = self.portfolio_data.setdefault("stocks_etfs", {})
        realized_profit = 0.0
        if action_u == "SELL":
            if symbol in stocks:
                current_titles = stocks[symbol]["titles"]
                entry_p = float(stocks[symbol]["entry_price"])
                sold_titles = min(titles, current_titles)
                realized_profit = (price_f - entry_p) * sold_titles
                stocks[symbol]["titles"] -= sold_titles
                if stocks[symbol]["titles"] <= 0:
                    del stocks[symbol]
                self.portfolio_data["cash_mxn"] += amount_mxn
                self.portfolio_data["total_realized_profit_mxn"] += realized_profit
        elif action_u == "BUY":
            if symbol in stocks:
                existing_titles = stocks[symbol]["titles"]
                existing_cost = existing_titles * float(stocks[symbol]["entry_price"])
                new_titles = existing_titles + titles
                new_avg_cost = (existing_cost + amount_mxn) / new_titles
                stocks[symbol]["titles"] = new_titles
                stocks[symbol]["entry_price"] = new_avg_cost
                stocks[symbol]["current_price"] = price_f
            else:
                stocks[symbol] = {
                    "titles": titles,
                    "entry_price": price_f,
                    "current_price": price_f,
                    "pocket": pocket
                }
            self.portfolio_data["cash_mxn"] = max(0.0, self.portfolio_data["cash_mxn"] - amount_mxn)

        # Mark as processed for deduplication
        if proof_filename:
            processed_proofs.append(proof_filename)
        processed_proofs.append(trade_key)

        # Log to trade journal
        record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "action": action_u,
            "symbol": symbol,
            "titles": titles,
            "price_mxn": price_f,
            "total_mxn": amount_mxn,
            "realized_profit_mxn": realized_profit,
            "proof_filename": proof_filename,
            "notes": notes,
            "status": "EJECUTADO_Y_AUDITADO"
        }
        self._append_to_journal(record)
        self._save_portfolio()
        return record

    def set_verified_holdings(
        self,
        stocks_etfs: Dict[str, Any],
        debt_funds: Dict[str, Any],
        cash_mxn: float = 0.0,
        proof_filename: Optional[str] = None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """Sets the exact verified holdings (idempotent snapshot reconciliation). Never duplicates titles or cash."""
        self.portfolio_data["stocks_etfs"] = stocks_etfs
        self.portfolio_data["debt_funds"] = debt_funds
        self.portfolio_data["cash_mxn"] = round(float(cash_mxn), 2)
        self.portfolio_data["last_reconciliation"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        if proof_filename:
            self.portfolio_data.setdefault("processed_proofs", []).append(proof_filename)
        self._save_portfolio()
        logger.info(f"Portafolio conciliado formalmente con snapshot verificado ({notes}).")
        return self.calculate_valuation()

    def register_dividend(self, symbol: str, gross_amount_mxn: Decimal, notes: str = "") -> Dict[str, Any]:
        """Records dividend/rent received (DRIP Compounding engine)."""
        amt = float(gross_amount_mxn)
        self.portfolio_data["cash_mxn"] += amt
        self.portfolio_data["total_dividends_collected_mxn"] += amt

        div_record = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "symbol": symbol,
            "amount_mxn": amt,
            "notes": notes,
        }
        entries = self._load_json(self.dividends_file)
        entries.append(div_record)
        with open(self.dividends_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        self._save_portfolio()
        return div_record

    def _append_to_journal(self, record: Dict[str, Any]) -> None:
        entries = self._load_json(self.journal_file)
        entries.append(record)
        with open(self.journal_file, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    def _load_json(self, path: str) -> List[Dict[str, Any]]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []
