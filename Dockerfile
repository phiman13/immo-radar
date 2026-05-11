FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    NODE_VERSION=20

# Install Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

# Install Python dependencies
COPY pyproject.toml /app/
RUN pip install --no-cache-dir \
    fastapi==0.115.6 "uvicorn[standard]==0.32.1" jinja2==3.1.4 httpx==0.28.1 \
    beautifulsoup4==4.12.3 lxml==5.3.0 playwright==1.49.0 sqlalchemy==2.0.36 \
    pydantic==2.10.4 pydantic-settings==2.7.0 apscheduler==3.10.4 \
    python-telegram-bot==21.6 anthropic==0.40.0 feedparser==6.0.11 \
    python-multipart==0.0.20 tenacity==9.0.0 structlog==24.4.0 geopy==2.4.1

# Build frontend
COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN cd /app/frontend && npm ci --prefer-offline

COPY frontend /app/frontend
RUN cd /app/frontend && npm run build
# Output goes to /app/app/web/static/dist/ (vite.config.ts outDir: '../app/web/static/dist')

# Copy app code
COPY app /app/app
COPY scripts /app/scripts

VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "-m", "app.main"]
