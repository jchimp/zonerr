FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends bind9-dnsutils bind9-utils bind9-host && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data /var/cache/bind

EXPOSE 5000

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "run:app"]
