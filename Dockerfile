FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc files and buffer stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose web health port for cloud provider
EXPOSE 10000

# Run unified master orchestrator
CMD ["python", "copiloto_maestro_runner.py"]
