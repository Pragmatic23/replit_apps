from flask import render_template, request
from app import app
from utils import get_module_recommendations

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_recommendations', methods=['POST'])
def get_recommendations():
    requirements = request.form.get('requirements')
    if not requirements:
        return "Please provide your requirements", 400

    recommendations = get_module_recommendations(requirements)
    return render_template('recommendations.html', recommendations=recommendations)
