FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY demo_ui ./demo_ui
ENV MODEL_PROVIDER=ollama DATABASE_PATH=/data/tickets.db
RUN mkdir /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
