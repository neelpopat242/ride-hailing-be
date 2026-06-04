from flask import Flask

from app.config import Config
from app.db import init_db
from app.redis_client import init_redis
from app.urls import register_blueprints
from app.utils.error_handlers import register_error_handlers


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    init_db(app)
    init_redis(app)
    register_blueprints(app)
    register_error_handlers(app)

    @app.get("/health")
    def health():
        return {"status": "ok"}, 200

    return app
