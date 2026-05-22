# Zonerr

A simple lightweight internal DNS server with a simple web interface for BIND management. Perfect for hosting internal DNS for homelabs.
Built with Python/Flask and Bootstrap 5.

## Features

- **Zone Management** - Create, edit, and delete forward and reverse DNS zones
- **Record Management** - Full CRUD for A, AAAA, CNAME, TXT, SRV, MX, NS, and PTR records
- **Auto-PTR** - Optionally create matching PTR records when adding A records
- **SOA Management** - Auto-incrementing serial numbers (YYYYMMDDNN format)
- **Dark/Light Theme** - Toggle with persistent localStorage preference
- **Simple Auth** - Password configured via environment variables
- **Replication** - Simple master/slave configuration
- **BIND Status** - View rndc status directly in the UI
- **Docker Ready** - Two modes: full stack or app-only

## Quick Start

### Option 1: Full Stack (App + BIND Container)

```bash
cp .env.example .env
# Edit .env with your admin password and secret key
docker compose up -d --build
# Open http://localhost:5000
```

### Option 2: Local BIND (App Container Only)

```bash
cp .env.example .env
docker compose -f docker-compose.local.yml up -d --build
```

### Option 3: Development (No Docker)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export $(cat .env | xargs)
python run.py
```

### Environment Variables

| Variable              | Default                    | Description           |
| --------------------- | -------------------------- | --------------------- |
| FLASK_SECRET_KEY      | dev-secret-key             | Flask session secret  |
| ADMIN_USERNAME        | admin                      | Login username        |
| ADMIN_PASSWORD        | changeme                   | Login password        |
| BIND_ZONE_DIR         | /etc/bind/zones            | Zone file directory   |
| BIND_NAMED_CONF_LOCAL | /etc/bind/named.conf.local | named.conf.local path |
| RNDC_HOST             | 127.0.0.1                  | BIND server address   |
| RNDC_PORT             | 953                        | rndc port             |