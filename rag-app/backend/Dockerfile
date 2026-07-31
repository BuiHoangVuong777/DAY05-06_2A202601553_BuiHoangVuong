FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models

WORKDIR /srv

# CPU-only torch keeps the image ~2 GB smaller than the default CUDA build.
# Requirements are copied first so this layer caches across code edits.
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image: the container then needs no network
# at run time, so a flaky demo-day connection can't break startup.
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('${EMBEDDING_MODEL}')"

COPY app ./app

# Use the baked cache and never phone home. Without this, sentence-transformers
# still issues cache-validation requests to huggingface.co on every startup —
# which is slow (or fatal) on a bad demo-day network. Changing EMBEDDING_MODEL
# therefore requires `docker compose up --build`, not just an .env edit.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
