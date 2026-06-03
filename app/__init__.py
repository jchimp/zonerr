import logging
import os

from flask import Flask, request
from flask_wtf.csrf import CSRFProtect

logger = logging.getLogger(__name__)

_INSECURE_SECRET_KEY = "dev-secret-key"
_INSECURE_PASSWORD_HASH = "pbkdf2:sha256:260000$changeme"

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", _INSECURE_SECRET_KEY),
        ADMIN_USERNAME=os.environ.get("ADMIN_USERNAME", "admin"),
        ADMIN_PASSWORD_HASH=os.environ.get("ADMIN_PASSWORD_HASH", ""),
        BIND_ZONE_DIR=os.environ.get("BIND_ZONE_DIR", "/etc/bind/zones"),
        BIND_NAMED_CONF_LOCAL=os.environ.get("BIND_NAMED_CONF_LOCAL", "/etc/bind/named.conf.local"),
        BIND_LOG_DIR=os.environ.get("BIND_LOG_DIR", "/var/log/bind"),
        RNDC_PATH=os.environ.get("RNDC_PATH", "/usr/sbin/rndc"),
        RNDC_KEY=os.environ.get("RNDC_KEY", ""),
        RNDC_HOST=os.environ.get("RNDC_HOST", "127.0.0.1"),
        RNDC_PORT=int(os.environ.get("RNDC_PORT", 953)),
        REPLICATION_CONFIG=os.environ.get("REPLICATION_CONFIG", "/data/replication.json"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # SESSION_COOKIE_SECURE=True  # enable when serving over HTTPS
    )

    if app.config["SECRET_KEY"] == _INSECURE_SECRET_KEY:
        logger.warning("FLASK_SECRET_KEY is not set — using insecure default. Set it in .env.")
    if not app.config["ADMIN_PASSWORD_HASH"]:
        logger.warning(
            "ADMIN_PASSWORD_HASH is not set. "
            "Generate one with: python -c \"from werkzeug.security import "
            "generate_password_hash; print(generate_password_hash('yourpassword'))\""
        )

    csrf.init_app(app)

    os.makedirs(app.config["BIND_ZONE_DIR"], exist_ok=True)

    from app.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.zones import zones_bp
    from app.routes.records import records_bp
    from app.routes.settings import settings_bp
    from app.routes.tools import tools_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(zones_bp, url_prefix="/zones")
    app.register_blueprint(records_bp, url_prefix="/records")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(tools_bp, url_prefix="/tools")

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    return app