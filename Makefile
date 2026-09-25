PY ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: setup demo api web eval eval-dev reports fixtures test test-backend test-frontend clean-db

setup:            ## Install backend and frontend dependencies
	python3 -m venv .venv
	$(PIP) install -q -r backend/requirements-dev.txt
	cd frontend && npm ci

demo: ## Build the UI and serve everything on http://localhost:8000 (fixture mode without a key)
	cd frontend && npm run build
	cd backend && ../$(PY) -m uvicorn app.main:app --port 8000

api:              ## Backend only, with reload (pair with `make web`)
	cd backend && ../$(PY) -m uvicorn app.main:app --reload --port 8000

web:              ## Vite dev server on http://localhost:5173, proxying /api to :8000
	cd frontend && npm run dev

eval:             ## Live evaluation on all 60 cases (needs ANTHROPIC_API_KEY); creates a new run
	cd backend && ../$(PY) -m app.evaluation --mode live --split all
	$(MAKE) reports

eval-dev:         ## Live evaluation on the 15 development cases only (use this while tuning)
	cd backend && ../$(PY) -m app.evaluation --mode live --split development

reports:          ## Regenerate docs/evaluation_report.md and docs/decision_memo.md from saved runs
	cd backend && ../$(PY) -m app.reports

fixtures:         ## Rebuild the saved example responses used in fixture mode
	$(PY) scripts/build_fixtures.py

test: test-backend test-frontend

test-backend:
	cd backend && ../$(PY) -m pytest

test-frontend:
	cd frontend && npx vitest run && npx tsc -b

clean-db:         ## Delete the local SQLite database (runs are re-seeded on next start)
	rm -f results/lab.sqlite3
