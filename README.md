# Polymarket Copy Trading

Copy trading bot for [Polymarket](https://polymarket.com) that tracks a target wallet's activity and automatically replicates buy/sell orders in your own account.

## Requirements

- Python 3.13 or higher
- Polymarket account with API key (PyClob)
- Wallet with USDC on Polygon

## Installation

1. Clone the repository:

```bash
git clone https://github.com/Mario-jesus/polymarket-copy-trading.git
cd polymarket-copy-trading
```

2. Install dependencies (recommended with Pipenv):

```bash
pip install pipenv   # if you don't have pipenv installed
pipenv install
pipenv shell         # activates the environment
```

If you prefer not to use Pipenv, use `pip` with `requirements.txt`:

```bash
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

3. Configure environment variables (see next section).

## Configuration

Copy the `.env.example` file to `.env` (or create `.env` manually) and fill in the values. The application uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) with nested variables using the `SECTION__KEY` prefix.

### Required variables

| Variable | Description |
|----------|-------------|
| `POLYMARKET__PRIVATE_KEY` | Private key of the wallet that will execute orders |
| `POLYMARKET__API_KEY` | Polymarket API key (PyClob) |
| `POLYMARKET__API_SECRET` | API Secret |
| `POLYMARKET__API_PASSPHRASE` | API Passphrase |
| `POLYMARKET__FUNDER` | Proxy wallet address (Wallet Address in Polymarket UI) |
| `TRACKING__TARGET_WALLET` | Address of the wallet to track (0x...) |

### Optional variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACKING__POLL_SECONDS` | 3.0 | Polling interval to detect trades (seconds) |
| `TRACKING__TRADES_LIMIT` | 20 | Number of trades per request |
| `STRATEGY__FIXED_POSITION_AMOUNT_USDC` | 10 | USDC per position when opening |
| `STRATEGY__MAX_ACTIVE_LEDGERS` | 10 | Maximum number of assets (markets) with open positions |
| `STRATEGY__CLOSE_TOTAL_THRESHOLD_PCT` | 80 | % of trader's close to trigger position closure (e.g. 80 = 80%) |
| `TELEGRAM__ENABLED` | false | Enable Telegram notifications |
| `TELEGRAM__API_KEY` | - | Telegram bot token |
| `TELEGRAM__CHAT_ID` | - | Chat ID for notifications |
| `LOGGING__CONSOLE_LEVEL` | INFO | Log level (DEBUG, INFO, WARNING, ERROR) |

### Minimal `.env` example

```env
# Polymarket (required)
POLYMARKET__CLOB_HOST=https://clob.polymarket.com
POLYMARKET__CHAIN_ID=137
POLYMARKET__PRIVATE_KEY=0x...
POLYMARKET__API_KEY=...
POLYMARKET__API_SECRET=...
POLYMARKET__API_PASSPHRASE=...
POLYMARKET__FUNDER=0x...
POLYMARKET__SIGNER=0x...

# Tracking (required)
TRACKING__TARGET_WALLET=0x...

# Optional
STRATEGY__FIXED_POSITION_AMOUNT_USDC=10
```

> **Note**: If you use `TRACKING__TARGET_WALLETS` with multiple comma-separated wallets, only the first one is used.

## Usage

### From the command line

From the project root (where the `src` folder is):

```bash
PYTHONPATH=src pipenv run python -m polymarket_copy_trading.main
```

To stop: press `Ctrl+C`. The system will perform an orderly shutdown (tracking session close, queues, notifications).

### From Jupyter Notebook

1. Open the notebook `notebooks/POLYMARKET_COPY_TRADING.ipynb`.
2. Run the first cell to set up the path:

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

3. Run the runner:

```python
from polymarket_copy_trading.main import run
await run()
```

4. To stop: interrupt the kernel (Interrupt).

## Architecture overview

- **TradeTracker**: Fetches trades from the target wallet via Polymarket Data API.
- **TradeConsumer**: Processes trades from the queue and sends them to `TradeProcessorService`.
- **PostTrackingEngine / CopyTradingEngineService**: Maintains position ledgers and decides when to open/close.
- **MarketOrderExecutionService**: Executes buy/sell orders on the CLOB.
- **OrderAnalysisWorker**: Reconciles placed orders with actual CLOB trades.
- **NotificationService**: Sends events to console and optionally to Telegram.

## Security

- **Do not share your `.env`** or commit it to repositories. `.env` is typically in `.gitignore`.
- Use a dedicated wallet with limited funds for copy trading.
- Polymarket credentials allow trading on your account: protect them.
