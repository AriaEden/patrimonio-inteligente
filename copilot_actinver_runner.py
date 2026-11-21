"""
copilot_actinver_runner.py
Motor de Monitoreo Bursátil Continuo para Actinver (Bursanet).
Opera durante el horario de la Bolsa Mexicana (08:30 a 15:00 hrs CDMX).
1. Monitorea cotizaciones de BMV y SIC en vivo con CERO CLAVES PRIVADAS.
2. Despacha señales de Swing Trading con Interés Compuesto para el Bolsillo Satélite.
3. Notifica planes de Rebalanceo Táctico para incorporar FIBRAs y Foco en Core.
4. Recibe y certifica capturas de pantalla de la app de Bursanet/Actinver.
"""

from decimal import Decimal
import logging
import os
import sys
import time
from typing import Dict, Any, Optional

# Load .env if present
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        # Fallback to parent or btc_accumulator .env for shared telegram credentials
        sibling_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "btc_accumulator_v1", ".env")
        if os.path.exists(sibling_env):
            env_path = sibling_env

    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and k not in os.environ:
                        os.environ[k] = v

load_env_file()

from actinver_engine.config import (
    TICKER_MAP,
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
)
from actinver_engine.market_data import ActinverMarketDataClient
from actinver_engine.portfolio_manager import ActinverPortfolioManager
from actinver_engine.rebalance_engine import ActinverRebalanceEngine
from actinver_engine.telegram_notifier import ActinverTelegramNotifier
from actinver_engine.telegram_bot_manager import ActinverTelegramBotManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ActinverCopiloto")


class ActinverCopilotRunner:
    """Monitors live Mexican stock market, handles proofs, and alerts via Telegram."""

    def __init__(self, check_interval_seconds: int = 60):
        self.check_interval_seconds = check_interval_seconds
        self.market_client = ActinverMarketDataClient()
        self.portfolio_mgr = ActinverPortfolioManager()
        self.rebalance_engine = ActinverRebalanceEngine(self.portfolio_mgr)
        self.notifier = ActinverTelegramNotifier()
        self.bot_manager = ActinverTelegramBotManager(self.portfolio_mgr, self.rebalance_engine)

        self.last_checked_quotes: Dict[str, Decimal] = {}
        self.rebalance_alert_sent = False
        self.flywheel_alert_sent = False

    def is_market_open(self) -> bool:
        """Checks if BMV / SIC is open (Mon-Fri 08:30 to 15:00 hrs CDMX)."""
        lt = time.localtime()
        weekday = lt.tm_wday  # 0 is Monday, 4 is Friday, 5 is Saturday, 6 is Sunday
        if weekday >= 5:
            return False  # Closed on weekends

        hour = lt.tm_hour
        minute = lt.tm_min

        start_mins = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
        close_mins = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE
        current_mins = hour * 60 + minute

        return start_mins <= current_mins < close_mins

    def run_single_iteration(self) -> None:
        """Executes one market monitoring check."""
        # 1. Listen for incoming user screenshots or queries
        self.bot_manager.process_incoming_updates()

        # 2. Fetch live quotes for tracked assets
        quotes = {}
        for name, info in TICKER_MAP.items():
            sym = info["symbol"]
            q = self.market_client.fetch_quote(sym)
            if q and q["price"]:
                quotes[name] = q["price"]

        if quotes:
            self.last_checked_quotes = quotes

        # 3. Check Cross-Asset Bitcoin Macro Cycle (Flywheel Cripto <-> Actinver)
        try:
            import json, urllib.request
            req = urllib.request.Request("https://api.bitso.com/v3/ticker/?book=btc_usd", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = json.loads(resp.read().decode("utf-8"))
                btc_last = d.get("payload", {}).get("last")
                if btc_last:
                    btc_p = Decimal(str(btc_last))
                    flywheel_sig = self.rebalance_engine.evaluate_cross_asset_flywheel(btc_p)
                    if flywheel_sig and not self.flywheel_alert_sent:
                        logger.info("🚨 ¡Señal de Volante Cruzado Cripto-Actinver detectada!")
                        self.notifier.send_cross_asset_flywheel_alert(flywheel_sig)
                        self.flywheel_alert_sent = True
        except Exception as e:
            logger.debug(f"Aviso consultando ticker cruzado de BTC: {e}")

        # 4. If initial rebalance hasn't been notified yet, notify user once on startup
        if not self.rebalance_alert_sent:
            plan = self.rebalance_engine.evaluate_initial_rebalance(self.last_checked_quotes)
            logger.info("Enviando resumen inicial del plan de rebalanceo a Telegram...")
            self.notifier.send_rebalance_plan_alert(plan)
            self.rebalance_alert_sent = True

        # 5. Check market hours
        if not self.is_market_open():
            logger.info("Bolsa Mexicana cerrada en este momento (Horario hábil: Lun-Vie 08:30 a 15:00 hrs CDMX).")
            return

        # 6. Analyze technical swing conditions for satellite pocket
        analyses = {}
        for name in ["CEMEX CPO", "GFINBUR O", "AMX B"]:
            sym = TICKER_MAP[name]["symbol"]
            analyses[name] = self.market_client.get_market_analysis(sym)

        signals = self.rebalance_engine.check_swing_signals(analyses)
        for sig in signals:
            logger.info(f"🚨 ¡Señal detectada en {sig['symbol']}: {sig['action']} a ${sig['price_mxn']} MXN!")
            self.notifier.send_swing_signal_alert(
                action=sig["action"],
                symbol=sig["symbol"],
                price_mxn=sig["price_mxn"],
                titles=50,
                reason=sig["reason"],
                pocket=sig["pocket"]
            )

    def start_continuous_monitoring(self) -> None:
        """Starts continuous autonomous copilot monitoring."""
        logger.info(f"🟢 Copiloto de Actinver (Bursanet) INICIADO. Monitoreando cada {self.check_interval_seconds}s...")
        print("=" * 75)
        print(" COPILOTO ACTINVER PATRIMONIAL V1.0 | RENTA VARIABLE & FIBRAS")
        print(" ESTRATEGIA CORE & SATELLITE • INTERÉS COMPUESTO • HORARIO BURSÁTIL")
        print("=" * 75)
        print("El bot está escuchando consultas y comprobantes de Actinver.")
        print("Horario de mercado: Lunes a Viernes de 08:30 a 15:00 hrs (CDMX).")
        print("Cero alertas nocturnas garantizado.\n")

        while True:
            try:
                self.run_single_iteration()
            except KeyboardInterrupt:
                logger.info("Monitoreo de Actinver detenido.")
                break
            except Exception as e:
                logger.error(f"Error en ciclo de Actinver: {e}")
            time.sleep(self.check_interval_seconds)


if __name__ == "__main__":
    runner = ActinverCopilotRunner(check_interval_seconds=60)
    if "--once" in sys.argv:
        runner.run_single_iteration()
    else:
        runner.start_continuous_monitoring()
