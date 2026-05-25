# Zonerr

A simple lightweight internal DNS server with a simple web interface for BIND management. 
Perfect for hosting internal DNS for homelabs. Built with Python, Flask and Bootstrap 5.

## Features

- **Zone Management** - Create, edit, and delete forward and reverse DNS zones
- **Record Management** - Full management for A, AAAA, CNAME, TXT, SRV, MX, NS, and PTR records
- **Import & Export** - Import and export entire zones via text files.
- **Auto-PTR** - Optionally create matching PTR records when adding A records
- **SOA Management** - Auto-incrementing serial numbers (YYYYMMDDNN format)
- **Replication** - Simple master/slave configuration
- **BIND Status** - View rndc status directly in the UI
- **Query Tool** - Query tool using dig to simple looks ups
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