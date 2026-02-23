# Use official Python image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements from root to backend
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend/ /app/backend/

# Set environment variables
ENV PYTHONPATH=/app/backend
ENV PORT=8000

# Expose the port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
