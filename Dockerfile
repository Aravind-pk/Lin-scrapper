FROM python:3.12-slim

# Cloud Run streams stdout; unbuffered keeps logs live rather than batched.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Nothing here needs root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

# Cloud Run injects PORT and ignores EXPOSE; the default is for local runs.
ENV PORT=8080
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
