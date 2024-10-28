from datetime import datetime
from app import db

class Recommendation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    requirements = db.Column(db.Text, nullable=False)
    recommendations = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    rating = db.Column(db.Integer)
    feedback = db.Column(db.Text)
