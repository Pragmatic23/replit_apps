import os
import time
from flask import Flask, request
from extensions import db, login_manager
from models import User, Recommendation, UserSession
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import redis
from redis.exceptions import ConnectionError as RedisConnectionError
import logging
from icon_cache import icon_cache

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Enable compression
    Compress(app)
    
    # Configure Redis with fallback and retry
    redis_client = None
    redis_connected = False
    
    for _ in range(3):  # Try 3 times
        try:
            redis_url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379")
            redis_client = redis.from_url(redis_url)
            redis_client.ping()
            redis_connected = True
            
            # Initialize icon cache with Redis
            icon_cache.initialize_redis()
            
            # Configure rate limiting with Redis
            limiter = Limiter(
                app=app,
                key_func=get_remote_address,
                default_limits=["200 per day", "50 per hour"],
                storage_uri=redis_url
            )
            logger.info("Rate limiting and icon caching enabled with Redis storage")
            break
        except (RedisConnectionError, OSError) as e:
            logger.warning(f"Redis connection attempt failed: {str(e)}")
            time.sleep(1)
    
    if not redis_connected:
        logger.warning("Redis unavailable after retries. Using in-memory storage for rate limiting")
        # Fallback to in-memory storage
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"],
            storage_uri="memory://"
        )
    
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
    
    # Configure caching headers for static files
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year
    app.config['STATIC_FOLDER'] = 'static'
    
    @app.after_request
    def add_cache_headers(response):
        if 'static' in request.path:
            # Cache static files (including icons) for 1 hour
            response.cache_control.max_age = 3600
            response.cache_control.public = True
        return response
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
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
