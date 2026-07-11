FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

# Bake the ONNX embedding model into the image so semantic/hybrid search works on a
# from-scratch build without relying on an out-of-repo build command. ~23 MB, one-time.
RUN python -m app.ml.download

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
