FROM python:3.11-slim
WORKDIR /app
RUN pip install google-cloud-storage google-cloud-pubsub supabase requests
COPY 09audio/09audio.py .
CMD ["python", "09audio.py"]
