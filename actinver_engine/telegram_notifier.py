"""
actinver_engine/telegram_notifier.py
Módulo de Notificaciones y Alertas por Telegram para el Copiloto de Actinver (Bursanet).
Despacha órdenes de rebalanceo, señales de swing trading y avisos de cobro de dividendos/rentas
directamente al celular del usuario sin requerir claves bancarias.
"""

from decimal import Decimal
import json
import logging
import os
import re
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.parse
import urllib.error

logger = logging.getLogger(__name__)

_UNSET = object()


class ActinverTelegramNotifier:
    """Dispatches trade instructions and portfolio accounting reports via Telegram."""

    def __init__(
        self,
        bot_token: Any = _UNSET,
        chat_id: Any = _UNSET,
    ):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN") if bot_token is _UNSET else bot_token
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID") if chat_id is _UNSET else chat_id
        self.is_configured = bool(self.bot_token and self.chat_id)

        if not self.is_configured:
            logger.info("Actinver Telegram Notifier en modo simulación: TELEGRAM_BOT_TOKEN o CHAT_ID no configurados.")

    def send_message(self, text: str, parse_mode: Optional[str] = "HTML") -> bool:
        """Sends an HTML formatted message to Telegram with zero-loss fallback."""
        if not self.is_configured:
            logger.info(f"[SIMULACIÓN TELEGRAM ACTINVER]\n{text}")
            return True

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                api_url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 400 and parse_mode:
                logger.warning(f"Error formato HTML alerta Actinver ({e}). Reenviando como texto plano...")
                clean_text = re.sub(r'<[^>]+>', '', text)
                clean_text = clean_text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", "\"").replace("&rarr;", "->").replace("&harr;", "<->")
                payload_fb = {
                    "chat_id": self.chat_id,
                    "text": clean_text,
                    "disable_web_page_preview": True,
                }
                try:
                    data_fb = json.dumps(payload_fb).encode("utf-8")
                    req_fb = urllib.request.Request(api_url, data=data_fb, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req_fb, timeout=10) as resp_fb:
                        return resp_fb.status == 200
                except Exception as e_fb:
                    logger.error(f"Fallo en reintento texto plano Actinver: {e_fb}")
                    return False
            logger.error(f"Error al enviar mensaje a Telegram (HTTP {e.code}): {e}")
            return False
        except Exception as e:
            logger.error(f"Error al enviar mensaje a Telegram: {e}")
            return False

    def send_rebalance_plan_alert(self, rebalance_data: Dict[str, Any]) -> bool:
        """Sends the initial Step 2 rebalancing execution plan to Telegram."""
        orders = rebalance_data.get("recommended_orders", [])
        total_val = rebalance_data.get("current_valuation_mxn", 0.0)

        lines = [
            "🏛️ <b>PLAN DE REBALANCEO TÁCTICO — ACTINVER (BURSANET)</b> 📊",
            "",
            f"<b>Valuación actual de tu portafolio:</b> ${total_val:,.2f} MXN",
            "<i>Estrategia: Asegurar ganancias en Cemex, balancear India y activar rentas compuestas en FIBRAs.</i>",
            "",
            "📋 <b>ÓRDENES RECOMENDADAS PARA COLOCAR HOY EN TU APP:</b>"
        ]

        for i, o in enumerate(orders, 1):
            action_emoji = "🟢 <b>COMPRAR</b>" if o.get("action", "BUY") == "BUY" else "🔴 <b>VENDER</b>"
            o_name = o.get("name") or o.get("symbol", "Activo")
            o_type = o.get("order_type", "LÍMITE (Limit)")
            o_price = float(o.get("suggested_price_mxn", 0.0))
            o_titles = o.get("titles", 1)
            o_total = float(o.get("est_total_mxn", o_price * o_titles))
            o_reason = o.get("reason", "Rebalanceo de portafolio")
            lines.append(f"""
{i}️⃣ {action_emoji} <b>{o.get('symbol', 'TÍTULO')}</b> ({o_name})
• <b>Tipo de Orden:</b> <b>{o_type}</b>
• <b>Títulos a operar:</b> <code>{o_titles} títulos</code>
• <b>Precio Límite sugerido:</b> <code>${o_price:,.2f} MXN</code>
• <b>Importe aproximado:</b> ≈ ${o_total:,.2f} MXN
• <b>Vigencia:</b> 1 a 3 días hábiles
• 🎯 <b>Motivo:</b> {o_reason}
""")

        lines.append("""
💡 <b>CÓMO REGISTRARLO:</b>
En cuanto coloques o se ejecuten estas órdenes en tu app de Bursanet / Actinver, <b>envíame la captura de pantalla por este chat</b>. La registraré de inmediato en tu bitácora de auditoría.
""")
        return self.send_message("\n".join(lines).strip())

    def send_swing_signal_alert(
        self,
        action: str,
        symbol: str,
        price_mxn: Decimal,
        titles: int,
        reason: str,
        pocket: str = "SATELLITE"
    ) -> bool:
        """Sends an active swing trading signal for the satellite pocket."""
        action_word = "VENTA (Toma de Ganancias)" if action.upper() == "SELL" else "COMPRA (Oportunidad en Soporte)"
        icon = "🎯" if action.upper() == "SELL" else "🛒"

        message = f"""
{icon} <b>SEÑAL DE SWING TRADING: {action_word}</b>

📋 <b>INSTRUCCIONES PARA TU APP DE ACTINVER (BURSANET):</b>
• <b>Emisora:</b> <code>{symbol}</code>
• <b>Acción:</b> <b>{action.upper()}</b>
• <b>Tipo de Orden:</b> <b>LÍMITE</b>
• <b>Precio Límite:</b> <code>${float(price_mxn):,.2f} MXN</code>
• <b>Cantidad sugerida:</b> <code>{titles} títulos</code> (≈ ${float(titles * price_mxn):,.2f} MXN)
• <b>Bolsillo:</b> {pocket} (Interés compuesto activo)

🎯 <b>Análisis técnico:</b> {reason}
📸 <i>Envíame captura de pantalla cuando la pongas para certificarla en tu bitácora.</i>
"""
        return self.send_message(message.strip())

    def send_dividend_collected_alert(
        self,
        symbol: str,
        amount_mxn: Decimal,
        reinvestment_advice: str
    ) -> bool:
        """Sends a notification when a dividend or FIBRA rent is deposited in Actinver."""
        message = f"""
💰 <b>¡RENTA / DIVIDENDO RECIBIDO EN ACTINVER!</b> 🚀

Se ha registrado un pago en efectivo en tu cuenta:
• <b>Emisora:</b> <code>{symbol}</code>
• <b>Monto depositado:</b> <b>+${float(amount_mxn):,.2f} MXN</b>
• <b>Efecto:</b> 🟢 Interés Compuesto DRIP listo para reinvertirse.

📋 <b>RECOMENDACIÓN DE REINVERSIÓN:</b>
{reinvestment_advice}
"""
        return self.send_message(message.strip())

    def send_mutual_funds_liquidation_alert(self, liquidation_data: Dict[str, Any]) -> bool:
        """Sends clear, step-by-step instructions to redeem the 8 scattered mutual funds."""
        total_cap = liquidation_data.get("total_dormant_capital_mxn", 0.0)
        p1 = liquidation_data.get("phase_1_immediate", {})
        p2 = liquidation_data.get("phase_2_strategic", {})

        p1_funds = "\n".join([f"• <b>{f['symbol']}</b> ({f['category']}): ${float(f['value_mxn']):,.2f} MXN [Liquida {f['settlement_days']}]" for f in p1.get("funds", [])])
        p2_funds = "\n".join([f"• <b>{f['symbol']}</b> ({f['category']}): ${float(f['value_mxn']):,.2f} MXN [Liquida {f['settlement_days']}]" for f in p2.get("funds", [])])

        message = f"""
🔓 <b>PLAN DE RESCATE DE CAPITAL LATENTE: FONDOS DISPERSOS</b>

Al rescatar estos 8 fondos, <b>desbloqueamos ${float(total_cap):,.2f} MXN en efectivo</b> para comprar activos con rendimiento del 15% al 20% anual y cero comisiones parasitarias.

📋 <b>FASE 1: LIQUIDACIÓN INMEDIATA (Posiciones Residuales - ${float(p1.get('total_mxn', 0)):,.2f} MXN)</b>
{p1_funds}
🎯 <b>Destino del efectivo:</b> {p1.get('reinvestment_target')}

📋 <b>FASE 2: LIQUIDACIÓN ESTRATÉGICA (${float(p2.get('total_mxn', 0)):,.2f} MXN)</b>
{p2_funds}
🎯 <b>Destino del efectivo:</b> {p2.get('reinvestment_target')}

📱 <b>CÓMO VENDERLOS EN TU APP DE BURSANET / ACTINVER:</b>
1. Abre tu app y entra a la sección <b>Fondos</b> (o toca cada fondo en tu portafolio).
2. Selecciona la opción <b>VENDER / RESCATAR</b>.
3. Elige <b>"Monto Total" o "Todos los Títulos"</b>.
4. Confirma la orden (se liquidará en el horario bancario).
5. Tómale captura y mándamela aquí para registrar el efectivo liberado.
"""
        return self.send_message(message.strip())

    def send_cross_asset_flywheel_alert(self, flywheel_signal: Dict[str, Any]) -> bool:
        """Dispatches cross-asset rotation alerts between Bitcoin and Actinver."""
        direction = flywheel_signal.get("direction")
        btc_p = flywheel_signal.get("btc_price_usd", Decimal("0"))
        reason = flywheel_signal.get("reason", "")
        advice = flywheel_signal.get("transfer_advice", "")

        icon = "🔄"
        title = "CRIPTO &rarr; ACTINVER (COSECHA MACRO)" if direction == "CRIPTO_A_ACTINVER" else "ACTINVER &rarr; CRIPTO (RECOMPRA GENERACIONAL)"

        message = f"""
{icon} <b>ALERTA DE VOLANTE CRUZADO: {title}</b>

Se ha activado una condición de rotación macro en el ciclo de 4 años:
• <b>Precio actual de Bitcoin:</b> <code>${float(btc_p):,.2f} USD</code>
• <b>Gatillo:</b> 🟢 Condición de ciclo cumplida.

📋 <b>MOTIVO CUANTITATIVO:</b>
{reason}

💼 <b>ACCIÓN REQUERIDA:</b>
{advice}
"""
        return self.send_message(message.strip())
