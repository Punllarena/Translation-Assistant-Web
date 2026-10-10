FROM python:3.12-slim

WORKDIR /app
# Source must be present before install: setuptools discovers api*/tools* at install time.
COPY pyproject.toml alembic.ini ./
COPY api ./api
COPY migrations ./migrations
COPY tools ./tools
RUN pip install --no-cache-dir .

EXPOSE 8000
# --proxy-headers so the login rate limiter sees real client addresses behind a reverse proxy.
CMD ["sh", "-c", "alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
