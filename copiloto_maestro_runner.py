"""
copiloto_maestro_runner.py
=============================================================================
MOTOR AUTÓNOMO INTEGRAL (BITCOIN + ACTINVER)
=============================================================================
Este motor unificado corre de forma 100% permanente e independiente en tu PC:
1. Cero dependencia del asistente o sesiones de IA.
2. Monitoreo de Bitcoin 24/7 en Bitso Alpha (4H y detección de Cisne Negro).
3. Monitoreo bursátil de Actinver/Bursanet (BMV/SIC) en horario de mercado.
4. Escucha continua de mensajes, comandos y capturas de pantalla en Telegram.
5. Prueba de Vida Diaria (Morning Heartbeat) a las 09:00 AM CDMX.
6. Soporte multiusuario privado: cada amigo tiene su chat, lote y bitácora aislada.
7. CERO CLAVES PRIVADAS: Solo consulta APIs públicas y te avisa a ti.
"""

from decimal import Decimal
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
import threading
import time

# Auto-load environment variables from .env
def load_env_file():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(base_dir, ".env")
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

# Ensure parent and sibling directories are on sys.path
base_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(base_dir)
actinver_dir = os.path.join(parent_dir, "actinver_copilot_v1")
for p in [base_dir, actinver_dir]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from btc_accumulator.config import audit_security_environment
from copilot_telegram_runner import CopilotTelegramRunner

# Configure dual logging: console + rotating log file
log_file = os.path.join(base_dir, "copiloto_sistema.log")
file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
console_handler = logging.StreamHandler(sys.stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger("CopilotoMaestro")

PID_FILE = os.path.join(base_dir, "copiloto.pid")


def save_pid():
    """Writes process ID to disk for status and stop utilities."""
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"No se pudo guardar PID: {e}")


def remove_pid():
    """Removes PID file on clean shutdown."""
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass


START_TIME = time.time()


class CloudHealthHandler(BaseHTTPRequestHandler):
    """Responds to cloud health checks (Render) and receives Telegram Webhooks for instant wake-up."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        uptime = round(time.time() - START_TIME, 1)
        resp = {
            "status": "ONLINE",
            "copilot": "Copiloto Maestro Hibrido (Bitcoin + Actinver)",
            "uptime_seconds": uptime,
            "zero_private_keys": True,
            "cloud_status": "Vigilancia activa 24/7/365 sin necesidad de PC",
            "bot_user": "@dabel_btc_copiloto_bot"
        }
        self.wfile.write(json.dumps(resp, indent=2).encode("utf-8"))

    def do_POST(self):
        """Allows Telegram Webhooks or external pingers to deliver updates directly."""
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        try:
            update = json.loads(post_data.decode("utf-8"))
            bm = getattr(self.server, "bot_manager", None)
            if bm and hasattr(bm, "process_single_update"):
                bm.process_single_update(update)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        except Exception:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": false}')

    def log_message(self, format, *args):
        # Silence routine web health checks to keep logs clean
        return


def start_cloud_health_server(bot_manager=None):
    """Starts a lightweight HTTP server on the cloud assigned port (default 10000 or PORT)."""
    port_str = os.getenv("PORT", "10000")
    try:
        port = int(port_str)
    except ValueError:
        port = 10000

    def serve():
        try:
            server = HTTPServer(("0.0.0.0", port), CloudHealthHandler)
            server.bot_manager = bot_manager
            logger.info(f"🌐 Servidor web de salud en la nube activo en puerto {port}")
            server.serve_forever()
        except Exception as e:
            logger.warning(f"Aviso iniciando servidor web en puerto {port}: {e}")

    t = threading.Thread(target=serve, daemon=True)
    t.start()


def start_cloud_self_ping():
    """Keeps free cloud web services alive 24/7 by pinging itself every 5 minutes."""
    ping_url = (
        os.getenv("RENDER_EXTERNAL_URL")
        or os.getenv("SELF_PING_URL")
        or "https://copiloto-inversion-hibrido.onrender.com"
    )

    def pinger():
        logger.info(f"🔄 Auto-ping activo para mantener despierto Render 24/7 en: {ping_url}")
        import urllib.request
        # Initial wait for server boot
        time.sleep(30)
        while True:
            try:
                req = urllib.request.Request(ping_url, headers={"User-Agent": "CopilotoKeepAlive/2.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    logger.debug(f"Auto-ping HTTP {r.status} exitoso a {ping_url}")
            except Exception as e:
                logger.debug(f"Aviso en auto-ping: {e}")
            time.sleep(300)  # Pings every 5 minutes (well below Render's 15-minute idle limit)

    t = threading.Thread(target=pinger, daemon=True)
    t.start()


class CopilotoMaestro:
    """Master Orchestrator running Bitcoin Accumulator and Actinver Copilot."""

    def __init__(self, check_interval_seconds: int = 30):
        self.check_interval_seconds = check_interval_seconds
        audit_security_environment()

        # Initialize Bitcoin runner
        logger.info("Iniciando Copiloto de Bitcoin (Bitso Alpha)...")
        self.btc_runner = CopilotTelegramRunner(check_interval_seconds=check_interval_seconds)

        # Initialize Actinver runner if available
        self.actinver_runner = None
        try:
            from copilot_actinver_runner import ActinverCopilotRunner
            logger.info("Iniciando Copiloto de Actinver (Bursanet / BMV)...")
            self.actinver_runner = ActinverCopilotRunner(check_interval_seconds=60)
        except Exception as e:
            logger.warning(f"Actinver no iniciado como runner independiente: {e}")

        self.last_actinver_check = 0.0
        self.actinver_interval_seconds = 60

    def run_single_master_iteration(self) -> None:
        """Runs a coordinated cycle of both asset classes (used in tests and single runs)."""
        # 1. Bitcoin iteration (Telegram polling, Bitso ticker, 4H candle, daily heartbeat)
        self.btc_runner.run_single_iteration()

        # 2. Actinver iteration
        if self.actinver_runner:
            try:
                self._run_actinver_cycle()
            except Exception as e:
                logger.warning(f"Aviso en ciclo de Actinver: {e}")

    def _run_actinver_cycle(self) -> None:
        """Executes stock and rebalance analysis without duplicate Telegram polling."""
        if not self.actinver_runner:
            return

        # 1. Fetch live quotes
        from actinver_engine.config import TICKER_MAP
        quotes = {}
        for name, info in TICKER_MAP.items():
            sym = info["symbol"]
            q = self.actinver_runner.market_client.fetch_quote(sym)
            if q and q["price"]:
                quotes[name] = q["price"]

        if quotes:
            self.actinver_runner.last_checked_quotes = quotes

        # 2. Check cross-asset flywheel with live Bitso price
        ticker = self.btc_runner.bot_manager.fetch_live_bitso_ticker("btc_usd")
        if ticker and ticker.get("last"):
            btc_p = Decimal(str(ticker["last"]))
            flywheel_sig = self.actinver_runner.rebalance_engine.evaluate_cross_asset_flywheel(btc_p)
            if flywheel_sig and not self.actinver_runner.flywheel_alert_sent:
                logger.info("🚨 ¡Señal de Volante Cruzado Cripto-Actinver detectada!")
                self.actinver_runner.notifier.send_cross_asset_flywheel_alert(flywheel_sig)
                self.actinver_runner.flywheel_alert_sent = True

        # 3. Check stock market open hours for swing trading
        if self.actinver_runner.is_market_open():
            analyses = {}
            for name in ["CEMEX CPO", "GFINBUR O", "AMX B"]:
                sym = TICKER_MAP[name]["symbol"]
                analyses[name] = self.actinver_runner.market_client.get_market_analysis(sym)
            signals = self.actinver_runner.rebalance_engine.check_swing_signals(analyses)
            for s in signals:
                logger.info(f"⚡ Señal de Swing Bursátil detectada: {s['action']} {s['symbol']}")
                self.actinver_runner.notifier.send_swing_trade_alert(s)

    def start(self) -> None:
        """Starts the infinite autonomous monitoring loop with sub-second Telegram latency and crash immunity."""
        save_pid()
        start_cloud_health_server(self.btc_runner.bot_manager)
        start_cloud_self_ping()
        logger.info("=================================================================")
        logger.info(f"🟢 COPILOTO MAESTRO INICIADO EN SEGUNDO PLANO (PID: {os.getpid()})")
        logger.info("• Modo Autónomo: ACTIVO (24/7 permanente con auto-recuperación)")
        logger.info("• Latencia Ultrarrápida: Telegram responde en < 1.5 segundos")
        logger.info("• Bitcoin (Bitso Alpha): Monitoreo continuo 24/7 activo")
        logger.info("• Actinver (Bursanet): Monitoreo bursátil activo (Lun-Vie 08:30-15:00)")
        logger.info("• Prueba de Vida Diaria: Programada a las 09:00 AM (CDMX)")
        logger.info("• Comandos Telegram: /estado, /precio, /portafolio, /rebalanceo, /modo, etc.")
        logger.info("=================================================================")

        telegram_poll_interval = 1.5   # Poll Telegram every 1.5 seconds for instant replies
        market_poll_interval = 30.0    # Evaluate Bitso market candles every 30 seconds

        # Run initial checks safely
        try:
            self.btc_runner.run_market_iteration()
        except Exception as e_init_btc:
            logger.warning(f"Aviso en verificación inicial BTC: {e_init_btc}")

        if self.actinver_runner:
            try:
                self._run_actinver_cycle()
            except Exception as e_init_act:
                logger.warning(f"Aviso en verificación inicial Actinver: {e_init_act}")

        last_market_run = time.time()

        while True:
            try:
                # 1. High-speed Telegram poll (isolated from exceptions)
                try:
                    self.btc_runner.check_user_screenshots_and_messages()
                    self.btc_runner.process_emergency_repeats()
                except Exception as e_poll:
                    logger.error(f"Error recuperable en sondeo de Telegram: {e_poll}")

                # 2. Periodic market check (isolated from exceptions)
                now = time.time()
                if now - last_market_run >= market_poll_interval:
                    last_market_run = now
                    try:
                        self.btc_runner.run_market_iteration()
                    except Exception as e_mkt:
                        logger.error(f"Error recuperable en iteración de mercado BTC: {e_mkt}")

                    if self.actinver_runner:
                        try:
                            self._run_actinver_cycle()
                        except Exception as e_act_mkt:
                            logger.error(f"Error recuperable en iteración bursátil: {e_act_mkt}")

                time.sleep(telegram_poll_interval)

            except KeyboardInterrupt:
                logger.info("Copiloto Maestro detenido manualmente por el usuario.")
                break
            except Exception as e_super:
                logger.error(f"Recuperación automática en bucle maestro (reanudando en 2s): {e_super}", exc_info=True)
                time.sleep(2.0)

        remove_pid()


def setup_signals():
    """Handles graceful termination."""
    def handler(signum, frame):
        logger.info(f"Señal de terminación recibida ({signum}). Apagando limpiamente...")
        remove_pid()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
    except Exception:
        pass


if __name__ == "__main__":
    setup_signals()
    orchestrator = CopilotoMaestro(check_interval_seconds=30)
    if "--once" in sys.argv:
        logger.info("Ejecutando una sola iteración de prueba (--once)...")
        orchestrator.run_single_master_iteration()
        remove_pid()
        logger.info("Iteración de prueba completada exitosamente.")
    else:
        orchestrator.start()
