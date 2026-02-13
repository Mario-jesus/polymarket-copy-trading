# Polymarket Copy Trading

Bot de copy trading para [Polymarket](https://polymarket.com) que sigue las operaciones de una wallet objetivo y replica automáticamente compras/ventas en tu propia cuenta.

## Requisitos

- Python 3.13 o superior
- Cuenta en Polymarket con API key (PyClob)
- Billetera con fondos en USDC en Polygon

## Instalación

1. Clona el repositorio:

```bash
git clone https://github.com/Mario-jesus/polymarket-copy-trading.git
cd polymarket-copy-trading
```

2. Instala dependencias (opción recomendada con Pipenv):

```bash
pip install pipenv   # si no tienes pipenv instalado
pipenv install
pipenv shell         # activa el entorno
```

Si prefieres no usar Pipenv, usa `pip` con `requirements.txt`:

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

3. Configura las variables de entorno (ver siguiente sección).

## Configuración

Copia el archivo `.env.example` a `.env` (o crea `.env` manualmente) y completa los valores. La aplicación usa [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) con variables anidadas usando el prefijo `SECCIÓN__CLAVE`.

### Variables obligatorias

| Variable | Descripción |
|----------|-------------|
| `POLYMARKET__PRIVATE_KEY` | Clave privada de la wallet que ejecutará las órdenes |
| `POLYMARKET__API_KEY` | API Key de Polymarket (PyClob) |
| `POLYMARKET__API_SECRET` | API Secret |
| `POLYMARKET__API_PASSPHRASE` | API Passphrase |
| `POLYMARKET__FUNDER` | Dirección de la proxy wallet (Wallet Address en la UI de Polymarket) |
| `TRACKING__TARGET_WALLET` | Dirección de la wallet a seguir (0x...) |

### Variables opcionales

| Variable | Default | Descripción |
|----------|---------|-------------|
| `TRACKING__POLL_SECONDS` | 3.0 | Intervalo de polling para detectar trades (segundos) |
| `TRACKING__TRADES_LIMIT` | 20 | Cantidad de trades por consulta |
| `STRATEGY__FIXED_POSITION_AMOUNT_USDC` | 10 | USDC por posición al abrir |
| `STRATEGY__MAX_ACTIVE_LEDGERS` | 10 | Máximo de assets (mercados) con posiciones abiertas |
| `STRATEGY__CLOSE_TOTAL_THRESHOLD_PCT` | 80 | % de cierre del trader para cerrar posiciones (ej: 80 = 80%) |
| `TELEGRAM__ENABLED` | false | Habilitar notificaciones por Telegram |
| `TELEGRAM__API_KEY` | - | Token del bot de Telegram |
| `TELEGRAM__CHAT_ID` | - | Chat ID para notificaciones |
| `LOGGING__CONSOLE_LEVEL` | INFO | Nivel de log (DEBUG, INFO, WARNING, ERROR) |

### Ejemplo de `.env` mínimo

```env
# Polymarket (obligatorio)
POLYMARKET__CLOB_HOST=https://clob.polymarket.com
POLYMARKET__CHAIN_ID=137
POLYMARKET__PRIVATE_KEY=0x...
POLYMARKET__API_KEY=...
POLYMARKET__API_SECRET=...
POLYMARKET__API_PASSPHRASE=...
POLYMARKET__FUNDER=0x...
POLYMARKET__SIGNER=0x...

# Tracking (obligatorio)
TRACKING__TARGET_WALLET=0x...

# Opcional
STRATEGY__FIXED_POSITION_AMOUNT_USDC=10
```

> **Nota**: Si usas `TRACKING__TARGET_WALLETS` con varias wallets separadas por coma, se usa solo la primera.

## Uso

### Desde la línea de comandos

Desde la raíz del proyecto (donde está la carpeta `src`):

```bash
PYTHONPATH=src python -m polymarket_copy_trading.main
```

Para detener: `Ctrl+C`. El sistema hará un shutdown ordenado (cierre de sesión de tracking, colas, notificaciones).

### Desde Jupyter Notebook

1. Abre el notebook `notebooks/POLYMARKET_COPY_TRADING.ipynb`.
2. Ejecuta la primera celda para configurar el path:

```python
import sys
from pathlib import Path
root = Path.cwd().resolve()
if root.name == "notebooks":
    root = root.parent
src_dir = root / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
```

3. Ejecuta el runner:

```python
from polymarket_copy_trading.main import run
await run()
```

4. Para detener: interrumpe el kernel (Interrupt).

## Arquitectura resumida

- **TradeTracker**: Consulta trades de la wallet objetivo vía Polymarket Data API.
- **TradeConsumer**: Procesa trades de la cola y los envía al `TradeProcessorService`.
- **PostTrackingEngine / CopyTradingEngineService**: Mantiene ledgers de posiciones y decide cuándo abrir/cerrar.
- **MarketOrderExecutionService**: Ejecuta órdenes de compra/venta en el CLOB.
- **OrderAnalysisWorker**: Reconoce órdenes colocadas con trades reales en el CLOB.
- **NotificationService**: Envía eventos a consola y opcionalmente a Telegram.

## Seguridad

- **No compartas tu `.env`** ni lo subas a repositorios. El `.env` suele estar en `.gitignore`.
- Usa una wallet dedicada con fondos limitados para copy trading.
- Las credenciales de Polymarket permiten operar en tu cuenta: protégelas.

## Licencia

Ver archivo LICENSE en el repositorio.
