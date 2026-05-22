import os
from flask import Flask


def create_app():
    app = Flask(__name__)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-secret-key"),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "changeme"),
        BIND_ZONE_DIR=os.environ.get("BIND_ZONE_DIR", "/etc/bind/zones"),
        BIND_NAMED_CONF_LOCAL=os.environ.get("BIND_NAMED_CONF_LOCAL", "/etc/bind/named.conf.local"),
        BIND_LOG_DIR=os.environ.get("BIND_LOG_DIR", "/var/log/bind"),
        RNDC_PATH=os.environ.get("RNDC_PATH", "/usr/sbin/rndc"),
        RNDC_KEY=os.environ.get("RNDC_KEY", ""),
        RNDC_HOST=os.environ.get("RNDC_HOST", "127.0.0.1"),
        RNDC_PORT=int(os.environ.get("RNDC_PORT", 953)),
        REPLICATION_CONFIG=os.environ.get("REPLICATION_CONFIG", "/data/replication.json"),
    )

    os.makedirs(app.config["BIND_ZONE_DIR"], exist_ok=True)

    from app.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.zones import zones_bp
    from app.routes.records import records_bp
    from app.routes.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(zones_bp, url_prefix="/zones")
    app.register_blueprint(records_bp, url_prefix="/records")
    app.register_blueprint(settings_bp, url_prefix="/settings")

    return app