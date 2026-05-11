FROM python:3.11-slim
WORKDIR /app
RUN pip install google-cloud-storage google-cloud-pubsub supabase requests
COPY 04names.py .
CMD ["python", "04names.py"]
