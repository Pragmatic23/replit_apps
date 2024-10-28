from functools import wraps
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
from models import User, Recommendation, UserSession
from utils import get_module_recommendations
from sqlalchemy import func, distinct

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            flash('You need administrator privileges to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def get_or_create_user_session():
    if not current_user.is_authenticated:
        return None
    
    active_session = UserSession.query.filter_by(
        user_id=current_user.id,
        session_end=None
    ).first()
    
    if not active_session:
        active_session = UserSession(user_id=current_user.id)
        db.session.add(active_session)
        db.session.commit()
    
    active_session.last_activity = datetime.utcnow()
    db.session.commit()
    return active_session

@app.route('/')
def index():
    if current_user.is_authenticated:
        get_or_create_user_session()
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            get_or_create_user_session()
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
        flash('Invalid email or password')
    
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
        
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(username=username).first():
            flash('Username already taken')
            return redirect(url_for('signup'))
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        get_or_create_user_session()
        return redirect(url_for('dashboard'))
    
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    active_session = UserSession.query.filter_by(
        user_id=current_user.id,
        session_end=None
    ).first()
    if active_session:
        active_session.session_end = datetime.utcnow()
        db.session.commit()
    
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    get_or_create_user_session()
    user_recommendations = Recommendation.query.filter_by(user_id=current_user.id).order_by(Recommendation.created_at.desc()).all()
    return render_template('user/dashboard.html', recommendations=user_recommendations)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    get_or_create_user_session()
    if request.method == 'POST':
        current_user.username = request.form.get('username')
        current_user.bio = request.form.get('bio')
        current_user.company = request.form.get('company')
        db.session.commit()
        flash('Profile updated successfully')
        return redirect(url_for('profile'))
    return render_template('user/profile.html')

@app.route('/admin')
@admin_required
def admin_dashboard():
    # Basic statistics
    total_users = User.query.count()
    total_recommendations = Recommendation.query.count()
    average_rating = db.session.query(func.avg(Recommendation.rating)).scalar() or 0
    active_sessions = UserSession.query.filter_by(session_end=None).count()
    
    # User activity trends (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    daily_users = db.session.query(
        func.date(UserSession.session_start).label('date'),
        func.count(distinct(UserSession.user_id)).label('count')
    ).filter(UserSession.session_start >= week_ago)\
    .group_by(func.date(UserSession.session_start))\
    .order_by(func.date(UserSession.session_start)).all()
    
    # Recent users and recommendations
    users = User.query.order_by(User.created_at.desc()).all()
    recommendations = Recommendation.query.order_by(Recommendation.created_at.desc()).limit(10).all()
    
    # Calculate average session duration
    completed_sessions = UserSession.query.filter(
        UserSession.session_end.isnot(None)
    ).all()
    
    total_duration = timedelta()
    session_count = len(completed_sessions)
    for session in completed_sessions:
        duration = session.session_end - session.session_start
        total_duration += duration
    
    avg_duration = str(total_duration / session_count if session_count > 0 else timedelta())
    
    # Daily ratings
    daily_ratings = db.session.query(
        func.date(Recommendation.created_at).label('date'),
        func.avg(Recommendation.rating).label('avg_rating')
    ).filter(
        Recommendation.rating.isnot(None),
        Recommendation.created_at >= week_ago
    ).group_by(func.date(Recommendation.created_at))\
    .order_by(func.date(Recommendation.created_at)).all()
    
    stats = {
        'total_users': total_users,
        'total_recommendations': total_recommendations,
        'average_rating': float(average_rating),
        'active_sessions': active_sessions,
        'daily_users': daily_users,
        'avg_session_duration': avg_duration,
        'weekly_feature_usage': Recommendation.query.filter(
            Recommendation.created_at >= week_ago
        ).count(),
        'daily_ratings': daily_ratings
    }
    
    return render_template('admin/dashboard.html', 
                         users=users, 
                         recommendations=recommendations, 
                         stats=stats)

@app.route('/get_recommendations', methods=['POST'])
def get_recommendations():
    requirements = request.form.get('requirements', '')
    industry = request.form.get('industry', '')
    company_size = request.form.get('company_size', '')
    budget = request.form.get('budget', '')
    features = request.form.getlist('features')

    if not industry or not company_size or not budget:
        flash('Please fill in all required fields')
        return redirect(url_for('index'))

    recommendations = get_module_recommendations(
        requirements=requirements,
        industry=industry,
        company_size=company_size,
        budget=budget,
        features=features
    )
    
    recommendation_id = None
    
    if current_user.is_authenticated:
        active_session = get_or_create_user_session()
        full_context = f"""
Industry: {industry}
Company Size: {company_size}
Budget Level: {budget}
Features: {', '.join(features) if features else 'None'}
Additional Requirements: {requirements}

Recommendations:
{recommendations}
"""
        recommendation = Recommendation(
            requirements=full_context,
            recommendations=recommendations,
            user_id=current_user.id,
            session_id=active_session.id if active_session else None
        )
        db.session.add(recommendation)
        db.session.commit()
        recommendation_id = recommendation.id
    
    return render_template('recommendations.html', 
                         recommendations=recommendations,
                         recommendation_id=recommendation_id)

@app.route('/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    recommendation_id = request.form.get('recommendation_id')
    rating = request.form.get('rating')
    feedback = request.form.get('feedback')
    
    if not recommendation_id or not rating:
        flash('Rating is required')
        return redirect(request.referrer)
        
    recommendation = Recommendation.query.get_or_404(recommendation_id)
    
    if recommendation.user_id != current_user.id:
        abort(403)
        
    recommendation.rating = int(rating)
    recommendation.feedback = feedback
    db.session.commit()
    
    flash('Thank you for your feedback!')
    return redirect(url_for('dashboard'))
