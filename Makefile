API ?= http://127.0.0.1:8000/api/v1
ADMIN_TOKEN ?= change-me

.PHONY: setup setup-h5 dev demo-seed accept up down logs test test-h5 lint video-smoke zip

setup:
	uv venv --python 3.11 .venv
	uv pip install --python .venv/bin/python -r backend/requirements-dev.txt

setup-h5:
	npm ci
	npx playwright install chromium

dev:
	mkdir -p data
	DATA_DIR="$(CURDIR)/data" H5_DIR="$(CURDIR)/h5" FEED_DIR="$(CURDIR)/data/feeds" SEED_FEED_DIR="$(CURDIR)/assets/samples/open_sources" PUBLIC_BASE_URL="http://localhost:8000" \
		.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

demo-seed:
	.venv/bin/python scripts/download_open_samples.py
	.venv/bin/python scripts/register_reference.py --api "$(API)" --token "$(ADMIN_TOKEN)" --action groove_step --video assets/samples/open_sources/breakdance_6_step.mp4
	.venv/bin/python scripts/register_reference.py --api "$(API)" --token "$(ADMIN_TOKEN)" --action arm_wave --video assets/samples/open_sources/arm_movements_reference.mp4
	.venv/bin/python scripts/register_reference.py --api "$(API)" --token "$(ADMIN_TOKEN)" --action cross_step --video assets/samples/open_sources/tendu_reference.mp4

accept:
	.venv/bin/python scripts/full_flow_acceptance.py --admin-token "$(ADMIN_TOKEN)"
	npm run test:h5

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	.venv/bin/pytest -q backend/tests

test-h5:
	npm run test:h5

lint:
	.venv/bin/ruff check backend/app backend/tests scripts

video-smoke:
	.venv/bin/python scripts/video_sample_smoke_test.py

zip:
	cd .. && zip -r dingge-coach.zip dingge-coach -x '*/__pycache__/*' '*.pyc' '.env'

prepare-data:
	python scripts/prepare_dataset.py --samples 2

evaluate:
	python scripts/evaluate_dataset.py --api http://localhost:8000/api/v1 --dir assets/evaluation --output evaluation.csv

calibrate:
	python scripts/calibrate_diagnosis.py evaluation.csv --output diagnosis-calibration.json
