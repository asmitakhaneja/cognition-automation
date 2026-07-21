.PHONY: install build backend dev clean test lint fmt docker

# One-shot setup: backend venv + frontend deps + production frontend build.
install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
	cd frontend && npm install

build:
	cd frontend && npm run build

# Run the production server (serves the built frontend + API) on :8000.
backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

# Full production run: build frontend, then serve everything from the backend.
run: build backend

# Frontend dev server with hot reload on :5173 (proxies /api to :8000).
dev:
	cd frontend && npm run dev

# Backend test suite.
test:
	cd backend && . .venv/bin/activate && python -m pytest -q

# PEP8: check formatting + lint.
lint:
	cd backend && . .venv/bin/activate && black --check app tests && flake8 app tests

# Auto-format Python.
fmt:
	cd backend && . .venv/bin/activate && black app tests

# Build the combined production image (frontend + backend).
docker:
	docker build -t devin-observability-dashboard .

clean:
	rm -rf frontend/dist frontend/node_modules backend/.venv
