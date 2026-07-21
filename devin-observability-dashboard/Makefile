.PHONY: install build backend dev clean

# One-shot setup: backend venv + frontend deps + production frontend build.
install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
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

clean:
	rm -rf frontend/dist frontend/node_modules backend/.venv
