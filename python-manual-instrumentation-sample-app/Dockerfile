FROM python:3.8.9

WORKDIR /app

COPY . .

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

ENV OTEL_EXPORTER_OTLP_ENDPOINT="http://10.0.11.176:4317"

ENTRYPOINT python app.py
