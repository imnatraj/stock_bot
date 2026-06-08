# stock_bot — Swing Trading Assistant (Phase 1)

This repository contains the scaffold and package layout for a production-ready automated swing trading assistant targeting Indian equities.

Phase 1 (this commit):
- Project folder structure
- Minimal package modules (importable)
- Basic scripts, Docker stubs, and a placeholder test

Next step: generate `requirements.txt` and pin verified dependency versions (Phase 2).

## Run locally

1. Create and activate a Python 3.12+ virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

2. Install pinned dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

3. Run the package (make imports resolvable by adding `src` to `PYTHONPATH`):

```bash
export PYTHONPATH=./src
python -m stock_bot
```

4. Run tests:

```bash
export PYTHONPATH=./src
pytest -q
```

If you prefer Docker, `docker-compose.yml` is provided; the `Dockerfile` installs `requirements.txt` and sets `PYTHONPATH` so `python -m stock_bot` runs inside the container.

Environment variables / .env
-----------------------------

Create a `.env` file in the project root for local development by copying
`.env.example` and filling in real credentials. The application will attempt to
auto-load `.env` via `python-dotenv` when running locally. The project already
includes `.env` in `.gitignore` to avoid accidental commits.

```bash
cp .env.example .env
# edit .env and fill secrets
```

**Developer Guide — Phase Commands**

- **Setup environment:** Create a virtualenv, activate it, and install pinned deps.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

- **Load environment:** create `.env` and export for the session.

```bash
cp .env.example .env
export $(grep -v '^#' .env | xargs)
export PYTHONPATH=./src
```

- **Phase 4 — Database (Alembic migrations):** create DB (if needed) and run migrations.

```bash
# create database if missing (uses MYSQL_* env vars)
.venv/bin/python -c "import os,pymysql; c=pymysql.connect(host=os.getenv('MYSQL_HOST'),port=int(os.getenv('MYSQL_PORT',3306)),user=os.getenv('MYSQL_USER'),password=os.getenv('MYSQL_PASSWORD')); c.autocommit(True); cur=c.cursor(); cur.execute(f\"CREATE DATABASE IF NOT EXISTS `{os.getenv('MYSQL_DATABASE','stock_bot')}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\"); cur.close(); c.close()"

# run alembic migrations
.venv/bin/alembic upgrade head
```

- **Phase 1 & 5 — Run scanner + Telegram alerts:**

```bash
export SAMPLE_SYMBOLS="RELIANCE.NS,TCS.NS,INFY.NS"
export PYTHONPATH=./src
python -m stock_bot.scanner.cli
# or use helper
./scripts/run_scanner.sh
```

- **Phase 6 — Backtest (quick run):**

```bash
export PYTHONPATH=./src
python -c "from stock_bot.backtest.simple import run_backtest; from stock_bot.integrations.csv_loader import load_signals_from_csv; s=load_signals_from_csv('examples/google_sheet_sample.csv'); print(run_backtest(s))"
```

- **Phase 2 — Record a trade (portfolio service):**

```bash
export PYTHONPATH=./src
python - <<'PY'
from stock_bot.services.portfolio_service import record_trade
print(record_trade('RELIANCE.NS','buy',1,1520.0))
PY
```

- **Phase 3 — Ranking engine (V3):**

```bash
export PYTHONPATH=./src
python - <<'PY'
from stock_bot.ranking.engine import rank_symbols
print(rank_symbols(['RELIANCE.NS','INFY.NS','TCS.NS']))
PY
```

- **Phase 4/ V4 — AI explainer (local fallback):**

```bash
export PYTHONPATH=./src
python - <<'PY'
from stock_bot.ai.assistant import explain_ranking
print(explain_ranking('RELIANCE.NS', {'r6':12.3,'r3':5.2,'dist52':8.5,'vol':120000}))
PY
```

- **Run tests:**

```bash
export PYTHONPATH=./src
pytest -q
```

- **Docker (build & run):**

```bash
docker compose build
docker compose up --build
```

Key implementation files

- Database engine: [src/stock_bot/db/engine.py](src/stock_bot/db/engine.py#L1)
- SQLAlchemy models: [src/stock_bot/db/models.py](src/stock_bot/db/models.py#L1)
- Scanner: [src/stock_bot/scanner/scanner.py](src/stock_bot/scanner/scanner.py#L1)
- Scanner CLI: [src/stock_bot/scanner/cli.py](src/stock_bot/scanner/cli.py#L1)
- Telegram integration: [src/stock_bot/integrations/telegram.py](src/stock_bot/integrations/telegram.py#L1)
- CSV/Sheets loaders: [src/stock_bot/integrations/csv_loader.py](src/stock_bot/integrations/csv_loader.py#L1), [src/stock_bot/integrations/google_sheets.py](src/stock_bot/integrations/google_sheets.py#L1)
- Backtest: [src/stock_bot/backtest/simple.py](src/stock_bot/backtest/simple.py#L1)
- Portfolio service: [src/stock_bot/services/portfolio_service.py](src/stock_bot/services/portfolio_service.py#L1)

