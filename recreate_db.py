from app import app, db
from models import User, Recommendation, UserSession

def recreate_database():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        
        # Create all tables
        db.create_all()
        
        print("Database tables recreated successfully!")

if __name__ == "__main__":
    recreate_database()
