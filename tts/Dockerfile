FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HF_HOME=/opt/models \
    XDG_CACHE_HOME=/opt/cache \
    NLTK_DATA=/opt/nltk_data

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip wheel "setuptools<81" && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 torchaudio==2.8.0 && \
    pip install --no-cache-dir -r requirements.txt

# Bake the English model and language resources into the image for reliable cold starts.
RUN mkdir -p /opt/models /opt/cache /opt/nltk_data && \
    python -m unidic download && \
    python -c "import nltk; nltk.download('averaged_perceptron_tagger'); nltk.download('averaged_perceptron_tagger_eng'); nltk.download('cmudict')" && \
    python -c "from melo.api import TTS; TTS(language='EN', device='cpu')"

COPY app.py .

RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app /opt/models /opt/cache /opt/nltk_data
USER appuser

CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT} --workers 1
