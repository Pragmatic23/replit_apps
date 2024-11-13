import os
from flask import Flask
from extensions import db, login_manager
from models import User
from flask_compress import Compress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Enable compression with optimized settings
    compress = Compress()
    compress.init_app(app)
    app.config['COMPRESS_ALGORITHM'] = 'gzip'
    app.config['COMPRESS_LEVEL'] = 6
    app.config['COMPRESS_MIN_SIZE'] = 500
    
    # Performance optimizations
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year
    app.config['TEMPLATES_AUTO_RELOAD'] = False  # Disable in production
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=31)
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    
    # Configure rate limiting with memory storage
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))
    
    # Configure database with optimized connection pooling
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///odoo_recommender.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 5,  # Reduced for better resource utilization
        "max_overflow": 10,
        "pool_timeout": 20,
        "pool_recycle": 1800,  # Recycle connections every 30 minutes
        "pool_pre_ping": True  # Enable connection health checks
    }
    
    # Disable SQLAlchemy event system and modification tracking
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
    
    # Import and register routes
    from routes import register_routes
    app = register_routes(app)
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app

app = create_app()

if __name__ == "__main__":
    # Set up server with optimized settings
    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True,
        use_reloader=False  # Disable reloader in production
    )