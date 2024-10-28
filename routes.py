from functools import wraps
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from app import app, db
from models import User, Recommendation
from utils import get_module_recommendations

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
        return redirect(url_for('dashboard'))
    
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    user_recommendations = Recommendation.query.filter_by(user_id=current_user.id).order_by(Recommendation.created_at.desc()).all()
    return render_template('user/dashboard.html', recommendations=user_recommendations)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
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
    users = User.query.order_by(User.created_at.desc()).all()
    recommendations = Recommendation.query.order_by(Recommendation.created_at.desc()).all()
    stats = {
        'total_users': User.query.count(),
        'total_recommendations': Recommendation.query.count(),
        'average_rating': db.session.query(db.func.avg(Recommendation.rating)).scalar() or 0
    }
    return render_template('admin/dashboard.html', users=users, recommendations=recommendations, stats=stats)

@app.route('/get_recommendations', methods=['POST'])
def get_recommendations():
    requirements = request.form.get('requirements')
    if not requirements:
        return "Please provide your requirements", 400

    recommendations = get_module_recommendations(requirements)
    recommendation_id = None
    
    # Save recommendation if user is logged in
    if current_user.is_authenticated:
        recommendation = Recommendation(
            requirements=requirements,
            recommendations=recommendations,
            user_id=current_user.id
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
    
    # Ensure the recommendation belongs to the current user
    if recommendation.user_id != current_user.id:
        abort(403)
        
    recommendation.rating = int(rating)
    recommendation.feedback = feedback
    db.session.commit()
    
    flash('Thank you for your feedback!')
    return redirect(url_for('dashboard'))
