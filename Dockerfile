FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application code
COPY telegram_bot.py ./
COPY src/ ./src/

# Create volume mount point for database
VOLUME ["/app/data"]

# Set environment variable for database location
ENV DB_FILE=/app/data/bot_data.db

# Run the bot
CMD ["python", "telegram_bot.py"]
