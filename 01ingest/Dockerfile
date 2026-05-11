FROM python:3.11-slim
WORKDIR /app
RUN pip install google-cloud-storage google-cloud-pubsub supabase requests
COPY 01ingest.py .
CMD ["python", "01ingest.py"]
