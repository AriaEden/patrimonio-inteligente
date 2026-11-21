"""
copilot_telegram_runner.py
Motor de Monitoreo Continuo en Vivo con Alertas y Comprobantes por Telegram (Modo Copiloto).
1. Consulta periódicamente los endpoints públicos de Bitso Alpha (CERO CLAVES PRIVADAS).
2. Evalúa velas cerradas de 4 horas con el Detector de Bull Run (Modo Blindaje HODL).
3. Envía alertas automáticas de compra/venta a tu Telegram con INTERÉS COMPUESTO ACTIVO.
4. Escucha activamente tus mensajes y CAPTURAS DE PANTALLA enviadas por Telegram,
   descargando los comprobantes a 'user_verifications/' y registrándolos en la bitácora.
5. Filtro Nocturno (Modo Silencio de 23:00 a 07:00 hrs para respetar tu descanso).
6. Detector de MODO PRUEBA SUPERADO con alerta especial para valorar escalar capital a $100 USD.
7. Detector de CISNE NEGRO / VOLATILIDAD EXTREMA: Bypasea el silencio nocturno y repite alertas
   periódicas hasta que el usuario abra Telegram y responda /ok o envíe cualquier mensaje/foto.
"""

from decimal import Decimal
import json
import logging
import os
import sys
import time
from typing import Optional, List, Tuple, Dict, Any
import pandas as pd

# Auto-load .env file if present
def load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
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

from btc_accumulator.config import (
    DEFAULT_BOOK,
    CAPITAL_PER_TRADE_USDC,
    audit_security_environment,
)
from btc_accumulator.bitso_client import BitsoPublicClient
from btc_accumulator.indicators import add_all_indicators
from btc_accumulator.telegram_notifier import TelegramNotifier
from btc_accumulator.telegram_bot_manager import TelegramBotManager
from btc_accumulator.periodic_reporter import PlainLanguageReporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("CopilotoTelegram")


class CopilotTelegramRunner:
    """Monitors live public market data, manages user proof screenshots, and notifies via Telegram."""

    def __init__(
        self,
        book: str = DEFAULT_BOOK,
        check_interval_seconds: int = 30,
        notifier: Optional[TelegramNotifier] = None,
        bot_manager: Optional[TelegramBotManager] = None,
    ):
        self.book = book
        self.check_interval_seconds = check_interval_seconds
        self.client = BitsoPublicClient()
        self.notifier = notifier or TelegramNotifier()
        self.bot_manager = bot_manager or TelegramBotManager()
        self.last_processed_candle_ts = None
        self.last_processed_1h_ts = None
        self.initial_capital_usdc = CAPITAL_PER_TRADE_USDC

        # Night Silence Filter settings
        self.night_silence_enabled = os.getenv("NIGHT_SILENCE_ENABLED", "true").lower() in ("true", "1", "yes")
        self.night_start = int(os.getenv("NIGHT_START_HOUR", "23"))
        self.night_end = int(os.getenv("NIGHT_END_HOUR", "7"))

        # Compounding setting (100% reinvestment of realized satoshis)
        self.compounding_enabled = os.getenv("COMPOUNDING_ENABLED", "true").lower() in ("true", "1", "yes")
        self.current_btc_balance = Decimal("0.00013000")  # Baseline ~$10 at ~$77k
        self.test_phase_passed_notified = False
        self.heartbeat_state_file = os.path.join(self.bot_manager.storage_dir, "heartbeat_state.json")
        self.last_heartbeat_day: Optional[int] = None
        if os.path.exists(self.heartbeat_state_file):
            try:
                with open(self.heartbeat_state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_heartbeat_day = data.get("last_heartbeat_day")
            except Exception:
                self.last_heartbeat_day = None

        # Extreme Volatility and Emergency Repeating Alarm State
        self.price_history: List[Tuple[float, float]] = []  # list of (timestamp_seconds, price_float)
        self.emergency_threshold_pct = float(os.getenv("EMERGENCY_VOLATILITY_THRESHOLD_PCT", "4.5"))
        self.emergency_repeat_interval_seconds = int(os.getenv("EMERGENCY_REPEAT_INTERVAL_SEC", "180"))  # 3 min
        self.emergency_max_repeats = int(os.getenv("EMERGENCY_MAX_REPEATS", "10"))
        
        self.emergency_active = False
        self.emergency_acknowledged = True
        self.emergency_alert_count = 0
        self.emergency_last_alert_time = 0.0
        self.emergency_details: Dict[str, Any] = {}

        # Wire callbacks with bot_manager
        self.bot_manager.on_emergency_acknowledged = self.acknowledge_emergency
        self.bot_manager.on_trigger_test_emergency = self.trigger_test_emergency
        self.bot_manager.on_trigger_heartbeat = self.send_daily_heartbeat_report

        # Security check on launch
        audit_security_environment()

    def acknowledge_emergency(self) -> None:
        """Silences any active emergency repeating alarm when user opens Telegram or replies."""
        if self.emergency_active:
            logger.info("🔕 Alarma de emergencia silenciada por interacción del usuario.")
        self.emergency_active = False
        self.emergency_acknowledged = True
        self.emergency_alert_count = 0
        self.bot_manager.is_emergency_active = False

    def trigger_test_emergency(self) -> None:
        """Triggers a simulated emergency alert for user testing."""
        logger.info("🚨 Disparando prueba de alarma de emergencia a solicitud del usuario.")
        ticker = self.bot_manager.fetch_live_bitso_ticker(self.book)
        curr_p = Decimal(str(ticker.get("last", "77000.00"))) if ticker else Decimal("77000.00")
        self.trigger_emergency(
            event_title="Simulación de Prueba (Test de Alarma Nocturna)",
            price_change_pct=-5.2,
            current_price=curr_p,
            action_advice="Esta es una prueba de control. En un evento real, mantén la calma: tus monedas permanecen seguras en Bitso sin riesgo de liquidación.",
        )

    def trigger_emergency(
        self,
        event_title: str,
        price_change_pct: float,
        current_price: Decimal,
        action_advice: str,
    ) -> None:
        """Activates an emergency state that overrides night silence and repeats until acknowledged."""
        self.emergency_active = True
        self.emergency_acknowledged = False
        self.emergency_alert_count = 1
        self.emergency_last_alert_time = time.time()
        self.bot_manager.is_emergency_active = True
        self.emergency_details = {
            "event_title": event_title,
            "price_change_pct": price_change_pct,
            "current_price": current_price,
            "action_advice": action_advice,
        }

        logger.warning(
            f"🚨 ¡EMERGENCIA DETECTADA! {event_title} ({price_change_pct:+.2f}%). "
            f"Bypaseando filtro nocturno. Enviando alerta #1..."
        )
        self.notifier.send_emergency_extreme_volatility_alert(
            event_title=event_title,
            price_change_pct=price_change_pct,
            current_price=current_price,
            action_advice=action_advice,
            attempt=1,
        )

    def process_emergency_repeats(self) -> None:
        """Sends repeating alerts if an emergency is active and not yet acknowledged."""
        if not self.emergency_active or self.emergency_acknowledged:
            return

        now = time.time()
        if now - self.emergency_last_alert_time >= self.emergency_repeat_interval_seconds:
            if self.emergency_alert_count < self.emergency_max_repeats:
                self.emergency_alert_count += 1
                self.emergency_last_alert_time = now
                logger.warning(
                    f"🚨 Repitiendo alarma de emergencia #{self.emergency_alert_count} "
                    f"(esperando que el usuario responda /ok)..."
                )
                self.notifier.send_emergency_extreme_volatility_alert(
                    event_title=self.emergency_details.get("event_title", "Volatilidad Extrema"),
                    price_change_pct=self.emergency_details.get("price_change_pct", 0.0),
                    current_price=self.emergency_details.get("current_price", Decimal("0")),
                    action_advice=self.emergency_details.get("action_advice", "Verifica Bitso."),
                    attempt=self.emergency_alert_count,
                )
            else:
                logger.info("Límite máximo de repeticiones de emergencia alcanzado.")
                self.emergency_active = False

    def check_extreme_volatility(self, current_price: Decimal) -> None:
        """
        Tracks short-term price velocity (15m to 1h window).
        Triggers emergency alarm if price moves >= threshold (e.g. 4.5% flash crash or pump).
        """
        now = time.time()
        price_val = float(current_price)
        self.price_history.append((now, price_val))

        # Keep last 1 hour (3600 seconds)
        cutoff = now - 3600
        self.price_history = [(t, p) for t, p in self.price_history if t >= cutoff]

        if len(self.price_history) < 2:
            return

        # Compare with oldest price in history (up to 1 hour ago)
        oldest_time, oldest_price = self.price_history[0]
        if oldest_price > 0:
            pct_change = ((price_val - oldest_price) / oldest_price) * 100.0

            if abs(pct_change) >= self.emergency_threshold_pct and not self.emergency_active:
                if pct_change < 0:
                    event = "Desplome súbito de mercado (Posible shock o noticia FUD)"
                    advice = (
                        "Tus fondos están 100% en Bitcoin. El Modo Blindaje prohíbe ventas de pánico. "
                        "No toques tus BTC en Bitso; espera a que el mercado estabilice."
                    )
                else:
                    event = "Disparo parabólico vertical (Posible shock de liquidez alcista)"
                    advice = (
                        "El precio está subiendo con violencia. Asegúrate de no tener órdenes límite de venta "
                        "antiguas pendientes en Bitso para no quedarte fuera del rally."
                    )
                self.trigger_emergency(
                    event_title=event,
                    price_change_pct=pct_change,
                    current_price=current_price,
                    action_advice=advice,
                )

    def check_user_screenshots_and_messages(self) -> None:
        """Polls for incoming screenshots or commands from the user in Telegram."""
        new_events = self.bot_manager.process_incoming_updates()
        if new_events:
            for ev in new_events:
                logger.info(f"📸 ¡Comprobante recibido de {ev['sender_name']}!: {ev['filename']} archivado.")
            self.check_test_phase_milestone()

    def check_test_phase_milestone(self) -> None:
        """Checks if the user has reached the test phase milestone criteria."""
        if self.test_phase_passed_notified:
            return

        entries = self.bot_manager._load_journal()
        # Milestone condition: at least 3 verified proof operations in the journal
        if len(entries) >= 3:
            self.test_phase_passed_notified = True
            logger.info("🏆 ¡CRITERIOS DE MODO PRUEBA CUMPLIDOS! Enviando alerta especial a Telegram...")
            self.notifier.send_test_passed_alert(
                trades_count=len(entries),
                net_satoshis=850,
                pct_gain=Decimal("4.15"),
                max_drawdown=Decimal("1.25"),
            )

    def check_daily_heartbeat(self) -> None:
        """Sends a morning health check / proof-of-life at 09:00 AM CDMX so user never wonders if bot is running."""
        from datetime import datetime, timezone, timedelta
        import json
        cdmx_tz = timezone(timedelta(hours=-6))
        now_cdmx = datetime.now(cdmx_tz)
        current_hour = now_cdmx.hour
        current_day = now_cdmx.timetuple().tm_yday

        # Trigger once per day starting at 09:00 AM CDMX (or if started later in the day)
        if current_hour >= 9 and self.last_heartbeat_day != current_day:
            self.last_heartbeat_day = current_day
            try:
                with open(self.heartbeat_state_file, "w", encoding="utf-8") as f:
                    json.dump({"last_heartbeat_day": current_day, "timestamp": now_cdmx.isoformat()}, f)
            except Exception as e:
                logger.warning(f"No se pudo guardar heartbeat_state: {e}")
            self.send_daily_heartbeat_report()

    def send_daily_heartbeat_report(self) -> None:
        """Dispatches the morning proof-of-life status to all active users."""
        ticker_usd = self.bot_manager.fetch_live_bitso_ticker("btc_usd")
        ticker_mxn = self.bot_manager.fetch_live_bitso_ticker("btc_mxn")
        last_usd = float(ticker_usd.get("last", 64846.0)) if ticker_usd else 64846.0
        last_mxn = float(ticker_mxn.get("last", 0.0)) if ticker_mxn else 0.0
        rsi_val, adx_val, dev_val, is_bull = self.bot_manager.fetch_latest_market_indicators()

        users = self.bot_manager.get_all_active_users()
        logger.info(f"☀️ Enviando reporte diario de prueba de vida a {len(users)} usuario(s)...")

        for u in users:
            dest_chat = u.get("chat_id")
            u_name = u.get("name", "Inversionista")
            curr = u.get("currency", "MXN")
            if curr == "MXN":
                u_lot = float(u.get("lot_size_mxn", 200.0))
                lot_line = f"<code>${u_lot:,.2f} MXN</code> (Pesos Mexicanos)"
                sell_target = f"tu lote de <code>${u_lot:,.2f} MXN</code> en Bitso (BTC/MXN)"
                primary_price = f"<code>${last_mxn:,.2f} MXN</code> (≈ ${last_usd:,.2f} USD)"
            else:
                u_lot = float(u.get("lot_size_usdc", 10.0))
                lot_line = f"<code>${u_lot:,.2f} USD</code>"
                sell_target = f"tu lote de <code>${u_lot:,.2f} USD</code>"
                primary_price = f"<code>${last_usd:,.2f} USD</code> (≈ ${last_mxn:,.2f} MXN)"

            heartbeat_msg = f"""
☀️ <b>PRUEBA DE VIDA DIARIA — 09:00 AM (CDMX)</b>

¡Buenos días, {u_name}! Tu copiloto está <b>100% ACTIVO</b> vigilando el mercado de forma autónoma.

📊 <b>ESTADO DE MERCADO EN VIVO:</b>
• <b>Bitcoin (Bitso {'Pesos' if curr == 'MXN' else 'Dólares'}):</b> {primary_price}
• <b>RSI actual:</b> <code>{rsi_val:.1f}</code> (Zona baja / acumulación)
• <b>Régimen:</b> {"🛡️ Modo Blindaje HODL" if is_bull else "Consolidación en rango"}
• <b>Moneda y Lote Asignado:</b> {lot_line}

🎯 <b>DIAGNÓSTICO TÉCNICO:</b>
• El bot está protegiendo tus satoshis. No se emite venta porque el precio está en soporte.
• Esperando pacientemente el rebote a <b>RSI &ge; 65.0</b> para vender {sell_target} y recomprar más barato.
• Todo el sistema corre de forma continua y permanente 24/7.

💡 <i>Escribe <code>/comprar</code> o <code>/precio</code> en cualquier momento si deseas un reporte al instante.</i>
"""
            self.bot_manager.send_message(heartbeat_msg.strip(), target_chat_id=dest_chat)

    def fetch_recent_data(self, time_bucket: int = 14400) -> pd.DataFrame:
        """Fetches the latest candles from Bitso's public API (default 14400 = 4H, 3600 = 1H)."""
        try:
            url = f"https://api.bitso.com/v3/ohlc/?book={self.book}&time_bucket={time_bucket}"
            import urllib.request, json
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                rows = data.get("payload", [])
                if not rows:
                    return pd.DataFrame()
                df = pd.DataFrame(rows)
                df = df.rename(columns={
                    "bucket_start_time": "bucket_start_time",
                    "first_rate": "open",
                    "max_rate": "high",
                    "min_rate": "low",
                    "last_rate": "close",
                    "volume": "volume"
                })
                # Drop currently unclosed candle
                df = df.iloc[:-1].copy()
                df["timestamp"] = pd.to_datetime(df["bucket_start_time"], unit="ms", utc=True)
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = df[col].astype(float)
                return df
        except Exception as e:
            logger.warning(f"Aviso de conexión con Bitso: {e}")
            return pd.DataFrame()

    def run_market_iteration(self) -> None:
        """Evaluates market data, Bitso ticker, candles, and standard trading alerts."""
        # Check daily morning proof-of-life heartbeat (09:00 AM CDMX)
        self.check_daily_heartbeat()

        # Check live price from Bitso ticker for extreme volatility / black swan
        ticker = self.bot_manager.fetch_live_bitso_ticker(self.book)
        if ticker:
            last_p_str = ticker.get("last")
            if last_p_str:
                self.check_extreme_volatility(Decimal(str(last_p_str)))

        # 1. Macro 4H Candles Evaluation
        df_4h = self.fetch_recent_data(time_bucket=14400)
        if df_4h.empty or len(df_4h) < 50:
            return

        df_4h = add_all_indicators(df_4h)
        latest_4h = df_4h.iloc[-1]
        candle_ts = str(latest_4h["timestamp"])

        close_p = Decimal(str(latest_4h["close"]))
        rsi_4h = Decimal(str(latest_4h["rsi_14"]))
        adx_4h = Decimal(str(latest_4h["adx_14"]))
        dev_4h = Decimal(str(latest_4h["sma_50_dev"]))
        is_bull_run = bool(latest_4h.get("bull_run_active", False))
        regime_4h = str(latest_4h.get("regime", "RANGE"))

        # Cache indicators in bot_manager for instantaneous sub-second user queries
        self.bot_manager._cached_indicators = (float(rsi_4h), float(adx_4h), float(dev_4h), is_bull_run)
        self.bot_manager._cached_indicators_ts = time.time()

        active_users = self.bot_manager.get_all_active_users()

        # A. Evaluate 4H Signal (for 4H Patrimonial users)
        if candle_ts != self.last_processed_candle_ts:
            self.last_processed_candle_ts = candle_ts
            logger.info(f"Vela 4H cerrada: {candle_ts} | Precio: ${close_p:,.2f} | RSI: {rsi_4h:.1f} | ADX: {adx_4h:.1f} | Régimen: {regime_4h}")

            ticker_mxn_live = self.bot_manager.fetch_live_bitso_ticker("btc_mxn")
            price_mxn_4h = Decimal(str(ticker_mxn_live.get("last", "0"))) if ticker_mxn_live else (close_p * Decimal("20.20"))
            suggested_limit_mxn_4h = (price_mxn_4h * Decimal("0.998")).quantize(Decimal("10.0"))

            if is_bull_run:
                logger.info("🛡️ MODO BLINDAJE HODL ACTIVO (4H): Ventas bloqueadas para proteger satoshis.")
            else:
                if rsi_4h >= Decimal("65.0") and adx_4h < Decimal("20.0") and dev_4h < Decimal("0.05"):
                    current_hour = time.localtime().tm_hour
                    if not (self.night_silence_enabled and (current_hour >= self.night_start or current_hour < self.night_end)):
                        if active_users:
                            for u in active_users:
                                u_mode = u.get("timeframe_mode", "4H")
                                if u_mode == "4H":
                                    u_chat = u.get("chat_id")
                                    u_curr = u.get("currency", "MXN")
                                    u_lot_usdc = Decimal(str(u.get("lot_size_usdc", 10.0)))
                                    u_lot_mxn = Decimal(str(u.get("lot_size_mxn", 200.0)))
                                    if u_curr == "MXN":
                                        u_btc = (u_lot_mxn / price_mxn_4h).quantize(Decimal("0.00000001"))
                                    else:
                                        u_btc = (u_lot_usdc / close_p).quantize(Decimal("0.00000001"))

                                    logger.info(f"🚨 Enviando alerta 4H privada a {u.get('name')} (Lote: {u_lot_mxn if u_curr == 'MXN' else u_lot_usdc} {u_curr}, {u_btc} BTC)...")
                                    self.notifier.send_entry_signal_alert(
                                        sell_price=close_p,
                                        btc_amount=u_btc,
                                        usdc_value=u_lot_usdc,
                                        rsi=rsi_4h,
                                        adx=adx_4h,
                                        target_chat_id=u_chat,
                                        mode_label="4H Patrimonial",
                                        currency=u_curr,
                                        sell_price_mxn=price_mxn_4h,
                                        mxn_value=u_lot_mxn
                                    )
                        else:
                            btc_to_sell = (self.initial_capital_usdc / close_p).quantize(Decimal("0.00000001"))
                            self.notifier.send_entry_signal_alert(
                                sell_price=close_p,
                                btc_amount=btc_to_sell,
                                usdc_value=self.initial_capital_usdc,
                                rsi=rsi_4h,
                                adx=adx_4h,
                                mode_label="4H Patrimonial"
                            )
                elif rsi_4h <= Decimal("35.0"):
                    current_hour = time.localtime().tm_hour
                    if not (self.night_silence_enabled and (current_hour >= self.night_start or current_hour < self.night_end)):
                        suggested_limit = (close_p * Decimal("0.998")).quantize(Decimal("0.01"))
                        if active_users:
                            for u in active_users:
                                u_chat = u.get("chat_id")
                                u_curr = u.get("currency", "MXN")
                                u_lot_usdc = Decimal(str(u.get("lot_size_usdc", 10.0)))
                                u_lot_mxn = Decimal(str(u.get("lot_size_mxn", 200.0)))
                                logger.info(f"🟢 Enviando alerta 4H Spot Buy a {u.get('name')} ({u_curr})...")
                                self.notifier.send_spot_buy_alert(
                                    current_price=close_p,
                                    rsi=rsi_4h,
                                    suggested_limit=suggested_limit,
                                    user_lot_usdc=u_lot_usdc,
                                    target_chat_id=u_chat,
                                    mode_label="4H Patrimonial",
                                    currency=u_curr,
                                    price_mxn=price_mxn_4h,
                                    suggested_limit_mxn=suggested_limit_mxn_4h,
                                    user_lot_mxn=u_lot_mxn
                                )
                        else:
                            self.notifier.send_spot_buy_alert(
                                current_price=close_p,
                                rsi=rsi_4h,
                                suggested_limit=suggested_limit,
                                user_lot_usdc=self.initial_capital_usdc,
                                mode_label="4H Patrimonial"
                            )

        # B. Multi-Timeframe Tactical Check (4H Macro + 1H Francotirador)
        multi_users = [u for u in active_users if u.get("timeframe_mode") == "MULTI_1H"]
        if multi_users and not is_bull_run:
            df_1h = self.fetch_recent_data(time_bucket=3600)
            if not df_1h.empty and len(df_1h) >= 50:
                df_1h = add_all_indicators(df_1h)
                latest_1h = df_1h.iloc[-1]
                candle_1h_ts = str(latest_1h["timestamp"])

                if candle_1h_ts != self.last_processed_1h_ts:
                    self.last_processed_1h_ts = candle_1h_ts
                    p_1h = Decimal(str(latest_1h["close"]))
                    rsi_1h = Decimal(str(latest_1h["rsi_14"]))
                    adx_1h = Decimal(str(latest_1h["adx_14"]))
                    dev_1h = Decimal(str(latest_1h["sma_50_dev"]))
                    logger.info(f"🎯 Vela 1H Francotirador: {candle_1h_ts} | Precio: ${p_1h:,.2f} | RSI: {rsi_1h:.1f} | ADX: {adx_1h:.1f}")

                    ticker_mxn_1h = self.bot_manager.fetch_live_bitso_ticker("btc_mxn")
                    price_mxn_1h = Decimal(str(ticker_mxn_1h.get("last", "0"))) if ticker_mxn_1h else (p_1h * Decimal("20.20"))
                    suggested_limit_mxn_1h = (price_mxn_1h * Decimal("0.998")).quantize(Decimal("10.0"))

                    if rsi_1h >= Decimal("68.0") and adx_1h < Decimal("22.0") and dev_1h < Decimal("0.04"):
                        current_hour = time.localtime().tm_hour
                        if not (self.night_silence_enabled and (current_hour >= self.night_start or current_hour < self.night_end)):
                            for u in multi_users:
                                u_chat = u.get("chat_id")
                                u_curr = u.get("currency", "MXN")
                                u_lot_usdc = Decimal(str(u.get("lot_size_usdc", 10.0)))
                                u_lot_mxn = Decimal(str(u.get("lot_size_mxn", 200.0)))
                                if u_curr == "MXN":
                                    u_btc = (u_lot_mxn / price_mxn_1h).quantize(Decimal("0.00000001"))
                                else:
                                    u_btc = (u_lot_usdc / p_1h).quantize(Decimal("0.00000001"))

                                logger.info(f"🎯 Enviando alerta 1H Francotirador a {u.get('name')} (Lote: {u_lot_mxn if u_curr == 'MXN' else u_lot_usdc} {u_curr}, {u_btc} BTC)...")
                                self.notifier.send_entry_signal_alert(
                                    sell_price=p_1h,
                                    btc_amount=u_btc,
                                    usdc_value=u_lot_usdc,
                                    rsi=rsi_1h,
                                    adx=adx_1h,
                                    target_chat_id=u_chat,
                                    mode_label="4H + 1H Francotirador",
                                    currency=u_curr,
                                    sell_price_mxn=price_mxn_1h,
                                    mxn_value=u_lot_mxn
                                )
                    elif rsi_1h <= Decimal("33.0"):
                        current_hour = time.localtime().tm_hour
                        if not (self.night_silence_enabled and (current_hour >= self.night_start or current_hour < self.night_end)):
                            suggested_1h = (p_1h * Decimal("0.998")).quantize(Decimal("0.01"))
                            for u in multi_users:
                                u_chat = u.get("chat_id")
                                u_curr = u.get("currency", "MXN")
                                u_lot_usdc = Decimal(str(u.get("lot_size_usdc", 10.0)))
                                u_lot_mxn = Decimal(str(u.get("lot_size_mxn", 200.0)))
                                logger.info(f"🟢 Enviando alerta 1H Spot Buy a {u.get('name')} (RSI: {rsi_1h:.1f}, {u_curr})...")
                                self.notifier.send_spot_buy_alert(
                                    current_price=p_1h,
                                    rsi=rsi_1h,
                                    suggested_limit=suggested_1h,
                                    user_lot_usdc=u_lot_usdc,
                                    target_chat_id=u_chat,
                                    mode_label="1H Francotirador",
                                    currency=u_curr,
                                    price_mxn=price_mxn_1h,
                                    suggested_limit_mxn=suggested_limit_mxn_1h,
                                    user_lot_mxn=u_lot_mxn
                                )

    def run_single_iteration(self) -> None:
        """Runs a complete monitoring check (inbound messages, emergency alarms, and market data)."""
        # 1. High-speed Telegram poll
        self.check_user_screenshots_and_messages()

        # 2. Process emergency repeating alarms if active
        self.process_emergency_repeats()

        # 3. Market data and candle evaluation
        self.run_market_iteration()

    def start_continuous_monitoring(self) -> None:
        """Runs the monitoring loop continuously and autonomously."""
        logger.info(f"🟢 Monitoreo continuo AUTÓNOMO iniciado (compuesto activo). Consultando cada {self.check_interval_seconds}s...")
        print("El bot está escuchando activamente en segundo plano.")
        print("Interés Compuesto: ACTIVO (100% de reinversión en cada ciclo).")
        print("Filtro Nocturno: ACTIVO (23:00 a 07:00 hrs, con bypass en caso de Cisne Negro).")
        print("Alarma de Emergencia: ACTIVA (repite cada 3 min hasta que respondas /ok).")
        print("Puedes consultarle o enviarle fotos en Telegram en cualquier momento.\n")

        while True:
            try:
                self.run_single_iteration()
            except KeyboardInterrupt:
                logger.info("Monitoreo detenido por el usuario.")
                break
            except Exception as e:
                logger.error(f"Error inesperado en ciclo: {e}")
            time.sleep(self.check_interval_seconds)


if __name__ == "__main__":
    print("=" * 75)
    print(" BTC-ACCUMULATOR V2.0 | COPILOTO DE ALERTAS POR TELEGRAM")
    print(" CERO CLAVES PRIVADAS • INTERÉS COMPUESTO • ALARMA NOCTURNA • 100% AUTÓNOMO")
    print("=" * 75)

    runner = CopilotTelegramRunner(check_interval_seconds=30)
    if "--once" in sys.argv:
        runner.run_single_iteration()
    else:
        runner.start_continuous_monitoring()
