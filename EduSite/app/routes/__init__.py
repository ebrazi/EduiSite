from .public import bp as public_bp
from .auth import bp as auth_bp
from .user import bp as user_bp
from .admin import bp as admin_bp
from .user import payment_callback
from . import mockgw


def register_blueprints(app):
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)
    if app.config["DEV_MODE"]:
        app.register_blueprint(mockgw.bp)
    # Payment callback always exists; the verifying gateway is swappable.
    app.add_url_rule(
        "/payment/callback", "payment_callback", payment_callback, methods=["GET"]
    )
