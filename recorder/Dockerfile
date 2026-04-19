FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY recorder.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "recorder.py"]
