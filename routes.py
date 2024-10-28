from flask import render_template, request, jsonify
from app import app, db
from models import Recommendation
from utils import get_module_recommendations

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_recommendations', methods=['POST'])
def get_recommendations():
    requirements = request.form.get('requirements')
    if not requirements:
        return jsonify({"error": "No requirements provided"}), 400

    recommendations = get_module_recommendations(requirements)
    
    # Store in database
    rec = Recommendation(
        requirements=requirements,
        recommendations=recommendations
    )
    db.session.add(rec)
    db.session.commit()
    
    return render_template('recommendations.html', 
                         recommendations=recommendations,
                         recommendation_id=rec.id)

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    rec_id = request.form.get('recommendation_id')
    rating = request.form.get('rating')
    feedback = request.form.get('feedback')
    
    rec = Recommendation.query.get(rec_id)
    if rec:
        rec.rating = int(rating)
        rec.feedback = feedback
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "Recommendation not found"}), 404
