# Teacher-labelling worker image (no model inside; the teacher is reached over HTTP).
FROM python:3.11.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY teacher.py worker.py clean.py ./
USER 1000
CMD ["python", "worker.py"]
