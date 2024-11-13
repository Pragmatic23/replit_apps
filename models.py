from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False)
    bio = db.Column(db.Text)
    company = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add relationship to sessions with lazy loading
    sessions = relationship('UserSession', backref='user', lazy='select')
    
    # Add relationship to recommendations with lazy loading
    recommendations = relationship('Recommendation', backref='user', lazy='select')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Recommendation(db.Model):
    __tablename__ = 'recommendation'
    
    id = db.Column(db.Integer, primary_key=True)
    requirements = db.Column(db.Text, nullable=False)
    recommendations = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    module_urls = db.Column(JSON)
    module_images = db.Column(JSON)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    session_id = db.Column(db.Integer, db.ForeignKey('user_session.id'), index=True)
    
    # Add composite index for faster querying
    __table_args__ = (
        db.Index('idx_recommendation_user_created', 'user_id', 'created_at'),
    )

class UserSession(db.Model):
    __tablename__ = 'user_session'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    session_start = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    session_end = db.Column(db.DateTime)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Add relationship with cascade delete
    recommendations = relationship('Recommendation', backref='session', lazy='select', cascade='all, delete-orphan')
    
    # Add composite index for faster querying
    __table_args__ = (
        db.Index('idx_session_user_end', 'user_id', 'session_end'),
    )
