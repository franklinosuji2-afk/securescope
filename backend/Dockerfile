FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
# System libraries and a font that the PDF report renderer (WeasyPrint) needs. Nothing else is installed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN useradd --system --uid 10001 --no-create-home securescope
USER 10001
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/v1/ready' % __import__('os').environ.get('PORT', '8000'), timeout=2).status==200 else 1)"
# Apply migrations, then serve. Fails fast (container exits) if the database is unreachable.
CMD ["sh", "-c", "python -m app.database.migrate && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
