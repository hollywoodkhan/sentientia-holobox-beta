FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY main.py retrieval.py knowledge_store.py tenant_store.py event_knowledge.json ./

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080
CMD ["python", "main.py"]
