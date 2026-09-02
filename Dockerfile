FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir requests pandas matplotlib streamlit

COPY src/ ./src/
COPY app.py ./
COPY scripts/ ./scripts/

ENV PYTHONPATH=/app/src

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
