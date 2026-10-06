# Official, lightweight Python base image (same Python version the CI checks use)
FROM python:3.12-slim
WORKDIR /app

# Python prints straight to the logs; pip stays quiet and leaves no cache behind
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Exact versions (see requirements.txt) so a rebuild can't silently pull in a newer,
# breaking Streamlit release. To upgrade, change the numbers there on purpose.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Run as an unprivileged user instead of root
RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
USER appuser

EXPOSE 8501
# Listens on Render's PORT (render.yaml sets 8501); falls back to 8501 when PORT is unset
CMD ["sh", "-c", "exec streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
