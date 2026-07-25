API ?= http://127.0.0.1:8000/api/v1
ADMIN_TOKEN ?= change-me
PROJECT_DIR := $(notdir $(CURDIR))

.PHONY: setup setup-h5 dev demo-seed tutorial-build reference-build accept up down logs test test-h5 lint content-check video-smoke zip

setup:
	uv venv --python 3.11 .venv
	uv pip install --python .venv/bin/python -r backend/requirements-dev.txt

setup-h5:
	npm ci
	npx playwright install chromium

dev:
	mkdir -p data
	DATA_DIR="$(CURDIR)/data" H5_DIR="$(CURDIR)/h5" FEED_DIR="$(CURDIR)/data/feeds" SEED_FEED_DIR="$(CURDIR)/assets/samples/open_sources" SEED_REFERENCE_DIR="$(CURDIR)/assets/references" TUTORIAL_ASSETS_DIR="$(CURDIR)/assets/tutorials" ALLOW_INSECURE_ADMIN_TOKEN=true PUBLIC_BASE_URL="http://localhost:8000" \
		.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

demo-seed:
	.venv/bin/python scripts/download_open_samples.py
	.venv/bin/python scripts/import_feed.py assets/samples/open_sources/爱你.MP4 --api "$(API)" --token "$(ADMIN_TOKEN)" --id groove_step --name 爱你 --pause-at 10 --focus upper
	.venv/bin/python scripts/import_feed.py assets/samples/open_sources/科目三.MP4 --api "$(API)" --token "$(ADMIN_TOKEN)" --id arm_wave --name 科目三 --pause-at 14 --focus lower
	.venv/bin/python scripts/import_feed.py assets/samples/open_sources/摇一摇.MP4 --api "$(API)" --token "$(ADMIN_TOKEN)" --id cross_step --name 摇一摇 --pause-at 7 --focus auto
	.venv/bin/python scripts/import_feed.py assets/samples/open_sources/jumpstyle.MP4 --api "$(API)" --token "$(ADMIN_TOKEN)" --id two_step_demo --name Jumpstyle --pause-at 8 --focus lower

tutorial-build:
	.venv/bin/python scripts/build_tutorial_assets.py

reference-build:
	.venv/bin/python scripts/build_reference_assets.py

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

content-check:
	.venv/bin/python scripts/validate_content_matrix.py

video-smoke:
	.venv/bin/python scripts/video_sample_smoke_test.py

zip:
	cd .. && zip -r BeatDance.zip "$(PROJECT_DIR)" -x '*/__pycache__/*' '*.pyc' '.env'

prepare-data:
	python scripts/prepare_dataset.py --samples 2

evaluate:
	python scripts/evaluate_dataset.py --api http://localhost:8000/api/v1 --dir assets/evaluation --output evaluation.csv

calibrate:
	python scripts/calibrate_diagnosis.py evaluation.csv --output diagnosis-calibration.json
