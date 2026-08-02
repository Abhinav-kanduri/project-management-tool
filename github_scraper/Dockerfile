services:
  github-summary-api:
    build: .
    container_name: github-repository-summary-api
    env_file:
      - .env
    ports:
      - "8000:8000"
    volumes:
      - summary-cache:/app/.cache
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

volumes:
  summary-cache:
