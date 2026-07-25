FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY backend/app /app/app
COPY h5 /app/h5
RUN mkdir -p /app/assets/samples/open_sources
COPY assets/tutorials /app/assets/tutorials
COPY assets/samples/open_sources/six_step_tutorial.mp4 /app/assets/samples/open_sources/
COPY assets/samples/open_sources/arm_movements_veil.mp4 /app/assets/samples/open_sources/
COPY assets/samples/open_sources/tendu_tutorial.mp4 /app/assets/samples/open_sources/
COPY assets/samples/open_sources/ATTRIBUTION.md /app/assets/samples/open_sources/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
