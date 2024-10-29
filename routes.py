# Import existing imports
from functools import wraps
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, abort, jsonify, send_file
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
from models import User, Recommendation, UserSession
from utils import get_module_recommendations
from sqlalchemy import func, distinct
import json
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import qrcode
from PIL import Image as PILImage
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_recommendations', methods=['POST'])
@login_required
def get_recommendations():
    # Get basic requirements
    industry = request.form.get('industry')
    features = request.form.getlist('features')
    requirements = request.form.get('requirements', '')
    
    # Get additional Odoo-specific requirements
    company_size = request.form.get('company_size')
    budget = request.form.get('budget')
    deployment = request.form.get('deployment')
    region = request.form.get('region')
    integrations = request.form.getlist('integrations')
    languages = request.form.getlist('languages')
    
    # Get new Odoo experience and setup fields
    odoo_experience = request.form.get('odoo_experience')
    current_version = request.form.get('current_version')
    setup_type = request.form.get('setup_type')
    timeline = request.form.get('timeline')
    
    # Create a detailed requirements string
    detailed_requirements = f"""
Odoo Experience Level: {odoo_experience}
Current Odoo Version: {current_version or 'Not using Odoo'}
Setup Type: {setup_type}
Implementation Timeline: {timeline}

Industry: {industry}
Company Size: {company_size}
Budget Range: {budget}
Deployment Type: {deployment}
Geographic Region: {region}
Required Features: {', '.join(features) if features else 'None specified'}
Integration Requirements: {', '.join(integrations) if integrations else 'None specified'}
Language Requirements: {', '.join(languages) if languages else 'English only'}

Additional Requirements:
{requirements}
"""
    
    recommendations = get_module_recommendations(
        requirements=detailed_requirements,
        industry=industry,
        features=features
    )
    
    # Create a new recommendation record if successful
    if not recommendations.get('error'):
        recommendation = Recommendation(
            requirements=detailed_requirements,
            recommendations=recommendations['text'],
            user_id=current_user.id,
            module_urls=json.dumps(recommendations.get('urls', {})),
            module_images=json.dumps(recommendations.get('images', {}))
        )
        db.session.add(recommendation)
        db.session.commit()
        
        return render_template('recommendations.html', 
                             recommendations=recommendations,
                             recommendation_id=recommendation.id)
    
    return render_template('recommendations.html', recommendations=recommendations)

# Rest of the routes remain unchanged...
