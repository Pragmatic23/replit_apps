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

@app.route('/get_recommendations', methods=['POST'])
@login_required
def get_recommendations():
    # Get all form fields
    industry = request.form.get('industry')
    features = request.form.getlist('features')
    requirements = request.form.get('requirements', '')
    
    # Get new fields
    customer_website = request.form.get('customer_website', '')
    has_odoo_experience = request.form.get('has_odoo_experience')
    preferred_edition = request.form.get('preferred_edition')
    current_version = request.form.get('current_version')
    
    # Get existing additional fields
    company_size = request.form.get('company_size')
    budget = request.form.get('budget')
    deployment = request.form.get('deployment')
    region = request.form.get('region')
    integrations = request.form.getlist('integrations')
    languages = request.form.getlist('languages')
    
    # Create a detailed requirements string
    detailed_requirements = f"""
Business Information:
Industry: {industry}
Company Size: {company_size}
Customer Website: {customer_website}
Budget Range: {budget}
Geographic Region: {region}

Odoo Experience and Preferences:
Previous Odoo Experience: {has_odoo_experience}
Preferred Edition: {preferred_edition}
Current Version: {current_version or 'Not using Odoo'}
Deployment Type: {deployment}

Technical Requirements:
Required Features: {', '.join(features) if features else 'None specified'}
Integration Requirements: {', '.join(integrations) if integrations else 'None specified'}
Language Requirements: {', '.join(languages) if languages else 'English only'}

Additional Requirements:
{requirements}
"""
    
    # Get recommendations with updated context
    recommendations = get_module_recommendations(
        requirements=detailed_requirements,
        industry=industry,
        features=features,
        preferred_edition=preferred_edition,
        has_experience=has_odoo_experience
    )
    
    # Create recommendation record if successful
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

# Keep other routes unchanged
