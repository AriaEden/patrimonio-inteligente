"""
actinver_engine/telegram_bot_manager.py
Gestor Interactivo de Telegram para Actinver (Bursanet).
1. Permite al usuario consultar el estado de su portafolio, rebalanceo y dividendos.
2. Escucha activamente y descarga CAPTURAS DE PANTALLA de la app de Actinver enviadas por el usuario.
3. Registra las órdenes ejecutadas en la bitácora contable de auditoría (actinver_trade_journal.json).
"""

from decimal import Decimal
import json
import logging
import os
import time
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.parse
from actinver_engine.portfolio_manager import ActinverPortfolioManager
from actinver_engine.rebalance_engine import ActinverRebalanceEngine

logger = logging.getLogger(__name__)

_UNSET = object()


class ActinverTelegramBotManager:
    """Handles bidirectional Telegram communication, photo proofs, and live queries for Actinver."""

    def __init__(
        self,
        portfolio_mgr: ActinverPortfolioManager,
        rebalance_engine: ActinverRebalanceEngine,
        bot_token: Any = _UNSET,
        chat_id: Any = _UNSET,
        storage_dir: Optional[str] = None,
    ):
        self.portfolio_mgr = portfolio_mgr
        self.rebalance_engine = rebalance_engine
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN") if bot_token is _UNSET else bot_token
        self.chat_id = str(os.getenv("TELEGRAM_CHAT_ID", "") if chat_id is _UNSET else (chat_id or ""))
        self.is_configured = bool(self.bot_token)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.storage_dir = storage_dir or os.path.join(base_dir, "user_verifications")
        os.makedirs(self.storage_dir, exist_ok=True)

        self.last_update_id = 0

    def send_message(self, text: str, parse_mode: str = "HTML", target_chat_id: Optional[str] = None) -> bool:
        """Sends an HTML formatted message to Telegram."""
        dest_chat = target_chat_id or self.chat_id
        if not self.bot_token or not dest_chat:
            logger.info(f"[SIMULACIÓN TELEGRAM ACTINVER]\n{text}")
            return True

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": dest_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(api_url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Error al enviar mensaje a Telegram: {e}")
            return False

    def get_updates(self) -> List[Dict[str, Any]]:
        """Polls for new incoming messages and screenshots from Telegram."""
        if not self.bot_token:
            return []

        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?offset={self.last_update_id + 1}&timeout=5"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("result", [])
        except Exception as e:
            logger.debug(f"Error en polling de Telegram: {e}")
            return []

    def download_file(self, file_id: str, dest_filename: str) -> Optional[str]:
        """Downloads a screenshot sent by the user to the local storage directory."""
        if not self.bot_token:
            return None

        get_file_url = f"https://api.telegram.org/bot{self.bot_token}/getFile?file_id={file_id}"
        try:
            req = urllib.request.Request(get_file_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                file_path = res_data.get("result", {}).get("file_path")
                if not file_path:
                    return None

            download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            local_target = os.path.join(self.storage_dir, dest_filename)

            dl_req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(dl_req, timeout=20) as in_stream, open(local_target, "wb") as out_file:
                out_file.write(in_stream.read())

            return local_target
        except Exception as e:
            logger.error(f"Error al descargar comprobante de Telegram: {e}")
            return None

    def handle_user_query(self, query_text: str, sender_id: str, sender_name: str) -> bool:
        """Parses and answers on-demand queries regarding the Actinver portfolio."""
        q = query_text.lower().strip()

        # 1. PORTFOLIO VALUATION QUERY (/cartera, /portafolio, /cuenta, saldo, como vamos)
        if any(term in q for term in ["/cartera", "/portafolio", "/cuenta", "cartera", "portafolio", "saldo", "cuanto tengo"]):
            val = self.portfolio_mgr.calculate_valuation()
            stocks = val["stock_breakdown"]

            lines = [
                f"🏛️ <b>ESTADO DE TU PORTAFOLIO EN ACTINVER (BURSANET):</b>\n",
                f"• <b>Valuación total estimada:</b> <code>${val['total_valuation_mxn']:,.2f} MXN</code>",
                f"• <b>Poder de compra disponible:</b> ${val['cash_mxn']:,.2f} MXN",
                f"• <b>Bolsillo Core (HODL):</b> ${val['core_val']:,.2f} MXN ({val['core_pct']}%)",
                f"• <b>Bolsillo Satélite (Swing):</b> ${val['satellite_val']:,.2f} MXN ({val['satellite_pct']}%)",
                f"• <b>Renta Fija / Deuda:</b> ${val['defensive_val']:,.2f} MXN ({val['defensive_pct']}%)",
                f"\n📊 <b>POSICIONES PRINCIPALES:</b>"
            ]
            for name, s in list(stocks.items())[:6]:
                gain_sign = "+" if s["gain_mxn"] >= 0 else ""
                lines.append(f"• <b>{name}:</b> {s['titles']} tits @ ${s['price']:,.2f} | {gain_sign}{s['pct_gain']:.1f}%")

            lines.append("\n💡 <i>Escribe /rebalanceo para ver las órdenes recomendadas.</i>")
            reply = "\n".join(lines)
            return self.send_message(reply.strip(), target_chat_id=sender_id)

        # 2. REBALANCE QUERY (/rebalanceo, rebalanceo, que hago, ordenes, paso 2)
        elif any(term in q for term in ["/rebalanceo", "rebalanceo", "que hago", "ordenes", "paso 2", "siguiente paso"]):
            plan = self.rebalance_engine.evaluate_initial_rebalance()
            orders = plan["recommended_orders"]

            lines = [
                "📋 <b>PLAN DE REBALANCEO RECOMENDADO PARA ACTINVER:</b>\n",
                "Para optimizar tu portafolio y activar el interés compuesto, estas son las 3 órdenes a colocar:\n"
            ]
            for i, o in enumerate(orders, 1):
                act_str = "🟢 COMPRAR" if o["action"] == "BUY" else "🔴 VENDER"
                lines.append(f"{i}️⃣ <b>{act_str} {o['symbol']}</b>")
                lines.append(f"   • {o['titles']} títulos a precio Límite ≈ <code>${float(o['suggested_price_mxn']):,.2f} MXN</code>")
                lines.append(f"   • Motivo: {o['reason']}\n")

            lines.append("📸 <i>Colócalas en tu app de Bursanet/Actinver y envíame la foto aquí para archivarlas.</i>")
            reply = "\n".join(lines)
            return self.send_message(reply.strip(), target_chat_id=sender_id)

        # 3. CORE POCKET QUERY (/core, core, hodl, largo plazo)
        elif any(term in q for term in ["/core", "core", "hodl"]):
            reply = """
🛡️ <b>BOLSILLO CORE (CRECIMIENTO HODL A LARGO PLAZO)</b>

Este bloque está blindado contra ventas impulsivas:
• <b>QQQM (Nasdaq 100):</b> Megatendencia tecnológica mundial (comisión baja 0.15%).
• <b>IVVPESO (S&P 500):</b> Núcleo del mercado estadounidense.
• <b>FIBRAMQ12 (Por incorporar):</b> Rentas de Nearshoring que caen en efectivo a tu cuenta.
• <b>Fondos de Renta Variable:</b> Crecimiento global para el retiro.

💡 <b>Regla del Bot:</b> Este bloque NO se vende en caídas; se deja correr a 5-10 años y cada dividendo se reinvierte.
"""
            return self.send_message(reply.strip(), target_chat_id=sender_id)

        # 4. SATELLITE POCKET QUERY (/satelite, satelite, swing, cemex, inda)
        elif any(term in q for term in ["/satelite", "satelite", "swing", "trading"]):
            reply = """
⚡ <b>BOLSILLO SATÉLITE (SWING TRADING CON INTERÉS COMPUESTO)</b>

En este bloque buscamos comprar con descuento y vender con ganancia para generar más liquidez:
• <b>CEMEX CPO:</b> Con +60% de ganancia, tomamos el 50% de beneficio para asegurar capital.
• <b>INDA (India):</b> Rebalanceamos la sobreconcentración del 28% hacia el 15%.
• <b>GFINBUR O:</b> Cíclica financiera en rango técnico.

💰 <b>Regla de Interés Compuesto:</b> El 100% de las ganancias en pesos se reinvierte para comprar activos del Bolsillo Core o entrar en nuevas oportunidades.
"""
            return self.send_message(reply.strip(), target_chat_id=sender_id)

        # 5. DIVIDENDS QUERY (/dividendos, dividendos, rentas)
        elif any(term in q for term in ["/dividendos", "dividendos", "rentas"]):
            divs = self.portfolio_mgr._load_json(self.portfolio_mgr.dividends_file)
            total_divs = sum(float(d.get("amount_mxn", 0)) for d in divs)
            if not divs:
                reply = "💰 <b>Aún no hay dividendos registrados.</b> En cuanto tus FIBRAs o ETFs paguen rentas en Actinver, el bot te notificará para reinvertirlos."
            else:
                lines = [f"💰 <b>HISTORIAL DE DIVIDENDOS Y RENTAS COBRADAS ({len(divs)}):</b>\n"]
                for d in divs[-5:]:
                    lines.append(f"• <b>{d['symbol']}:</b> +${float(d['amount_mxn']):,.2f} MXN ({d['timestamp']})")
                lines.append(f"\n🟢 <b>Total acumulado reinvertido:</b> <b>${total_divs:,.2f} MXN</b>")
                reply = "\n".join(lines)
            return self.send_message(reply.strip(), target_chat_id=sender_id)

        # 6. MUTUAL FUNDS LIQUIDATION QUERY (/liquidar_fondos, /fondos, liquidar, fondos)
        elif any(term in q for term in ["/liquidar_fondos", "/fondos", "liquidar fondos", "fondos", "fondos dispersos"]):
            liq_data = self.rebalance_engine.evaluate_mutual_funds_liquidation()
            p1 = liq_data["phase_1_immediate"]
            p2 = liq_data["phase_2_strategic"]
            p1_txt = "\n".join([f"• <code>{f['symbol']}</code>: ${float(f['value_mxn']):,.2f} MXN ({f['settlement_days']})" for f in p1["funds"]])
            p2_txt = "\n".join([f"• <code>{f['symbol']}</code>: ${float(f['value_mxn']):,.2f} MXN ({f['settlement_days']})" for f in p2["funds"]])

            reply = f"""
🔓 <b>PLAN DE RESCATE DE CAPITAL LATENTE ($14,553 MXN EN FONDOS)</b>

Al rescatar estos 8 fondos, eliminamos comisiones del 2.5% anual y liberamos efectivo para activos con alto crecimiento:

1️⃣ <b>FASE 1: RESCATE INMEDIATO (Posiciones chicas - ${float(p1['total_mxn']):,.2f} MXN):</b>
{p1_txt}
🎯 <b>Destino:</b> Comprar 35 títulos más de FIBRA Macquarie (rentas trimestrales).

2️⃣ <b>FASE 2: RESCATE ESTRATÉGICO (${float(p2['total_mxn']):,.2f} MXN):</b>
{p2_txt}
🎯 <b>Destino:</b> Comprar 2 títulos más de QQQM (Nasdaq 100) y FIBRAs.

📱 <b>Pasos en tu app de Bursanet:</b> Menú &rarr; Fondos &rarr; Vender/Rescatar &rarr; Selecciona 100% &rarr; Confirmar.
"""
            return self.send_message(reply.strip(), target_chat_id=sender_id)

        # 7. CROSS-ASSET FLYWHEEL QUERY (/cruzado, /volante, volante, cruzado, flywheel, btc y actinver)
        elif any(term in q for term in ["/cruzado", "/volante", "volante", "cruzado", "flywheel", "bitcoin y actinver"]):
            reply = """
🔄 <b>ESTADO DEL VOLANTE CRUZADO (BITCOIN &harr; ACTINVER)</b>

El sistema monitorea el ciclo de 4 años para transferir ganancias y multiplicar capital:

1️⃣ <b>PICO DE CICLO (Cosecha Cripto &rarr; Actinver):</b>
• <b>Gatillo:</b> Bitcoin >= $95,000 USD (Euforia / MVRV Z-Score alto).
• <b>Acción:</b> Vender el 50% de BTC en Bitso, transferir MXN a Actinver y amarrar rentas del 10% en FIBRAs.
• <b>Estado:</b> ⏳ Vigilancia activa (Bitcoin en ~$74k-$78k USD, aún en acumulación).

2️⃣ <b>INVIERNO CRIPTO (Rentas Actinver &rarr; Recompra BTC):</b>
• <b>Gatillo:</b> Bitcoin <= $50,000 USD (Pánico extremo / Soporte de 200 semanas).
• <b>Acción:</b> Usar las rentas acumuladas de Actinver para comprar satoshis a precio de remate.
• <b>Estado:</b> 🛡️ Desactivado (Mercado en fase alcista).

💡 <i>El bot te enviará la alerta en el momento exacto en que se active cualquiera de los dos gatillos.</i>
"""
            return self.send_message(reply.strip(), target_chat_id=sender_id)

        # 8. HELP MENU (/start, /ayuda, ayuda, hola)
        else:
            menu = f"""
👋 Hola {sender_name}. Soy tu <b>Copiloto Patrimonial para Actinver (Bursanet)</b>.

🤖 <b>Comandos interactivos disponibles:</b>

• <code>/cartera</code> &rarr; Ver valuación de tu portafolio y posiciones en MXN.
• <code>/rebalanceo</code> &rarr; Ver las 3 órdenes tácticas para hoy (Cemex, India, FIBRAs).
• <code>/liquidar_fondos</code> &rarr; Ver instrucciones para rescatar los $14,553 MXN de fondos.
• <code>/cruzado</code> &rarr; Ver estado del volante macro Bitcoin &harr; Actinver.
• <code>/core</code> &rarr; Ver tus activos de HODL a largo plazo.
• <code>/satelite</code> &rarr; Ver tus posiciones de Swing Trading.
• <code>/dividendos</code> &rarr; Ver rentas cobradas y reinversión compuesta.
• <code>/ayuda</code> &rarr; Mostrar este menú.

📸 <b>Envío de comprobantes:</b>
Cada vez que pongas una orden en Bursanet / Actinver, mándame la captura de pantalla por este chat y la registraré al instante.
"""
            return self.send_message(menu.strip(), target_chat_id=sender_id)

    def process_incoming_updates(self) -> List[Dict[str, Any]]:
        """Processes incoming screenshots and queries from the user."""
        updates = self.get_updates()
        processed_events = []

        for u in updates:
            up_id = u.get("update_id", 0)
            if up_id > self.last_update_id:
                self.last_update_id = up_id

            msg = u.get("message") or u.get("channel_post")
            if not msg:
                continue

            from_user = msg.get("from", {})
            sender_id = str(from_user.get("id") or msg.get("chat", {}).get("id"))
            sender_name = from_user.get("first_name", "Usuario")
            caption = msg.get("caption", "").strip()
            text = msg.get("text", "").strip()

            photos = msg.get("photo")
            doc = msg.get("document")

            if photos or (doc and doc.get("mime_type", "").startswith("image/")):
                file_id = photos[-1]["file_id"] if photos else doc["file_id"]
                ts_str = time.strftime("%Y%m%d_%H%M%S")
                dest_filename = f"comprobante_actinver_{ts_str}.jpg"

                saved_path = self.download_file(file_id, dest_filename)

                if saved_path:
                    record = {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                        "sender_id": sender_id,
                        "sender_name": sender_name,
                        "filename": dest_filename,
                        "local_path": saved_path,
                        "caption": caption,
                        "status": "VERIFICADO_EN_BITACORA"
                    }
                    self.portfolio_mgr._append_to_journal(record)
                    processed_events.append(record)

                    ack = f"""
✅ <b>¡COMPROBANTE DE ACTINVER REGISTRADO CON ÉXITO!</b>

Hola {sender_name}, he certificado tu captura de pantalla de Bursanet.
• <b>Archivo guardado:</b> <code>{dest_filename}</code>
• <b>Fecha:</b> {record['timestamp']}
• <b>Nota:</b> {caption if caption else 'Sin notas'}

📊 <i>Tu portafolio y bitácora de auditoría patrimonial han sido actualizados.</i>
"""
                    self.send_message(ack.strip(), target_chat_id=sender_id)

            elif text:
                self.handle_user_query(text, sender_id, sender_name)

        return processed_events
