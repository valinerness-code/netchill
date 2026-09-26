# Use an official, lightweight Python base image
FROM python:3.11-slim
WORKDIR /app

# Bypasses requirements.txt completely for multi-module communication
RUN pip install --no-cache-dir "streamlit>=1.37.0" "requests>=2.31.0"

COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
