FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Dépendances Python d'abord (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code
COPY . .

# Railway injecte $PORT au runtime
ENV PORT=8080
EXPOSE 8080

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
