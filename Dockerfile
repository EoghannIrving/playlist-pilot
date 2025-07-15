FROM python:3.12-slim

WORKDIR /app

# Only copy requirements first for caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure necessary dirs exist in image (in case volumes aren't mounted)
RUN mkdir -p playlist_pilot/logs playlist_pilot/cache playlist_pilot/user_data

# Set PYTHONPATH so app imports work
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
