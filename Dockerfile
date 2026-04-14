FROM python:3.14-slim

WORKDIR /app

# Install Flask (only external dependency)
RUN pip install --no-cache-dir flask

# Copy project files — data files are mounted via docker-compose volume
COPY *.py ./
COPY *.html ./
COPY *.css ./
COPY *.js ./
COPY *.yaml ./

EXPOSE 8000

CMD ["python", "server.py"]
