FROM python:3.11-slim
WORKDIR /app
RUN pip install google-cloud-storage google-cloud-pubsub supabase requests
COPY 11translate.py .
CMD ["python", "11translate.py"]
