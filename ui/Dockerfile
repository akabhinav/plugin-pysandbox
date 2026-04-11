FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir streamlit httpx

# Copy every Python module in ui/ so new feature files (e.g. features.py)
# are picked up without having to edit the Dockerfile each time one is
# added. `app.py` imports from `features` at startup, so omitting any
# file here crashes the container on first load.
COPY *.py .

EXPOSE 8501

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD curl -sf http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
