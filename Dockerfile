FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY data/demo ./data/demo
COPY data/calendar ./data/calendar
COPY data/display ./data/display
# TerminalService initializes its research store even in the DEMO runtime.
RUN mkdir -p /app/var /app/data/research/phase5 \
    && chown -R 10001:10001 /app/var /app/data/research
USER 10001:10001
ENV DATABASE_URL=sqlite:////app/var/parity-pulse.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "app.main:create_app", "--factory", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
