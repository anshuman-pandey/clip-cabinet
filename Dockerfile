FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . .
RUN mkdir -p /app/data && chown app:app /app/data
USER app
EXPOSE 5120
CMD ["gunicorn", "--bind", "0.0.0.0:5120", "--workers", "2", "--threads", "4", "--timeout", "120", "app:create_app()"]
