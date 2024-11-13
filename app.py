import os
from flask import Flask
from extensions import db, login_manager
from models import User, Recommendation, UserSession
from flask_compress import Compress

def create_app():
    app = Flask(__name__)
    
    # Enable compression
    Compress(app)
    
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "odoo-recommender-secret-key"
    
    # Configure database with optimized settings
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///odoo_recommender.db")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_size": 10,  # Maximum number of connections
        "pool_recycle": 300,  # Recycle connections after 5 minutes
        "pool_pre_ping": True,  # Test connections before using them
        "max_overflow": 20,  # Allow up to 20 connections beyond pool_size
        "pool_timeout": 30,  # Wait up to 30 seconds for a connection
        "echo": False,  # Disable SQL echo for production
        "max_identifier_length": 63  # PostgreSQL max identifier length
    }
    
    # Additional performance configurations
    app.config['TEMPLATES_AUTO_RELOAD'] = False  # Disable in production
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
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
