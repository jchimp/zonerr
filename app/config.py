import os


class Config:
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
    BIND_ZONE_DIR = os.environ.get("BIND_ZONE_DIR", "/etc/bind/zones")
    BIND_NAMED_CONF_LOCAL = os.environ.get("BIND_NAMED_CONF_LOCAL", "/etc/bind/named.conf.local")
    RNDC_PATH = os.environ.get("RNDC_PATH", "/usr/sbin/rndc")
    RNDC_KEY = os.environ.get("RNDC_KEY", "")
    RNDC_HOST = os.environ.get("RNDC_HOST", "127.0.0.1")
    RNDC_PORT = int(os.environ.get("RNDC_PORT", 953))
    REPLICATION_CONFIG = os.environ.get("REPLICATION_CONFIG", "/data/replication.json")
    