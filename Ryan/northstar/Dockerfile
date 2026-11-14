# Build from the REPO ROOT so the image contains Minh/converter/ and api/ as well:
#   docker compose -f Ryan/northstar/docker-compose.yml up --build
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY . /repo
RUN pip install --no-cache-dir -r Ryan/northstar/requirements.txt \
 && if [ -f Minh/converter/requirements.txt ]; then pip install --no-cache-dir -r Minh/converter/requirements.txt; fi
WORKDIR /repo/Ryan/northstar
ENV NORTHSTAR_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8100
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
