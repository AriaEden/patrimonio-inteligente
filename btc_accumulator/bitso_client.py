"""
btc_accumulator/bitso_client.py
Public Bitso Alpha API client, book specifications parser, and order constraint validator.
Operates exclusively over public endpoints with zero authentication required.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
import json
import logging
from typing import Dict, Any, Tuple, Optional
import urllib.request
import urllib.error

from btc_accumulator.config import (
    DEFAULT_BOOK,
    COMPARISON_BOOK,
    DEFAULT_MAKER_FEE_RATE,
    DEFAULT_TAKER_FEE_RATE,
    MXN_MAKER_FEE_RATE,
    MXN_TAKER_FEE_RATE,
    BTC_USD_MIN_AMOUNT,
    BTC_USD_MIN_VALUE,
    BTC_USD_TICK_SIZE,
    BTC_MXN_MIN_AMOUNT,
    BTC_MXN_MIN_VALUE,
    BTC_MXN_TICK_SIZE,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BookSpecification:
    """Represents public trading rules and constraints for a Bitso trading pair."""
    book: str
    minimum_amount: Decimal
    maximum_amount: Decimal
    minimum_value: Decimal
    maximum_value: Decimal
    minimum_price: Decimal
    maximum_price: Decimal
    tick_size: Decimal
    maker_fee: Decimal
    taker_fee: Decimal


@dataclass(frozen=True)
class TickerSummary:
    """Public ticker snapshot."""
    book: str
    bid: Decimal
    ask: Decimal
    last: Decimal
    volume: Decimal
    vwap: Decimal
    spread_absolute: Decimal
    spread_bps: Decimal


class BitsoPublicClient:
    """
    Public HTTP client for Bitso Alpha API v3.
    Strictly read-only; no private keys or trade dispatch endpoints exist in this client.
    """
    BASE_URL = "https://api.bitso.com/v3"
    USER_AGENT = "BTC-Accumulator-V1/PublicAudit (Institutional Research)"

    def __init__(self, timeout_sec: int = 15):
        self.timeout_sec = timeout_sec

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Performs a safe GET request to Bitso public API."""
        url = f"{self.BASE_URL}{path}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"

        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if not data.get("success", False):
                    raise RuntimeError(f"Bitso API error response: {data.get('error')}")
                return data["payload"]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            logger.error(f"HTTP Error {e.code} querying Bitso {url}: {error_body}")
            raise ConnectionError(f"Bitso API returned {e.code}: {error_body}")
        except Exception as e:
            logger.error(f"Network error querying Bitso {url}: {e}")
            raise ConnectionError(f"Failed to communicate with Bitso: {e}")

    def get_available_books(self) -> Dict[str, BookSpecification]:
        """Fetches and parses all available trading books and their exact constraints."""
        payload = self._get("/available_books/")
        books: Dict[str, BookSpecification] = {}

        for item in payload:
            book_name = item["book"]
            fees = item.get("fees", {}).get("flat_rate", {})
            maker_fee = Decimal(str(fees.get("maker", "0.0030")))
            taker_fee = Decimal(str(fees.get("taker", "0.0036")))

            books[book_name] = BookSpecification(
                book=book_name,
                minimum_amount=Decimal(str(item["minimum_amount"])),
                maximum_amount=Decimal(str(item["maximum_amount"])),
                minimum_value=Decimal(str(item["minimum_value"])),
                maximum_value=Decimal(str(item["maximum_value"])),
                minimum_price=Decimal(str(item["minimum_price"])),
                maximum_price=Decimal(str(item["maximum_price"])),
                tick_size=Decimal(str(item["tick_size"])),
                maker_fee=maker_fee,
                taker_fee=taker_fee,
            )
        return books

    def get_book_spec(self, book: str = DEFAULT_BOOK) -> BookSpecification:
        """Retrieves verified specifications for a specific book, with static institutional fallback."""
        try:
            all_books = self.get_available_books()
            if book in all_books:
                return all_books[book]
        except Exception as e:
            logger.warning(f"Could not fetch live book specs ({e}). Using verified institutional parameters.")

        # Static institutional fallback derived from verified Bitso endpoints
        if book == DEFAULT_BOOK:
            return BookSpecification(
                book=DEFAULT_BOOK,
                minimum_amount=BTC_USD_MIN_AMOUNT,
                maximum_amount=Decimal("600.0"),
                minimum_value=BTC_USD_MIN_VALUE,
                maximum_value=Decimal("10000000.0"),
                minimum_price=Decimal("5000.0"),
                maximum_price=Decimal("2000000.0"),
                tick_size=BTC_USD_TICK_SIZE,
                maker_fee=DEFAULT_MAKER_FEE_RATE,
                taker_fee=DEFAULT_TAKER_FEE_RATE,
            )
        elif book == COMPARISON_BOOK:
            return BookSpecification(
                book=COMPARISON_BOOK,
                minimum_amount=BTC_MXN_MIN_AMOUNT,
                maximum_amount=Decimal("600.0"),
                minimum_value=BTC_MXN_MIN_VALUE,
                maximum_value=Decimal("200000000.0"),
                minimum_price=Decimal("100000.0"),
                maximum_price=Decimal("40000000.0"),
                tick_size=BTC_MXN_TICK_SIZE,
                maker_fee=MXN_MAKER_FEE_RATE,
                taker_fee=MXN_TAKER_FEE_RATE,
            )
        else:
            raise ValueError(f"Unknown book specification for '{book}'")

    def get_ticker(self, book: str = DEFAULT_BOOK) -> TickerSummary:
        """Retrieves the live public ticker, calculating spreads and relative basis."""
        payload = self._get("/ticker/", params={"book": book})
        bid = Decimal(str(payload["bid"]))
        ask = Decimal(str(payload["ask"]))
        last = Decimal(str(payload["last"]))
        volume = Decimal(str(payload["volume"]))
        vwap = Decimal(str(payload["vwap"]))

        spread_abs = ask - bid
        spread_bps = (spread_abs / ask) * Decimal("10000") if ask > 0 else Decimal("0")

        return TickerSummary(
            book=book,
            bid=bid,
            ask=ask,
            last=last,
            volume=volume,
            vwap=vwap,
            spread_absolute=spread_abs,
            spread_bps=spread_bps,
        )

    def get_order_book(self, book: str = DEFAULT_BOOK) -> Dict[str, Any]:
        """Retrieves the live public order book with top bids and asks."""
        payload = self._get("/order_book/", params={"book": book})
        return {
            "bids": [(Decimal(b["price"]), Decimal(b["amount"])) for b in payload.get("bids", [])],
            "asks": [(Decimal(a["price"]), Decimal(a["amount"])) for a in payload.get("asks", [])],
            "sequence": payload.get("sequence"),
            "updated_at": payload.get("updated_at"),
        }

    @staticmethod
    def validate_order_constraints(
        btc_amount: Decimal,
        quote_value: Decimal,
        book_spec: BookSpecification
    ) -> Tuple[bool, str]:
        """
        Automatically validates minimum_amount, minimum_value, and maximum limits
        for both the SELL and BUYBACK operations according to exchange rules.
        """
        # 1. Amount validation
        if btc_amount < book_spec.minimum_amount:
            return (
                False,
                f"Amount {btc_amount} BTC is below minimum_amount {book_spec.minimum_amount} BTC"
            )
        if btc_amount > book_spec.maximum_amount:
            return (
                False,
                f"Amount {btc_amount} BTC exceeds maximum_amount {book_spec.maximum_amount} BTC"
            )

        # 2. Value validation
        if quote_value < book_spec.minimum_value:
            return (
                False,
                f"Value {quote_value} is below minimum_value {book_spec.minimum_value} in {book_spec.book}"
            )
        if quote_value > book_spec.maximum_value:
            return (
                False,
                f"Value {quote_value} exceeds maximum_value {book_spec.maximum_value} in {book_spec.book}"
            )

        return (True, "Order constraints valid.")

    @staticmethod
    def quantize_price(price: Decimal, tick_size: Decimal) -> Decimal:
        """Quantizes price to the exchange's minimum tick size."""
        steps = (price / tick_size).quantize(Decimal("1"), rounding=ROUND_DOWN)
        return steps * tick_size

    @staticmethod
    def quantize_btc(amount: Decimal) -> Decimal:
        """Quantizes BTC amount to 8 decimal places (satoshi precision)."""
        return amount.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
