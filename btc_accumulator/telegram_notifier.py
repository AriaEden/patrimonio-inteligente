"""
btc_accumulator/telegram_notifier.py
Módulo de Notificaciones y Alertas por Telegram para Modo Copiloto Asistido.
Permite que el bot envíe señales de compra/venta y reportes periódicos directamente
a tu celular por Telegram, eliminando la necesidad de claves API de trading o retiros.
Cero dependencias externas (utiliza urllib nativo de Python).
"""

from decimal import Decimal
import json
import logging
import os
import re
from typing import Optional, Dict, Any
import urllib.request
import urllib.parse
import urllib.error

logger = logging.getLogger(__name__)

_UNSET = object()


class TelegramNotifier:
    """Dispatches real-time signal alerts and periodic accounting reports via Telegram."""

    def __init__(
        self,
        bot_token: Any = _UNSET,
        chat_id: Any = _UNSET,
    ):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN") if bot_token is _UNSET else bot_token
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID") if chat_id is _UNSET else chat_id
        self.is_configured = bool(self.bot_token and self.chat_id)

        if not self.is_configured:
            logger.info("Telegram Notifier en modo simulación: TELEGRAM_BOT_TOKEN o CHAT_ID no configurados.")

    def send_message(self, text: str, parse_mode: Optional[str] = "HTML", target_chat_id: Optional[str] = None) -> bool:
        """Sends an HTML/Markdown formatted message to the configured Telegram chat with zero-loss fallback."""
        dest_chat = target_chat_id or self.chat_id
        if not self.is_configured or not dest_chat:
            logger.info(f"[SIMULACIÓN TELEGRAM]\n{text}")
            return True

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": dest_chat,
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
                if resp.status == 200:
                    logger.info("Notificación enviada exitosamente a Telegram.")
                    return True
                else:
                    logger.error(f"Error al enviar mensaje a Telegram (HTTP {resp.status})")
                    return False
        except urllib.error.HTTPError as e:
            if e.code == 400 and parse_mode:
                logger.warning(f"Error de formato HTML en alerta ({e}). Reenviando al instante en texto plano...")
                clean_text = re.sub(r'<[^>]+>', '', text)
                clean_text = clean_text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", "\"").replace("&rarr;", "->").replace("&harr;", "<->")
                payload_fb = {
                    "chat_id": dest_chat,
                    "text": clean_text,
                    "disable_web_page_preview": True,
                }
                try:
                    data_fb = json.dumps(payload_fb).encode("utf-8")
                    req_fb = urllib.request.Request(api_url, data=data_fb, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req_fb, timeout=10) as resp_fb:
                        return resp_fb.status == 200
                except Exception as e_fb:
                    logger.error(f"Fallo en reintento texto plano alerta: {e_fb}")
                    return False
            logger.error(f"Error al enviar mensaje a Telegram (HTTP {e.code}): {e}")
            return False
        except Exception as e:
            logger.error(f"Excepción al conectar con Telegram API: {e}")
            return False

    def send_entry_signal_alert(
        self,
        sell_price: Decimal,
        btc_amount: Decimal,
        usdc_value: Decimal,
        rsi: Decimal,
        adx: Decimal,
        current_hour: Optional[int] = None,
        target_chat_id: Optional[str] = None,
        mode_label: str = "4H Patrimonial",
        currency: str = "MXN",
        sell_price_mxn: Optional[Decimal] = None,
        mxn_value: Optional[Decimal] = None,
    ) -> bool:
        """Sends a high-priority entry sell signal alert with exact manual execution instructions and time-aware order advice."""
        import time
        hour = current_hour if current_hour is not None else time.localtime().tm_hour

        pair_str = "BTC / MXN (Pesos Mexicanos)" if currency == "MXN" else "BTC / USD (o BTC/USDC)"
        price_disp = f"${float(sell_price_mxn):,.2f} MXN (≈ ${float(sell_price):,.2f} USD)" if (currency == "MXN" and sell_price_mxn) else f"${float(sell_price):,.2f} USD"
        val_disp = f"${float(mxn_value):,.2f} MXN" if (currency == "MXN" and mxn_value) else f"${float(usdc_value):,.2f} USD"

        if 20 <= hour < 23:
            time_advice = f"""
🌙 <b>RECOMENDACIÓN POR PROXIMIDAD A LA NOCHE ({hour}:00 hrs):</b>
• <b>Tipo de Orden recomendada:</b> <b>LÍMITE (Maker)</b> con vigencia <i>"Hasta ser cancelada" (GTC)</i>.
• <b>¿Por qué?</b> Te permite irte a dormir con total tranquilidad. Si el precio alcanza los {price_disp} durante la noche, Bitso la ejecutará sola al centavo exacto pagando la menor comisión (Maker 0.10%). No necesitas vigilar la pantalla ni desvelarte.
• 🚫 <i>Evita órdenes de Mercado antes de dormir para no sufrir comisiones altas ni deslizamiento de precio.</i>
"""
        elif 23 <= hour or hour < 7:
            time_advice = f"""
🌙 <b>HORARIO NOCTURNO ({hour}:00 hrs):</b>
• <b>Tipo de Orden recomendada:</b> <b>LÍMITE (Maker)</b> pasiva. Déjala colocada en Bitso y continúa descansando.
"""
        else:
            time_advice = f"""
☀️ <b>RECOMENDACIÓN DE EJECUCIÓN DIURNA ({hour}:00 hrs):</b>
• <b>Tipo de Orden recomendada:</b> <b>LÍMITE (Maker)</b>. Colócala en el libro de Bitso para pagar tarifa reducida de creador (Maker 0.10%).
"""

        message = f"""
🚨 <b>ALERTA BTC-ACCUMULATOR: OPORTUNIDAD DE VENTA [{mode_label.upper()}]</b>

Se ha detectado una condición de sobrecompra en rango lateral ({mode_label}).

📋 <b>INSTRUCCIONES PARA TU APP DE BITSO:</b>
• <b>Modo Operativo:</b> {mode_label}
• <b>Par de Trading:</b> <code>{pair_str}</code>
• <b>Tipo de Orden:</b> <b>LÍMITE (Maker)</b>
• <b>Precio de Venta:</b> <code>{price_disp}</code>
• <b>Cantidad a Vender:</b> <code>{float(btc_amount):.8f} BTC</code> (≈ {val_disp})
• <b>Vigencia:</b> Hasta ser cancelada (GTC)
{time_advice.strip()}

🎯 <i>Objetivo posterior: Recompraremos con 2.5% de descuento para acumular Satoshis netos.</i>
"""
        return self.send_message(message.strip(), target_chat_id=target_chat_id)

    def send_target_buyback_alert(
        self,
        buyback_price: Decimal,
        usdc_budget: Decimal,
        est_btc_acquired: Decimal,
        satoshis_earned: int,
        target_chat_id: Optional[str] = None,
        currency: str = "MXN",
        buyback_price_mxn: Optional[Decimal] = None,
        mxn_budget: Optional[Decimal] = None,
    ) -> bool:
        """Sends a take-profit target buyback alert."""
        pair_str = "BTC / MXN (Pesos Mexicanos)" if currency == "MXN" else "BTC / USD"
        price_disp = f"${float(buyback_price_mxn):,.2f} MXN (≈ ${float(buyback_price):,.2f} USD)" if (currency == "MXN" and buyback_price_mxn) else f"${float(buyback_price):,.2f} USD"
        budget_disp = f"${float(mxn_budget):,.2f} MXN" if (currency == "MXN" and mxn_budget) else f"${float(usdc_budget):,.2f} USDC"

        message = f"""
🎯 <b>OBJETIVO CUMPLIDO: RECOMPRA CON DESCUENTO</b>

Bitcoin retrocedió el 2.5% previsto. ¡Es momento de embolsar la ganancia!

📋 <b>INSTRUCCIONES PARA TU APP DE BITSO:</b>
• <b>Acción:</b> <b>COMPRAR BITCOIN</b>
• <b>Par de Trading:</b> <code>{pair_str}</code>
• <b>Tipo de Orden recomendada:</b> <b>LÍMITE (Maker)</b>
• <b>Precio Límite:</b> <code>{price_disp}</code>
• <b>Monto a gastar:</b> <code>{budget_disp}</code>
• <b>Bitcoin estimado:</b> <code>{float(est_btc_acquired):.8f} BTC</code>
• <b>Vigencia:</b> Good 'Til Cancelled (Hasta ser cancelada)

💡 <i>Con la orden LÍMITE, dejas la postura puesta y te puedes ir a dormir; Bitso comprará sola si toca el precio.</i>
💰 <b>Ganancia neta:</b> <b>+{satoshis_earned:,} satoshis</b> sobre tu capital inicial.
"""
        return self.send_message(message.strip(), target_chat_id=target_chat_id)

    def send_defensive_stop_alert(
        self,
        stop_price: Decimal,
        usdc_budget: Decimal,
        target_chat_id: Optional[str] = None,
    ) -> bool:
        """Sends an emergency stop-loss notification."""
        message = f"""
⚠️ <b>FRENO DE EMERGENCIA: STOP DEFENSIVO</b>

El precio de Bitcoin superó el +3.0% sobre la venta. Activando salida protectora.

📋 <b>INSTRUCCIONES PARA TU APP DE BITSO:</b>
• <b>Acción:</b> <b>COMPRAR BITCOIN INMEDIATAMENTE (Taker / Mercado)</b>
• <b>Monto a gastar:</b> <code>${float(usdc_budget):,.2f} USDC</code>
• <b>Precio de referencia:</b> ≈ <code>${float(stop_price):,.2f} USD</code>

🛡️ <i>Asumimos una pequeña pérdida controlada para mantener tus Bitcoin a salvo y no quedarnos fuera del mercado.</i>
"""
        return self.send_message(message.strip(), target_chat_id=target_chat_id)

    def send_periodic_report(self, report_text: str) -> bool:
        """Dispatches the plain-language executive periodic account summary."""
        formatted = f"<pre>{report_text}</pre>"
        return self.send_message(formatted)

    def send_test_passed_alert(
        self,
        trades_count: int,
        net_satoshis: int,
        pct_gain: Decimal,
        max_drawdown: Decimal,
    ) -> bool:
        """Sends celebratory and actionable alert when the test phase criteria are met."""
        message = f"""
🏆 <b>¡MODO PRUEBA SUPERADO CON ÉXITO!</b> 🚀

Estimado copiloto, tu sistema ha cumplido satisfactoriamente con la <b>Matriz de Aprobación</b>:

📊 <b>RESULTADOS DEL PERÍODO DE PRUEBA:</b>
• <b>Operaciones completadas:</b> {trades_count}
• <b>Rendimiento neto en Bitcoin:</b> <b>+{net_satoshis:,} satoshis</b> ({pct_gain:+.2f}% frente a HODL)
• <b>Interés Compuesto:</b> 🟢 100% activo y reinvertido
• <b>Riesgo y Control:</b> Drawdown máximo {float(max_drawdown):.2f}% (dentro del límite seguro &lt; 5%)
• <b>Disciplina Macro:</b> Cero ventas en fases alcistas parabólicas

🎯 <b>CONCLUSIÓN TÉCNICA:</b>
El algoritmo ha demostrado solidez matemática, estabilidad operativa y protección de capital.

💡 <b>Siguiente paso:</b> Estás en posición técnica favorable para valorar si es el momento oportuno de escalar e invertir una mayor cantidad de capital. Escribe <code>/escalar</code> para conocer la estrategia recomendada.
"""
        return self.send_message(message.strip())

    def send_scaling_plan_alert(
        self,
        current_btc: Decimal,
        current_sats: int,
        target_capital_usdc: Decimal = Decimal("100.00"),
    ) -> bool:
        """Sends the exact scaling strategy when transitioning from $10 to $100 USD."""
        message = f"""
📈 <b>ESTRATEGIA DE ESCALAMIENTO A ${float(target_capital_usdc):,.0f} USD (SISTEMA APROBADO)</b>

Al haber certificado la rentabilidad en la prueba de $10 USD, este es el plan estructurado para multiplicar el capital a ${float(target_capital_usdc):,.0f} USD minimizando riesgos:

📋 <b>PLAN TÉCNICO DE TRANSICIÓN:</b>
1️⃣ <b>Asignación Modular (2 Lotes de $50 USD):</b>
   • En lugar de lanzar una sola orden de $100 USD, dividiremos el capital en <b>2 tranches de $50 USD</b>.
   • Lote 1: Entra en sobrecompra estándar (RSI &gt;= 65).
   • Lote 2: Entra en sobrecompra extrema (RSI &gt;= 75) como respaldo.
   • <i>Beneficio:</i> Reduce a la mitad el impacto de cualquier retroceso fallido.

2️⃣ <b>Preservación de tus Ganancias de Prueba:</b>
   • Tus {current_sats:,} satoshis ganados en la fase de prueba se mantienen en la cartera principal como ganancia consolidada intocable.

3️⃣ <b>Regla de Riesgo Escalada (5% MtM):</b>
   • En $100 USD, la pérdida máxima tolerada de seguridad antes de suspensión se ajusta a <b>$5.00 USD</b> (en satoshis equivalentes).
   • El freno de emergencia automático sigue 100% activo.

4️⃣ <b>Comisiones Bitso Reducidas:</b>
   • Con $100 USD por ciclo, el volumen mensual crecerá 10 veces más rápido, acelerando el paso a niveles de comisiones preferenciales en Bitso.
"""
        return self.send_message(message.strip())

    def send_emergency_extreme_volatility_alert(
        self,
        event_title: str,
        price_change_pct: float,
        current_price: Decimal,
        action_advice: str,
        attempt: int = 1,
    ) -> bool:
        """Dispatches an urgent emergency volatility alarm that repeats until acknowledged."""
        repeat_text = f"🚨 [ALARMA CONTINUA #{attempt}]" if attempt > 1 else "🚨 [ALARMA DE EMERGENCIA]"
        message = f"""
{repeat_text} <b>VOLATILIDAD EXTREMA DETECTADA EN BITCOIN</b> ⚠️

<b>¡ATENCIÓN!</b> Se detectó un movimiento brusco anormal en el mercado ({price_change_pct:+.2f}%):
• <b>Precio actual en Bitso:</b> <code>${float(current_price):,.2f} USD</code>
• <b>Tipo de Evento:</b> {event_title}

📋 <b>ACCIÓN REQUERIDA:</b>
{action_advice}

🔕 <b>Para apagar esta alarma sonora en tu celular:</b>
Responde a este mensaje con la palabra <code>/ok</code> o envía cualquier mensaje.
"""
        return self.send_message(message.strip())

    def send_spot_buy_alert(
        self,
        current_price: Decimal,
        rsi: Decimal,
        suggested_limit: Decimal,
        user_lot_usdc: Decimal,
        target_chat_id: Optional[str] = None,
        mode_label: str = "4H Patrimonial",
        currency: str = "MXN",
        price_mxn: Optional[Decimal] = None,
        suggested_limit_mxn: Optional[Decimal] = None,
        user_lot_mxn: Optional[Decimal] = None,
    ) -> bool:
        """Sends a high-priority spot accumulation buy alert when RSI is in oversold/discount territory."""
        if currency == "MXN" and price_mxn and user_lot_mxn and suggested_limit_mxn:
            satoshis_est = int((user_lot_mxn / price_mxn) * Decimal("100000000")) if price_mxn > 0 else 16000
            pair_name = "BTC / MXN (Pesos Mexicanos)"
            price_str = f"${float(price_mxn):,.2f} MXN (≈ ${float(current_price):,.2f} USD)"
            suggested_str = f"${float(suggested_limit_mxn):,.2f} MXN"
            lot_str = f"${float(user_lot_mxn):,.2f} MXN"
            app_advice = "Bitso App Móvil o Bitso Alpha (Libro BTC/MXN en Pesos)"
            sub_title = "EN PESOS MEXICANOS"
            footer_note = "Esta señal está optimizada para operar directamente con tus pesos mexicanos (SPEI) sin necesidad de cambiarlos a dólares."
        else:
            satoshis_est = int((user_lot_usdc / current_price) * Decimal("100000000")) if current_price > 0 else 15000
            pair_name = "BTC / USD"
            price_str = f"${float(current_price):,.2f} USD"
            suggested_str = f"${float(suggested_limit):,.2f} USD"
            lot_str = f"${float(user_lot_usdc):,.2f} USD"
            app_advice = "Bitso Alpha (Libro BTC/USD)"
            sub_title = "EN DÓLARES"
            footer_note = "Esta señal es para acumulación de ahorro patrimonial al contado con dólares/USDC."

        message = f"""
🟢 <b>ALERTA COPILOTO: OPORTUNIDAD DE COMPRA SPOT [{sub_title}]</b>

Bitcoin ha entrado en <b>Zona de Descuento y Soporte Técnico</b>.
• <b>Precio actual BTC:</b> <code>{price_str}</code>
• <b>RSI (Fuerza):</b> <code>{float(rsi):.1f}</code> (Zona baja / Sobreventa atractiva)

🎯 <b>INSTRUCCIONES PARA TU APP DE BITSO:</b>
1. <b>Plataforma:</b> {app_advice}
2. <b>Par de Trading:</b> <code>{pair_name}</code>
3. <b>Tipo de Orden:</b> Coloca una orden <b>LÍMITE (Maker)</b>.
4. <b>Precio Sugerido:</b> <code>{suggested_str}</code> (tarifa mínima Maker del 0.10%).
5. <b>Monto a Operar:</b> Tu cuota de ahorro de <b>{lot_str}</b> (≈ <b>{satoshis_est:,} satoshis</b>).
6. <b>Vigencia:</b> GTC (<i>"Hasta ser cancelada"</i>). Bitso la ejecutará de forma automática al tocar el precio.

💡 <i>{footer_note}</i>
"""
        return self.send_message(message.strip(), target_chat_id=target_chat_id)
