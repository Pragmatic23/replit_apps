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
    industry = request.form.get('industry')
    features = request.form.getlist('features')
    requirements = request.form.get('requirements', '')
    
    recommendations = get_module_recommendations(
        requirements=requirements,
        industry=industry,
        features=features
    )
    
    # Create a new recommendation record if successful
    if not recommendations.get('error'):
        recommendation = Recommendation(
            requirements=requirements,
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

@app.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    recommendation_id = request.form.get('recommendation_id')
    overall_rating = request.form.get('overall_rating')
    ease_of_use = request.form.get('ease_of_use')
    features = request.form.get('features_rating')
    integration = request.form.get('integration_rating')
    category = request.form.get('feedback_category')
    feedback = request.form.get('feedback')
    screenshot = request.files.get('screenshot')
    
    if not recommendation_id or not overall_rating:
        flash('Overall rating is required')
        return redirect(request.referrer)
        
    recommendation = Recommendation.query.get_or_404(recommendation_id)
    
    if recommendation.user_id != current_user.id:
        abort(403)
    
    # Handle screenshot upload
    screenshot_url = None
    if screenshot and screenshot.filename:
        filename = secure_filename(f"screenshot_{recommendation_id}_{int(datetime.utcnow().timestamp())}.png")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        screenshot.save(filepath)
        screenshot_url = f"/static/uploads/{filename}"
        
    recommendation.rating = int(overall_rating)
    recommendation.ease_of_use_rating = int(ease_of_use) if ease_of_use else None
    recommendation.features_rating = int(features) if features else None
    recommendation.integration_rating = int(integration) if integration else None
    recommendation.feedback_category = category
    recommendation.feedback = feedback
    recommendation.screenshot_url = screenshot_url
    
    db.session.commit()
    
    flash('Thank you for your detailed feedback!')
    return redirect(url_for('dashboard'))

@app.route('/export_recommendations/<int:recommendation_id>')
@login_required
def export_recommendations(recommendation_id):
    recommendation = Recommendation.query.get_or_404(recommendation_id)
    
    if recommendation.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    
    # Create PDF filename
    pdf_filename = f"recommendation_{recommendation_id}.pdf"
    pdf_path = os.path.join(UPLOAD_FOLDER, pdf_filename)
    
    # Create the PDF document
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Add title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )
    story.append(Paragraph("Odoo Module Recommendations", title_style))
    story.append(Spacer(1, 12))
    
    # Add requirements
    story.append(Paragraph("Requirements:", styles["Heading2"]))
    story.append(Paragraph(recommendation.requirements, styles["BodyText"]))
    story.append(Spacer(1, 12))
    
    # Add recommendations
    story.append(Paragraph("Recommended Modules:", styles["Heading2"]))
    
    # Parse the stored JSON data
    module_urls = json.loads(recommendation.module_urls) if recommendation.module_urls else {}
    
    # Add each module with QR code
    for module in recommendation.recommendations.split('\n\n'):
        if module.strip():
            lines = module.strip().split('\n')
            if lines:
                module_name = lines[0].strip().replace('*', '').replace('#', '').replace('-', '').strip()
                module_url = module_urls.get(module_name, '')
                
                # Create QR code if URL exists
                if module_url:
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(module_url)
                    qr.make(fit=True)
                    qr_image = qr.make_image(fill_color="black", back_color="white")
                    qr_path = os.path.join(UPLOAD_FOLDER, f"qr_{recommendation_id}_{module_name}.png")
                    qr_image.save(qr_path)
                    
                    # Add module name and description
                    story.append(Paragraph(module_name, styles["Heading3"]))
                    if len(lines) > 1:
                        story.append(Paragraph(lines[1], styles["BodyText"]))
                    
                    # Add QR code
                    story.append(Image(qr_path, width=100, height=100))
                    story.append(Spacer(1, 12))
    
    # Build PDF
    doc.build(story)
    
    # Return the PDF file
    return send_file(pdf_path, as_attachment=True, download_name=pdf_filename)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            
            # Create new session
            session = UserSession(user_id=user.id)
            db.session.add(session)
            db.session.commit()
            
            return redirect(url_for('dashboard'))
            
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(username=username).first():
            flash('Username already taken')
            return redirect(url_for('signup'))
            
        user = User()
        user.username = username
        user.email = email
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    # End current session
    active_session = UserSession.query.filter_by(
        user_id=current_user.id, 
        session_end=None
    ).first()
    
    if active_session:
        active_session.session_end = datetime.utcnow()
        db.session.commit()
    
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_recommendations = Recommendation.query.filter_by(
        user_id=current_user.id
    ).order_by(Recommendation.created_at.desc()).all()
    
    return render_template('user/dashboard.html', 
                         recommendations=user_recommendations)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.username = request.form.get('username')
        current_user.company = request.form.get('company')
        current_user.bio = request.form.get('bio')
        
        db.session.commit()
        flash('Profile updated successfully!')
        
    return render_template('user/profile.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get basic stats
    stats = {
        'total_users': User.query.count(),
        'total_recommendations': Recommendation.query.count(),
        'average_rating': db.session.query(func.avg(Recommendation.rating)).scalar() or 0,
        'active_sessions': UserSession.query.filter_by(session_end=None).count()
    }
    
    # Get daily active users for the last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily_users = db.session.query(
        func.date(UserSession.session_start).label('date'),
        func.count(distinct(UserSession.user_id)).label('count')
    ).filter(UserSession.session_start >= seven_days_ago).group_by(
        func.date(UserSession.session_start)
    ).all()
    
    # Get daily average ratings
    daily_ratings = db.session.query(
        func.date(Recommendation.created_at).label('date'),
        func.avg(Recommendation.rating).label('avg_rating')
    ).filter(
        Recommendation.rating.isnot(None),
        Recommendation.created_at >= seven_days_ago
    ).group_by(
        func.date(Recommendation.created_at)
    ).all()
    
    # Calculate average session duration
    avg_duration = db.session.query(
        func.avg(
            UserSession.session_end - UserSession.session_start
        )
    ).filter(UserSession.session_end.isnot(None)).scalar()
    
    if avg_duration:
        stats['avg_session_duration'] = str(avg_duration).split('.')[0]
    else:
        stats['avg_session_duration'] = 'N/A'
    
    # Get weekly feature usage
    week_ago = datetime.utcnow() - timedelta(days=7)
    stats['weekly_feature_usage'] = Recommendation.query.filter(
        Recommendation.created_at >= week_ago
    ).count()
    
    stats['daily_users'] = daily_users
    stats['daily_ratings'] = daily_ratings
    
    # Get recent users and recommendations
    users = User.query.order_by(User.created_at.desc()).limit(10).all()
    recommendations = Recommendation.query.order_by(
        Recommendation.created_at.desc()
    ).limit(10).all()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         users=users,
                         recommendations=recommendations)
