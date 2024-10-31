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
import tempfile
import io
import re

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

def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def is_valid_username(username):
    return len(username) >= 3 and re.match(r'^[a-zA-Z0-9_-]+$', username)

def is_strong_password(password):
    return (len(password) >= 8 and 
            re.search(r'[A-Z]', password) and 
            re.search(r'[a-z]', password) and 
            re.search(r'[0-9]', password))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_recommendations', methods=['POST'])
@login_required
def get_recommendations():
    try:
        industry = request.form.get('industry')
        features = request.form.getlist('features')
        requirements = request.form.get('requirements', '')
        
        customer_website = request.form.get('customer_website', '')
        has_odoo_experience = request.form.get('has_odoo_experience')
        preferred_edition = request.form.get('preferred_edition')
        current_version = request.form.get('current_version')
        
        company_size = request.form.get('company_size')
        deployment = request.form.get('deployment')
        region = request.form.get('region')
        integrations = request.form.getlist('integrations')
        languages = request.form.getlist('languages')
        
        detailed_requirements = f"""
Business Information:
Industry: {industry}
Company Size: {company_size}
Customer Website: {customer_website}
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
        
        recommendations = get_module_recommendations(
            requirements=detailed_requirements,
            industry=industry,
            features=features,
            preferred_edition=preferred_edition,
            has_experience=has_odoo_experience
        )
        
        if 'error' in recommendations:
            flash(recommendations['error'], 'error')
            return redirect(url_for('index'))
            
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
    
    except Exception as e:
        flash(f"An error occurred: {str(e)}", 'error')
        return redirect(url_for('index'))

@app.route('/export_recommendations/<int:recommendation_id>')
@login_required
def export_recommendations(recommendation_id):
    try:
        recommendation = Recommendation.query.get_or_404(recommendation_id)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            doc = SimpleDocTemplate(tmp_file.name, pagesize=letter)
            styles = getSampleStyleSheet()
            story = []
            
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontSize=24,
                spaceAfter=30
            )
            story.append(Paragraph("Odoo Module Recommendations", title_style))
            story.append(Spacer(1, 20))
            
            story.append(Paragraph("Business Requirements", styles['Heading1']))
            story.append(Paragraph(recommendation.requirements, styles['Normal']))
            story.append(Spacer(1, 20))
            
            story.append(Paragraph("Recommended Modules", styles['Heading1']))
            story.append(Paragraph(recommendation.recommendations, styles['Normal']))
            
            doc.build(story)
            
            return send_file(
                tmp_file.name,
                as_attachment=True,
                download_name=f'odoo_recommendations_{recommendation_id}.pdf',
                mimetype='application/pdf'
            )
    except Exception as e:
        flash(f"Error generating PDF: {str(e)}", 'error')
        return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False) == 'on'
        
        if not email or not password:
            flash('Please fill in all fields', 'danger')
            return redirect(url_for('login'))
            
        if not is_valid_email(email):
            flash('Please enter a valid email address', 'danger')
            return redirect(url_for('login'))
            
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            
            # Create new session after successful login
            new_session = UserSession(user_id=user.id)
            db.session.add(new_session)
            db.session.commit()
            
            flash('Successfully logged in!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'danger')
            
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([username, email, password, confirm_password]):
            flash('Please fill in all fields', 'danger')
            return redirect(url_for('signup'))
            
        if not is_valid_username(username):
            flash('Username must be at least 3 characters and contain only letters, numbers, underscores, and hyphens', 'danger')
            return redirect(url_for('signup'))
            
        if not is_valid_email(email):
            flash('Please enter a valid email address', 'danger')
            return redirect(url_for('signup'))
            
        if not is_strong_password(password):
            flash('Password must be at least 8 characters and contain uppercase, lowercase, and numbers', 'danger')
            return redirect(url_for('signup'))
            
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'danger')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(username=username).first():
            flash('Username already taken', 'danger')
            return redirect(url_for('signup'))
        
        try:
            # Create and save the user first
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()  # This will assign an ID to the user
            
            # Now create the session with the user's ID
            session = UserSession(user_id=user.id)
            db.session.add(session)
            
            # Commit all changes
            db.session.commit()
            
            # Log the user in
            login_user(user)
            flash('Account created successfully!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during registration. Please try again.', 'danger')
            return redirect(url_for('signup'))
        
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    if current_user.is_authenticated:
        # End the current session if it exists
        current_session = UserSession.query.filter_by(
            user_id=current_user.id, 
            session_end=None
        ).first()
        
        if current_session:
            current_session.session_end = datetime.utcnow()
            try:
                db.session.commit()
            except:
                db.session.rollback()
    
    logout_user()
    flash('Successfully logged out', 'info')
    return redirect(url_for('login'))

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    stats = {
        'total_users': User.query.count(),
        'total_recommendations': Recommendation.query.count(),
        'active_sessions': UserSession.query.filter_by(session_end=None).count(),
        'daily_users': [],
        'daily_ratings': []
    }
    
    users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recommendations = Recommendation.query.order_by(Recommendation.created_at.desc()).limit(10).all()
    
    return render_template('admin/dashboard.html', stats=stats, users=users, recommendations=recommendations)

@app.route('/dashboard')
@login_required
def dashboard():
    user_recommendations = Recommendation.query.filter_by(user_id=current_user.id).order_by(Recommendation.created_at.desc()).all()
    return render_template('user/dashboard.html', recommendations=user_recommendations)
