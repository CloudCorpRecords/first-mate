FROM python:3.12-slim

WORKDIR /app
COPY . /app

# No dependencies to install. First Mate uses the Python standard library only.
ENV FIRST_MATE_HOST=0.0.0.0
ENV FIRST_MATE_PORT=8000
ENV FIRST_MATE_DATA_DIR=/app/data/ship-logs

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"

CMD ["python3", "-m", "first_mate", "serve"]
