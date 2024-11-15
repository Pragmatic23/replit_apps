import os
from flask import Flask
from extensions import db, login_manager
from models import User, Recommendation, UserSession
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from redis.exceptions import ConnectionError as RedisConnectionError
import logging

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Enable compression
    Compress(app)
    
    # Configure Redis with fallback
    try:
        redis_client = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
        redis_client.ping()  # Test connection
        
        # Configure rate limiting with Redis
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"],
            storage_uri=os.environ.get("REDIS_URL", "redis://localhost:6379")
        )
        logger.info("Rate limiting enabled with Redis storage")
    except RedisConnectionError:
        # Fallback to in-memory storage if Redis is not available
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"],
            storage_uri="memory://"
        )
        logger.warning("Redis unavailable. Using in-memory storage for rate limiting")
    
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "odoo-recommender-secret-key"
    
    # Configure database with optimized settings
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///odoo_recommender.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 10,
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "max_overflow": 20,
        "pool_timeout": 30,
        "echo": False,
        "max_identifier_length": 63
    }
    
    # Additional performance configurations
    app.config['TEMPLATES_AUTO_RELOAD'] = False
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        # Use Session.get() instead of Query.get()
        return db.session.get(User, int(user_id))
    
    # Import and register routes
    from routes import register_routes
    register_routes(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
