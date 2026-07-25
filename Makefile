.PHONY: up down logs test lint zip

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check app tests

zip:
	cd .. && zip -r dingge-coach.zip dingge-coach -x '*/__pycache__/*' '*.pyc' '.env'

prepare-data:
	python scripts/prepare_dataset.py --samples 2

evaluate:
	python scripts/evaluate_dataset.py --api http://localhost:8000/api/v1 --dir assets/evaluation --output evaluation.csv

calibrate:
	python scripts/calibrate_diagnosis.py evaluation.csv --output diagnosis-calibration.json
