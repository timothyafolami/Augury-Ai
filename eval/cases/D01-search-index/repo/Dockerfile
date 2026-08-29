FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# One worker. The search path is CPU-bound on token verification, so a second
# worker would only double the number of cores it can saturate.
CMD ["uvicorn", "app.api.handlers:app", "--workers", "1", "--host", "0.0.0.0"]
