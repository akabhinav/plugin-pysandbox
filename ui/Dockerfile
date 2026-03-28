FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir streamlit httpx

COPY app.py .

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -sf http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
