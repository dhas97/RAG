# ---------------------------------------------------------------------------
# Backend Dockerfile — builds the Django + Gunicorn API server.
#
# WHY python:3.11-slim?
#   The slim variant strips documentation and test files from the base image,
#   keeping the final image smaller. We don't need those extras at runtime.
# ---------------------------------------------------------------------------
FROM python:3.11-slim

# All subsequent commands run from /app inside the container.
WORKDIR /app

# libpq-dev is the C header/library required by psycopg2 (PostgreSQL adapter).
# Even though we use SQLite in development, keeping it here means the image
# is ready to switch to Postgres without rebuilding from scratch.
# --no-install-recommends prevents apt from pulling in unneeded packages.
# Cleaning the apt cache in the same layer keeps the image size small.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first, before copying the rest of the source code.
# Docker caches each layer; installing dependencies in a separate layer means
# that as long as requirements.txt hasn't changed, this expensive step is
# skipped on rebuilds and only the changed source code layer is re-built.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the Django project into the container.
COPY . .

# Document that the app listens on port 8000 (does not actually publish it;
# that is done in docker-compose.yml with the ports mapping).
EXPOSE 8000

# WHY migrate before starting gunicorn?
#   Running migrations here ensures the SQLite database schema is always
#   up to date when the container starts, with no manual step required.
#
# WHY gunicorn instead of Django's built-in runserver?
#   runserver is single-threaded and not designed for production traffic.
#   Gunicorn forks multiple worker processes so the app can handle concurrent
#   requests.
#
# --workers 2     : two worker processes (suits a low-traffic / single-CPU host)
# --timeout 300   : allow up to 5 min per request — needed because uploading a
#                   large PDF and generating embeddings can take a long time.
# --capture-output: route print() / logging output to the Docker log stream.
CMD ["sh", "-c", "python manage.py migrate && gunicorn rag_assistant.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 300 --log-level debug --capture-output"]
