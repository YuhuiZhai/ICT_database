import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_mail import Mail
from itsdangerous import URLSafeTimedSerializer

db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()


def _normalize_database_url(url: str) -> str:
    # Some platforms give postgres://... but SQLAlchemy wants postgresql://...
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    # -------------------------
    # Config (AWS-friendly)
    # -------------------------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

    db_url = os.environ.get("DATABASE_URL", "sqlite:///vehicle_request_form.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_database_url(db_url)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    app.config.update(
        # MAIL_SERVER=os.environ.get("MAIL_SERVER", "smtp.gmail.com"),
        # MAIL_PORT=int(os.environ.get("MAIL_PORT", "587")),
        # MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "true").lower() == "true",
        MAIL_SERVER=os.environ.get("MAIL_SERVER", "email-smtp.us-east-1.amazonaws.com"),
        MAIL_PORT=int(os.environ.get("MAIL_PORT", "587")),
        MAIL_USE_TLS=os.environ.get("MAIL_USE_TLS", "true").lower() == "true",
        MAIL_USERNAME=os.environ.get("MAIL_USERNAME"),
        MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.environ.get(
            "MAIL_DEFAULT_SENDER", os.environ.get("MAIL_USERNAME")
        ),
    )

    # -------------------------
    # Init extensions
    # -------------------------
    db.init_app(app)
    mail.init_app(app)

    login_manager.init_app(app)
    # IMPORTANT: blueprint endpoint name
    login_manager.login_view = "user.user_login"

    # Serializer accessible via current_app.config["SERIALIZER"] in routes
    app.config["SERIALIZER"] = URLSafeTimedSerializer(app.config["SECRET_KEY"])

    # -------------------------
    # Template filters
    # -------------------------
    from .utils import register_template_filters
    register_template_filters(app)

    # -------------------------
    # Models + user_loader
    # -------------------------
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # -------------------------
    # Register blueprints
    # -------------------------
    from .routes_user import bp as user_bp
    from .routes_admin import bp as auth_bp
    app.register_blueprint(user_bp)
    app.register_blueprint(auth_bp)

    # -------------------------
    # Flask-Admin setup
    # -------------------------
    from .admin_views import init_admin
    init_admin(app)

    # -------------------------
    # Create tables + optional bootstrap admin
    # -------------------------
    with app.app_context():
        db.create_all()
        _maybe_bootstrap_admin()

    return app


def _maybe_bootstrap_admin():
    """
    Optional: create a default admin account if env vars are set.
    """
    from werkzeug.security import generate_password_hash
    from .models import AdminAccount

    username = os.environ.get("ADMIN_BOOTSTRAP_USERNAME")
    password = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    if not username or not password:
        return

    if AdminAccount.query.filter_by(username=username).first():
        return

    acc = AdminAccount(
        username=username,
        password_hash=generate_password_hash(password, method="pbkdf2:sha256"),
    )
    db.session.add(acc)
    db.session.commit()
