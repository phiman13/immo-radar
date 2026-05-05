FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY pyproject.toml /app/
RUN pip install --no-cache-dir \
    fastapi==0.115.6 "uvicorn[standard]==0.32.1" jinja2==3.1.4 httpx==0.28.1 \
    beautifulsoup4==4.12.3 lxml==5.3.0 playwright==1.49.0 sqlalchemy==2.0.36 \
    pydantic==2.10.4 pydantic-settings==2.7.0 apscheduler==3.10.4 \
    python-telegram-bot==21.6 anthropic==0.40.0 feedparser==6.0.11 \
    python-multipart==0.0.20 tenacity==9.0.0 structlog==24.4.0 geopy==2.4.1

COPY app /app/app
COPY scripts /app/scripts

VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "-m", "app.main"]
