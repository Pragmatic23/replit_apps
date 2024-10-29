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

# ... (keep existing route handlers) ...

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
