"""
settings.py — Django configuration for the RAG assistant backend.

HOW SECRETS ARE MANAGED:
  Sensitive values (GEMINI_API_KEY, SECRET_KEY, etc.) are loaded from a .env
  file via python-dotenv. Never hard-code secrets here; keep them in .env and
  make sure .env is listed in .gitignore so it is never committed to version
  control.

KEY DESIGN DECISIONS:
  - SQLite database: no separate DB server needed; the file lives at
    backend/data/db.sqlite3. Good enough for personal / small-team use.
  - CorsMiddleware placed FIRST: it must run before Django inspects the
    request so that browser preflight (OPTIONS) requests are handled before
    other middleware can reject them.
  - DEBUG and ALLOWED_HOSTS are read from environment variables so the same
    codebase can run both in development (DEBUG=True) and production
    (DEBUG=False) without code changes.
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment variables from a .env file in the project root (if present).
# This must happen before any os.environ.get() calls below.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key secret in production.
# The fallback value is intentionally labelled "insecure" to make it obvious
# that it must be replaced before deploying publicly.
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me-in-production')

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# Comma-separated list of hostnames that this Django app will serve.
# Restricting this prevents HTTP Host header attacks.
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',   # Django REST Framework — provides APIView, serializers, etc.
    'corsheaders',      # Allows the React frontend (different port) to call this API.
    'api',              # Our application: models, views, services.
]

MIDDLEWARE = [
    # CorsMiddleware MUST be first so it can handle browser OPTIONS preflight
    # requests before any other middleware processes the request.
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'rag_assistant.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'rag_assistant.wsgi.application'

# PostgreSQL + pgvector.  All credentials come from environment variables
# so the same settings.py works in development, CI, and production.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "ragdb"),
        "USER": os.environ.get("POSTGRES_USER", "raguser"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "OPTIONS": {
            # Production: use SSL; set to "require" on cloud DBs (RDS, Cloud SQL, etc.)
            "sslmode": os.environ.get("POSTGRES_SSLMODE", "prefer"),
        },
        "CONN_MAX_AGE": 60,  # reuse DB connections for up to 60 s (reduces overhead)
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'uploads'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Browsers block cross-origin fetch() calls unless the server explicitly
# allows the calling origin. The React dev server runs on port 5173 (Vite)
# or 3000, so we allow those origins. In production, replace these with the
# actual deployed frontend URL.
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5173,http://localhost:3000'
).split(',')

REST_FRAMEWORK = {
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',  # needed to receive file uploads
    ]
}

# Read from environment so the key is never committed to version control.
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# Django's in-memory file handling limit. Files larger than this threshold are
# spooled to disk instead of being kept in RAM. The DocumentUploadView enforces
# its own 100 MB hard cap, but these settings prevent excessive RAM use for any
# other form fields that might exist now or in the future.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
