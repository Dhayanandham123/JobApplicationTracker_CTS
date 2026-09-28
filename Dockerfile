FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Cloud Run sends traffic to $PORT
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 120 app:app
