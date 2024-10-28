from app import app, db
from models import User

def create_admin_user():
    with app.app_context():
        # Check if admin already exists
        admin = User.query.filter_by(email='admin@example.com').first()
        if not admin:
            # Create new admin user
            admin = User()
            admin.username = 'admin'
            admin.email = 'admin@example.com'
            admin.is_admin = True
            admin.set_password('admin123')  # Set a default password
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")
        else:
            print("Admin user already exists!")

if __name__ == "__main__":
    create_admin_user()
