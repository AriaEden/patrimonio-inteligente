# BTC-Accumulator V1.3: Validación de Datos y Ejecuciones

Motor de trading algorítmico institucional en Python para evaluar estrategias de **acumulación neta de Bitcoin (BTC)** frente a retención pasiva (**HODL**), operando en los libros spot de **Bitso Alpha**.

---

## 1. Novedades y Mejoras Clave de la Versión 1.3

1. **Validación de la Ventana de 2 Horas con Datos de 1 Hora:**
   * Las señales se generan en velas cerradas de 4 horas, pero la ejecución de las órdenes post-only (vigencia de 2 horas) se evalúa estrictamente utilizando las velas horarias consecutivas de la Hora 1 ($t$ a $t+1h$) y Hora 2 ($t+1h$ a $t+2h$).
   * Se descartan llenados falsos provocados por movimientos alcistas que ocurren en las horas 3 o 4 de la vela de 4 horas.
2. **Erradicación de Supuestos Arbitrarios de Ejecución Parcial:**
   * Se eliminó el llenado artificial del 50% en toques de 1 tick. Sin datos directos del libro de órdenes, no se asumen llenados fraccionales inventados.
3. **Resolución Intravela de Salidas Contradictorias:**
   * Si una vela de 4 horas alcanza simultáneamente el objetivo de recompra (-2.5%) y el stop defensivo (+3.0%), se analiza la secuencia temporal horaria intravela. Si no hay datos concluyentes, se aplica el principio conservador del peor caso (*Worst-Case Principle*).
4. **Doble Escenario de Simulación:**
   * **Escenario Conservador (Línea Base Oficial):** Toques sin penetración en 2 horas caducan sin llenar.
   * **Escenario Optimista (Cota Superior):** Toques exactos se asumen ejecutados.
5. **Verificación y Procedencia de Datos Históricos:**
   * Descarga reproducible desde Bitso API v3 (`btc_accumulator/fetch_data.py`).
   * 10,525 velas de 4 horas y 42,100 velas de 1 hora consecutivas con **0 huecos temporales**.
   * Precios contrastados contra eventos macroeconómicos independientes con 0.00% de discrepancia.
6. **Gestión de Cartera e Interés Compuesto:**
   * Capital inicial experimental de **10 USD equivalentes en BTC** al inicio de cada período.
   * Contabilidad estricta en `Decimal` sin redondeos prematuros de comisiones (0.30% maker / 0.36% taker).
   * Monitoreo dual de riesgo: Drawdown Realizado vs. Drawdown Marcado a Mercado (MtM), con regla de suspensión preventiva al alcanzar el 5% de MtM Drawdown.

---

## 2. Ejecución y Pruebas

### Ejecutar las Pruebas Automatizadas (39 pruebas unitarias)
```powershell
pytest -v
```

### Ejecutar el Pipeline Comparativo Completo
```powershell
python main.py
```

### Descargar y Verificar los Datos Históricos desde Bitso API v3
```powershell
python btc_accumulator/fetch_data.py
```

---

## 3. Entregables Generados

* **Reporte HTML Comparativo**: `reports/btc_accumulator_v1_3_report.html` (Tablero interactivo con doble escenario, walk-forward y registro de operaciones).
* **Registro de Operaciones (CSV)**:
  * `reports/trades_and_balances_v1.3_conservative.csv` (Escenario Conservador).
  * `reports/trades_and_balances_v1.3_optimistic.csv` (Escenario Optimista).
  * `reports/trades_and_balances_v1.3.csv` (Historial unificado).
* **Resumen de Auditoría Técnico**: `RESUMEN_AUDITORIA.md`.
* **Datasets Verificados de Bitso**:
  * `data/bitso_btc_usd_4h.csv` (10,525 velas de 4H).
  * `data/bitso_btc_usd_1h.csv` (42,100 velas de 1H).
* **Archivo ZIP de Auditoría**: `BTC_Accumulator_V1.3_Auditoria.zip`.
