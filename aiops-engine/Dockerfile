FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline.py .
COPY model_monitor.py .

# Create data and models directories
RUN mkdir -p /data /app/models

# Copy pre-trained model into image (populated at build time)
COPY models/ /app/models/

EXPOSE 8000

CMD ["python", "pipeline.py"]
