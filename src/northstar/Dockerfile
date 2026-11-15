# Build from the top of the repository so the image contains all of src/ (converter, api, monitors, web):
#   docker compose -f src/northstar/docker-compose.yml up --build
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY . /repo
RUN pip install --no-cache-dir -r src/northstar/requirements.txt -r src/converter/requirements.txt
WORKDIR /repo/src/northstar
ENV NORTHSTAR_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8100
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
