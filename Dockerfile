FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir requests pandas pyarrow matplotlib streamlit

COPY src/ ./src/
COPY app.py ./
COPY data/processed/ ./data/processed/

ENV PYTHONPATH=/app/src

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
