"""
=============================================================================
CampusFIX Enterprise Monolith
=============================================================================
A comprehensive, all-in-one Campus Facility Maintenance & Ticketing System.
This file contains the Application Factory, Database Models, HTML Template
Generator, View Routes, Role-Based Access Control, and Seeding Scripts.

Instructions:
1. pip install Flask Flask-SQLAlchemy Flask-Login Werkzeug
2. python app.py
3. Open http://localhost:5000 in your browser.
=============================================================================
"""

import os
import logging
import csv
from io import StringIO
from datetime import datetime, timedelta
from itertools import chain
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, 
                   flash, abort, jsonify, Response, send_from_directory)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, login_user, logout_user, 
                         login_required, current_user, UserMixin)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, desc, or_

# ==========================================
# 1. APPLICATION CONFIGURATION & SETUP
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super_secret_campusfix_key_999')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///campusfix_enterprise_master.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# FIX: Inject datetime into Jinja globals to resolve "UndefinedError"
app.jinja_env.globals.update(datetime=datetime)

# File Upload Configurations
UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Centralized Logging setup
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] %(levelname)s - %(module)s.%(funcName)s: %(message)s'
)
logger = logging.getLogger('CampusFixLogger')

# Initialize Database
db = SQLAlchemy(app)

# Initialize Authentication
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Secure Area: Please log in to continue."
login_manager.login_message_category = 'warning'

@app.after_request
def apply_security_headers(response):
    """Middleware: Apply enterprise security headers."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

def allowed_file(filename):
    """Helper: Validate uploaded file extensions."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ==========================================
# 2. DATABASE MODELS
# ==========================================

class User(UserMixin, db.Model):
    """System Users: Can be Students, Techs, or Admins."""
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Student') # Student, Tech, Admin
    department = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    complaints_filed = db.relationship('Complaint', foreign_keys='Complaint.user_id', backref='author', lazy=True)
    complaints_assigned = db.relationship('Complaint', foreign_keys='Complaint.assigned_to', backref='assignee', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True, order_by="desc(Notification.created_at)")

class Complaint(db.Model):
    """Maintenance Tickets / Complaints."""
    __tablename__ = 'complaints'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False) 
    priority = db.Column(db.String(20), nullable=False, default='Medium') 
    location = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='Pending', index=True)
    image_file = db.Column(db.String(255), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    comments = db.relationship('Comment', backref='complaint', lazy=True, cascade="all, delete-orphan")
    audit_logs = db.relationship('AuditLog', backref='complaint', lazy=True, cascade="all, delete-orphan")
    
    @property
    def progress(self):
        if self.status == "Pending":
            return 25
        elif self.status == "In Progress":
            return 75
        elif self.status == "Resolved":
            return 100
        return 0

class Comment(db.Model):
    """Communication stream on a ticket."""
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False)
    
    user = db.relationship('User', backref='comments')

class AuditLog(db.Model):
    """Immutable system logs for security and tracking."""
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=True)
    
    user = db.relationship('User')

class Notification(db.Model):
    """User-specific system alerts."""
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

class InventoryItem(db.Model):
    """Tech inventory tracking."""
    __tablename__ = 'inventory'
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    category = db.Column(db.String(50), nullable=False)
    last_restocked = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==========================================
# 3. RBAC DECORATORS & HELPERS
# ==========================================

def role_required(*roles):
    """Decorator to enforce role-based access to specific routes."""
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if current_user.role not in roles:
                logger.warning(f"Access denied: {current_user.email} attempted to access {request.path}")
                abort(403)
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper

def create_notification(user_id, message, link=None):
    """Helper to generate internal system notifications."""
    notif = Notification(user_id=user_id, message=message, link=link)
    db.session.add(notif)
    # Note: Commit is expected to be handled by the calling function


# ==========================================
# 4. TEMPLATE AUTO-GENERATOR
# ==========================================

def initialize_templates():
    """Generates all comprehensive HTML files required for the application."""
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(template_dir, exist_ok=True)

    templates = {
        # ------------------------------------------------------------------
        # BASE TEMPLATE
        # ------------------------------------------------------------------
        "base.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}CampusFIX Enterprise{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root { --primary-brand: #d35400; --secondary-brand: #2c3e50; }
        body { background-color: #f8f9fa; font-family: 'Inter', sans-serif; color: #333; }
        .navbar { background-color: var(--secondary-brand) !important; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .navbar-brand { font-weight: 700; letter-spacing: 0.5px; }
        .btn-primary { background-color: var(--primary-brand); border-color: var(--primary-brand); }
        .btn-primary:hover { background-color: #e67e22; border-color: #e67e22; }
        .text-primary { color: var(--primary-brand) !important; }
        .card { border: none; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.04); transition: transform 0.2s ease; }
        .card-hover:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(0,0,0,0.08); }
        .status-badge { font-weight: 600; padding: 0.4em 0.8em; border-radius: 8px; }
        .timeline { border-left: 2px solid #e9ecef; padding-left: 1.5rem; position: relative; }
        .timeline-item { margin-bottom: 1.5rem; position: relative; }
        .timeline-item::before { content: ''; position: absolute; left: -1.85rem; top: 0.25rem; width: 12px; height: 12px; border-radius: 50%; background: var(--secondary-brand); border: 2px solid #fff; }
        .nav-pills .nav-link.active { background-color: var(--primary-brand); }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark mb-4 sticky-top">
        <div class="container-fluid px-4">
            <a class="navbar-brand d-flex align-items-center" href="{{ url_for('index') }}">
                <i class="bi bi-tools text-warning me-2 fs-4"></i> CampusFIX
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto align-items-center">
                    {% if current_user.is_authenticated %}
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('dashboard') }}"><i class="bi bi-speedometer2 me-1"></i> Dashboard</a></li>
                        
                        {% if current_user.role == 'Admin' %}
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('manage_users') }}"><i class="bi bi-people me-1"></i> Users</a></li>
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('inventory') }}"><i class="bi bi-box-seam me-1"></i> Inventory</a></li>
                        {% elif current_user.role == 'Tech' %}
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('inventory') }}"><i class="bi bi-tools me-1"></i> Parts</a></li>
                        {% endif %}
                        
                        <li class="nav-item dropdown ms-2">
                            <a class="nav-link dropdown-toggle" href="#" id="notifDropdown" role="button" data-bs-toggle="dropdown">
                                <i class="bi bi-bell-fill"></i>
                                {% set unread = current_user.notifications|selectattr("is_read", "equalto", false)|list|length %}
                                {% if unread > 0 %}<span class="position-absolute top-10 start-90 translate-middle badge rounded-pill bg-danger" style="font-size:0.6rem;">{{ unread }}</span>{% endif %}
                            </a>
                            <ul class="dropdown-menu dropdown-menu-end shadow p-0" style="width: 300px; max-height: 400px; overflow-y: auto;">
                                <li class="dropdown-header bg-light border-bottom fw-bold text-dark py-2">Notifications</li>
                                {% for notif in current_user.notifications[:5] %}
                                <li>
                                    <a class="dropdown-item py-3 border-bottom {% if not notif.is_read %}bg-light{% endif %}" href="{{ url_for('read_notification', id=notif.id) }}">
                                        <div class="small text-muted mb-1">{{ notif.created_at.strftime('%b %d, %H:%M') }}</div>
                                        <div class="text-wrap lh-sm" style="font-size: 0.9rem;">{{ notif.message }}</div>
                                    </a>
                                </li>
                                {% else %}
                                <li><span class="dropdown-item text-muted text-center py-3">No new notifications.</span></li>
                                {% endfor %}
                            </ul>
                        </li>
                        
                        <li class="nav-item dropdown ms-2">
                            <a class="nav-link dropdown-toggle d-flex align-items-center" href="#" role="button" data-bs-toggle="dropdown">
                                <div class="bg-secondary text-white rounded-circle d-flex align-items-center justify-content-center me-2" style="width: 30px; height: 30px; font-size: 14px;">
                                    {{ current_user.full_name[0]|upper }}
                                </div>
                                <span>{{ current_user.full_name.split()[0] }}</span>
                            </a>
                            <ul class="dropdown-menu dropdown-menu-end shadow border-0 mt-2">
                                <li><h6 class="dropdown-header">{{ current_user.role }} Account</h6></li>
                                <li><a class="dropdown-item" href="{{ url_for('profile') }}"><i class="bi bi-person me-2"></i>My Profile</a></li>
                                <li><hr class="dropdown-divider"></li>
                                <li><a class="dropdown-item text-danger" href="{{ url_for('logout') }}"><i class="bi bi-box-arrow-right me-2"></i>Sign Out</a></li>
                            </ul>
                        </li>
                    {% else %}
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">Login</a></li>
                        <li class="nav-item"><a class="btn btn-primary ms-2 rounded-pill px-4" href="{{ url_for('register') }}">Register</a></li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>

    <main class="container-fluid px-md-5 mb-5" style="min-height: 80vh;">
        <div aria-live="polite" aria-atomic="true" class="position-relative">
            <div class="toast-container position-absolute top-0 end-0 p-3" style="z-index: 1100;">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        {% for category, message in messages %}
                            <div class="toast show align-items-center text-white bg-{{ 'danger' if category == 'error' else ('success' if category == 'success' else 'primary') }} border-0 mb-2 shadow" role="alert" aria-live="assertive" aria-atomic="true">
                                <div class="d-flex">
                                    <div class="toast-body fw-medium"><i class="bi bi-info-circle-fill me-2"></i>{{ message }}</div>
                                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                                </div>
                            </div>
                        {% endfor %}
                    {% endif %}
                {% endwith %}
            </div>
        </div>
        
        {% block content %}{% endblock %}
    </main>

    <footer class="bg-dark text-white py-4 mt-auto">
        <div class="container text-center text-md-start">
            <div class="row align-items-center">
                <div class="col-md-6 mb-3 mb-md-0">
                    <h5 class="fw-bold mb-1"><i class="bi bi-tools text-warning me-2"></i>CampusFIX Enterprise</h5>
                    <p class="text-white-50 small mb-0">Streamlining facility management since 2026.</p>
                </div>
                <div class="col-md-6 text-md-end text-white-50 small">
                    &copy; {{ datetime.now().year }} CampusFIX. All rights reserved. <br>
                    <a href="#" class="text-white-50 text-decoration-none me-2">Privacy Policy</a> |
                    <a href="#" class="text-white-50 text-decoration-none ms-2">Support Desk</a>
                </div>
            </div>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Auto-hide toasts after 5 seconds
        document.addEventListener('DOMContentLoaded', function () {
            var toastElList = [].slice.call(document.querySelectorAll('.toast'))
            var toastList = toastElList.map(function (toastEl) {
                return new bootstrap.Toast(toastEl, { delay: 5000 }).show()
            })
        });
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>""",

        # ------------------------------------------------------------------
        # AUTHENTICATION TEMPLATES
        # ------------------------------------------------------------------
        "login.html": """{% extends "base.html" %}
{% block title %}Login - CampusFIX{% endblock %}
{% block content %}
<div class="row justify-content-center align-items-center" style="min-height: 70vh;">
    <div class="col-md-5 col-lg-4">
        <div class="card shadow-lg border-0 overflow-hidden">
            <div class="card-body p-5">
                <div class="text-center mb-4">
                    <div class="bg-primary text-white rounded-circle d-inline-flex align-items-center justify-content-center mb-3" style="width: 60px; height: 60px;">
                        <i class="bi bi-person-lock fs-2"></i>
                    </div>
                    <h3 class="fw-bold text-dark">Welcome Back</h3>
                    <p class="text-muted small">Enter your credentials to access the portal.</p>
                </div>
                <form method="POST" action="{{ url_for('login') }}">
                    <div class="form-floating mb-3">
                        <input type="email" name="email" class="form-control bg-light border-0" id="emailInput" placeholder="name@example.com" required>
                        <label for="emailInput">Email address</label>
                    </div>
                    <div class="form-floating mb-4">
                        <input type="password" name="password" class="form-control bg-light border-0" id="passInput" placeholder="Password" required>
                        <label for="passInput">Password</label>
                    </div>
                    <button type="submit" class="btn btn-primary w-100 py-3 fw-bold rounded-3 shadow-sm">Secure Sign In</button>
                </form>
            </div>
            <div class="card-footer bg-light text-center py-3 border-0">
                <span class="text-muted small">Need an account?
<a href="{{ url_for('register') }}" class="text-primary fw-bold text-decoration-none">Register here</a></span>
            </div>
        </div>
    </div>
</div>
{% endblock %}""",

        "register.html": """{% extends "base.html" %}
{% block title %}Register - CampusFIX{% endblock %}
{% block content %}
<div class="row justify-content-center align-items-center" style="min-height: 70vh;">
    <div class="col-md-6 col-lg-5">
        <div class="card shadow-lg border-0">
            <div class="card-body p-5">
                <h3 class="fw-bold text-dark mb-4 text-center">Create Account</h3>
                <form method="POST" action="{{ url_for('register') }}">
                    <div class="mb-3">
                        <label class="form-label text-muted fw-semibold small">Full Name</label>
                        <input type="text" name="full_name" class="form-control bg-light border-0 py-2" required>
                    </div>
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label text-muted fw-semibold small">Email Address</label>
                            <input type="email" name="email" class="form-control bg-light border-0 py-2" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label text-muted fw-semibold small">Department / Major</label>
                            <input type="text" name="department" class="form-control bg-light border-0 py-2">
                        </div>
                    </div>
                    <div class="mb-4">
                        <label class="form-label text-muted fw-semibold small">Password</label>
                        <input type="password" name="password" class="form-control bg-light border-0 py-2" required minlength="8">
                        <div class="form-text">Must be at least 8 characters long.</div>
                    </div>
                    <button type="submit" class="btn btn-secondary w-100 py-3 fw-bold rounded-3">Register as Student</button>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}""",

        "profile.html": """{% extends "base.html" %}
{% block title %}My Profile{% endblock %}
{% block content %}
<div class="row max-w-4xl mx-auto mt-4">
    <div class="col-md-4 mb-4">
        <div class="card shadow-sm border-0 text-center p-4">
            <div class="bg-primary text-white rounded-circle mx-auto d-flex align-items-center justify-content-center mb-3" style="width: 100px; height: 100px; font-size: 2.5rem;">
                {{ current_user.full_name[0]|upper }}
            </div>
            <h4 class="fw-bold mb-0">{{ current_user.full_name }}</h4>
            <p class="text-muted mb-3">{{ current_user.role }} Account</p>
            <span class="badge bg-light text-dark border p-2 mb-2"><i class="bi bi-envelope me-2"></i>{{ current_user.email }}</span>
            <span class="badge bg-light text-dark border p-2"><i class="bi bi-building me-2"></i>{{ current_user.department or 'General' }}</span>
        </div>
    </div>
    <div class="col-md-8">
        <div class="card shadow-sm border-0 h-100">
            <div class="card-header bg-white py-3 border-bottom-0">
                <h5 class="fw-bold mb-0">Update Information</h5>
            </div>
            <div class="card-body p-4">
                <form action="{{ url_for('profile') }}" method="POST">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label text-muted small fw-bold">Full Name</label>
                            <input type="text" name="full_name" class="form-control" value="{{ current_user.full_name }}" required>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label text-muted small fw-bold">Department</label>
                            <input type="text" name="department" class="form-control" value="{{ current_user.department }}">
                        </div>
                    </div>
                    <hr class="my-4">
                    <h6 class="fw-bold mb-3">Change Password</h6>
                    <div class="mb-3">
                        <label class="form-label text-muted small fw-bold">New Password (leave blank to keep current)</label>
                        <input type="password" name="new_password" class="form-control">
                    </div>
                    <div class="text-end mt-4">
                        <button type="submit" class="btn btn-primary px-4"><i class="bi bi-save me-2"></i>Save Changes</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # DASHBOARDS
        # ------------------------------------------------------------------
        "student_dashboard.html": """{% extends "base.html" %}
{% block title %}Dashboard - CampusFIX{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-end mb-4 border-bottom pb-3 mt-3">
    <div>
        <h2 class="fw-bold mb-0">Welcome, {{ current_user.full_name.split()[0] }}!</h2>
        <p class="text-muted mb-0">Here is the status of your reported facilities issues.</p>
    </div>
    <a href="{{ url_for('submit_complaint') }}" class="btn btn-primary btn-lg shadow-sm rounded-pill px-4">
        <i class="bi bi-plus-lg me-2"></i>Report Issue
    </a>
</div>

<div class="row g-4">
    <div class="col-md-3">
        <div class="card bg-white border-0 shadow-sm p-3 border-start border-4 border-primary h-100">
            <h6 class="text-muted small fw-bold text-uppercase">Total Reported</h6>
            <h2 class="mb-0 fw-bold">{{ complaints|length }}</h2>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card bg-white border-0 shadow-sm p-3 border-start border-4 border-danger h-100">
            <h6 class="text-muted small fw-bold text-uppercase">Pending</h6>
            <h2 class="mb-0 fw-bold">{{ complaints|selectattr("status", "equalto", "Pending")|list|length }}</h2>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card bg-white border-0 shadow-sm p-3 border-start border-4 border-warning h-100">
            <h6 class="text-muted small fw-bold text-uppercase">In Progress</h6>
            <h2 class="mb-0 fw-bold">{{ complaints|selectattr("status", "equalto", "In Progress")|list|length }}</h2>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card bg-white border-0 shadow-sm p-3 border-start border-4 border-success h-100">
            <h6 class="text-muted small fw-bold text-uppercase">Resolved</h6>
            <h2 class="mb-0 fw-bold">{{ complaints|selectattr("status", "equalto", "Resolved")|list|length }}</h2>
        </div>
    </div>
</div>

<h4 class="fw-bold mt-5 mb-3">Your Ticket History</h4>
<div class="card border-0 shadow-sm overflow-hidden">
    <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
                <tr>
                    <th class="py-3 px-4">ID</th>
                    <th class="py-3">Issue Title</th>
                    <th class="py-3">Category</th>
                    <th class="py-3">Date Submitted</th>
                    <th class="py-3">Status</th>
                    <th class="py-3 text-end px-4">Action</th>
                </tr>
            </thead>
            <tbody>
                {% for c in complaints %}
                <tr>
                    <td class="px-4 fw-bold text-muted">#{{ c.id }}</td>
                    <td class="fw-medium text-dark">{{ c.title }}</td>
                    <td><span class="badge bg-light text-secondary border"><i class="bi bi-tag me-1"></i>{{ c.category }}</span></td>
                    <td class="text-muted small">{{ c.created_at.strftime('%d %b %Y') }}</td>
                    <td>
                        <span class="badge {% if c.status == 'Resolved' %}bg-success{% elif c.status == 'In Progress' %}bg-warning text-dark{% elif c.status == 'Cancelled' %}bg-secondary{% else %}bg-danger{% endif %} rounded-pill px-3 py-2">
                            {{ c.status }}
                        </span>
                    </td>
                    <td class="text-end px-4">
                        <a href="{{ url_for('view_complaint', id=c.id) }}" class="btn btn-sm btn-outline-primary rounded-pill px-3">View</a>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="6" class="text-center py-5">
                        <div class="text-muted">
                            <i class="bi bi-inbox fs-1 d-block mb-3"></i>
                            You haven't reported any issues yet.
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}""",

        "tech_dashboard.html": """{% extends "base.html" %}
{% block title %}Technician Portal - CampusFIX{% endblock %}
{% block content %}
<div class="row mb-4 mt-3 align-items-end">
    <div class="col-md-8">
        <h2 class="fw-bold mb-0 text-dark"><i class="bi bi-tools text-primary me-2"></i>Technician Workspace</h2>
        <p class="text-muted mb-0">Manage and resolve campus maintenance requests.</p>
    </div>
</div>

<ul class="nav nav-pills mb-4 bg-white p-2 rounded shadow-sm d-inline-flex" id="pills-tab" role="tablist">
    <li class="nav-item" role="presentation">
        <button class="nav-link active rounded-pill px-4 fw-bold" data-bs-toggle="pill" data-bs-target="#assigned">My Queue ({{ assigned|length }})</button>
    </li>
    <li class="nav-item" role="presentation">
        <button class="nav-link rounded-pill px-4 fw-bold text-dark" data-bs-toggle="pill" data-bs-target="#open">Open Pool ({{ open_tickets|length }})</button>
    </li>
</ul>

<div class="tab-content" id="pills-tabContent">
    <div class="tab-pane fade show active" id="assigned" role="tabpanel">
        <div class="row g-4">
            {% for c in assigned %}
            <div class="col-md-6 col-lg-4">
                <div class="card card-hover h-100 border-0 border-top border-4 {% if c.priority == 'Critical' %}border-danger{% elif c.status == 'Resolved' %}border-success{% else %}border-warning{% endif %}">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-2">
                            <span class="badge bg-light text-dark border">#{{ c.id }} | {{ c.category }}</span>
                            <span class="badge {% if c.status == 'Resolved' %}bg-success{% else %}bg-warning text-dark{% endif %}">{{ c.status }}</span>
                        </div>
                        <h5 class="fw-bold mb-1 text-truncate">{{ c.title }}</h5>
                        <p class="text-muted small mb-3"><i class="bi bi-geo-alt me-1"></i>{{ c.location }}</p>
                        <p class="small text-secondary text-truncate" style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; white-space: normal;">{{ c.description }}</p>
                    </div>
                    <div class="card-footer bg-white border-0 pt-0 d-flex justify-content-between align-items-center">
                        <div class="small text-muted"><i class="bi bi-clock me-1"></i>{{ c.updated_at.strftime('%b %d') }}</div>
                        <a href="{{ url_for('view_complaint', id=c.id) }}" class="btn btn-primary btn-sm px-3 rounded-pill">Manage</a>
                    </div>
                </div>
            </div>
            {% else %}
            <div class="col-12">
                <div class="card border-0 shadow-sm text-center py-5">
                    <div class="card-body">
                        <i class="bi bi-check-circle text-success fs-1 mb-3 d-block"></i>
                        <h4 class="text-muted">Your queue is empty!</h4>
                        <p class="text-muted small">Grab a ticket from the open pool to get started.</p>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>

    <div class="tab-pane fade" id="open" role="tabpanel">
        <div class="card border-0 shadow-sm overflow-hidden">
            <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                    <thead class="table-light">
                        <tr>
                            <th class="py-3 px-4">Priority</th>
                            <th class="py-3">Location / Title</th>
                            <th class="py-3">Reported By</th>
                            <th class="py-3">Time Open</th>
                            <th class="py-3 text-end px-4">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for c in open_tickets %}
                        <tr>
                            <td class="px-4">
                                {% if c.priority == 'Critical' %}<span class="badge bg-danger rounded-pill px-3"><i class="bi bi-exclamation-triangle-fill me-1"></i> Critical</span>
                                {% elif c.priority == 'High' %}<span class="badge bg-warning text-dark rounded-pill px-3">High</span>
                                {% else %}<span class="badge bg-info text-dark rounded-pill px-3">{{ c.priority }}</span>{% endif %}
                            </td>
                            <td>
                                <div class="fw-bold text-dark">{{ c.title }}</div>
                                <div class="small text-muted"><i class="bi bi-geo-alt me-1"></i>{{ c.location }}</div>
                            </td>
                            <td>
                                <div class="d-flex align-items-center">
                                    <div class="bg-secondary text-white rounded-circle d-flex align-items-center justify-content-center me-2" style="width: 24px; height: 24px; font-size: 10px;">{{ c.author.full_name[0] }}</div>
                                    <span class="small">{{ c.author.full_name }}</span>
                                </div>
                            </td>
                            <td class="text-muted small">{{ c.created_at.strftime('%b %d, %H:%M') }}</td>
                            <td class="text-end px-4">
                                <form action="{{ url_for('update_complaint', id=c.id) }}" method="POST" class="d-inline">
                                    <input type="hidden" name="claim_ticket" value="true">
                                    <input type="hidden" name="status" value="In Progress">
                                    <button type="submit" class="btn btn-sm btn-dark rounded-pill px-3">Claim Issue</button>
                                </form>
                            </td>
                        </tr>
                        {% else %}
                        <tr><td colspan="5" class="text-center py-5 text-muted">No open tickets at the moment. Excellent!</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
{% endblock %}""",

        "admin_dashboard.html": """{% extends "base.html" %}
{% block title %}Admin Control Center{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-end mb-4 border-bottom pb-3 mt-3">
    <div>
        <h2 class="fw-bold mb-0 text-dark"><i class="bi bi-shield-lock text-primary me-2"></i>Admin Control Center</h2>
        <p class="text-muted mb-0">System-wide performance, logs, and oversight.</p>
    </div>
    <div>
        <a href="{{ url_for('export_data') }}" class="btn btn-outline-secondary btn-sm rounded-pill"><i class="bi bi-download me-2"></i>Export CSV</a>
        <button class="btn btn-primary btn-sm rounded-pill ms-2" onclick="location.reload();"><i class="bi bi-arrow-clockwise me-2"></i>Refresh</button>
    </div>
</div>

<div class="row g-4 mb-4">
    <div class="col-xl-3 col-md-6">
        <div class="card bg-primary text-white border-0 shadow-sm h-100 p-3">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h6 class="fw-bold mb-0 text-uppercase opacity-75">Total Users</h6>
                <i class="bi bi-people fs-3 opacity-50"></i>
            </div>
            <h2 class="display-5 fw-bold mb-0">{{ stats.users }}</h2>
        </div>
    </div>
    <div class="col-xl-3 col-md-6">
        <div class="card bg-dark text-white border-0 shadow-sm h-100 p-3">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h6 class="fw-bold mb-0 text-uppercase opacity-75">Total Tickets</h6>
                <i class="bi bi-ticket-detailed fs-3 opacity-50"></i>
            </div>
            <h2 class="display-5 fw-bold mb-0">{{ stats.total_complaints }}</h2>
        </div>
    </div>
    <div class="col-xl-3 col-md-6">
        <div class="card bg-warning text-dark border-0 shadow-sm h-100 p-3">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h6 class="fw-bold mb-0 text-uppercase opacity-75">Active/Pending</h6>
                <i class="bi bi-hourglass-split fs-3 opacity-50"></i>
            </div>
            <h2 class="display-5 fw-bold mb-0">{{ stats.active }}</h2>
        </div>
    </div>
    <div class="col-xl-3 col-md-6">
        <div class="card bg-success text-white border-0 shadow-sm h-100 p-3">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h6 class="fw-bold mb-0 text-uppercase opacity-75">Resolved</h6>
                <i class="bi bi-check2-circle fs-3 opacity-50"></i>
            </div>
            <h2 class="display-5 fw-bold mb-0">{{ stats.resolved }}</h2>
        </div>
    </div>
</div>

<div class="row g-4">
    <div class="col-lg-8">
        <div class="card border-0 shadow-sm h-100">
            <div class="card-header bg-white py-3 border-bottom-0 d-flex justify-content-between align-items-center">
                <h6 class="fw-bold mb-0">System Audit Trail</h6>
                <span class="badge bg-light text-secondary border">Live</span>
            </div>
            <div class="card-body p-0">
                <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
                    <table class="table table-hover table-sm align-middle mb-0">
                        <thead class="table-light sticky-top">
                            <tr>
                                <th class="px-4 py-2">Timestamp</th>
                                <th>User</th>
                                <th>Action</th>
                                <th class="text-end px-4">Target</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for log in logs %}
                            <tr>
                                <td class="px-4 text-muted small" style="font-family: monospace;">{{ log.created_at.strftime('%y-%m-%d %H:%M:%S') }}</td>
                                <td>
                                    {% if log.user %}
                                    <span class="badge bg-light text-dark border">{{ log.user.role }}</span> <span class="small">{{ log.user.full_name }}</span>
                                    {% else %}<span class="text-muted small">System</span>{% endif %}
                                </td>
                                <td><span class="small text-dark fw-medium">{{ log.action }}</span></td>
                                <td class="text-end px-4">
                                    {% if log.complaint_id %}
                                    <a href="{{ url_for('view_complaint', id=log.complaint_id) }}" class="btn btn-sm btn-link text-decoration-none py-0">TKT-{{ log.complaint_id }}</a>
                                    {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    <div class="col-lg-4">
        <div class="card border-0 shadow-sm h-100">
            <div class="card-header bg-white py-3 border-bottom-0">
                <h6 class="fw-bold mb-0">Technician Load</h6>
            </div>
            <div class="card-body">
                {% for tech in techs %}
                <div class="mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <span class="fw-medium text-dark small">{{ tech.full_name }}</span>
                        <span class="badge bg-primary rounded-pill">{{ tech.assigned_count }} open</span>
                    </div>
                    <div class="progress" style="height: 6px;">
                        {% set pct = (tech.assigned_count / 10 * 100) if tech.assigned_count <= 10 else 100 %}
                        <div class="progress-bar bg-{% if pct > 80 %}danger{% elif pct > 50 %}warning{% else %}success{% endif %}" role="progressbar" style="width: {{ pct }}%;"></div>
                    </div>
                </div>
                {% else %}
                <p class="text-muted small text-center py-4">No active technicians found.</p>
                {% endfor %}
            </div>
        </div>
    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # CORE FEATURES (Complaints, Views, Users, Inventory)
        # ------------------------------------------------------------------
        "submit_complaint.html": """{% extends "base.html" %}
{% block title %}Report Issue - CampusFIX{% endblock %}
{% block content %}
<div class="row justify-content-center mt-3">
    <div class="col-lg-8">
        <div class="card border-0 shadow-lg" style="background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%); color: white;">
            <div class="card-body p-md-5">
                <div class="text-center mb-5">
                    <div class="bg-primary text-white rounded-circle d-inline-flex align-items-center justify-content-center mb-3 shadow" style="width: 70px; height: 70px;">
                        <i class="bi bi-tools fs-1"></i>
                    </div>
                    <h2 class="fw-bold mb-1">Report Facility Issue</h2>
                    <p class="text-white-50">Please provide detailed information so our tech team can assist you quickly.</p>
                </div>
                
                <form action="{{ url_for('submit_complaint') }}" method="POST" enctype="multipart/form-data">
                    <div class="mb-4">
                        <label class="form-label text-white-50 fw-bold small text-uppercase">Short Title</label>
                        <input type="text" name="title" class="form-control form-control-lg bg-dark text-white border-secondary shadow-none" placeholder="e.g., Broken AC in Room 102" required>
                    </div>
                    
                    <div class="row mb-4 g-3">
                        <div class="col-md-6">
                            <label class="form-label text-white-50 fw-bold small text-uppercase">Issue Category</label>
                            <select name="category" class="form-select form-select-lg bg-dark text-white border-secondary shadow-none" required>
                                <option value="" disabled selected>Select category...</option>
                                <option value="Electrical">Electrical / Lighting</option>
                                <option value="Plumbing">Plumbing / Water</option>
                                <option value="HVAC">HVAC (Heating/Cooling)</option>
                                <option value="IT/Network">IT / Campus Wi-Fi</option>
                                <option value="Structural">Structural / Furniture</option>
                                <option value="Cleaning">Cleaning / Janitorial</option>
                                <option value="Other">Other</option>
                            </select>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label text-white-50 fw-bold small text-uppercase">Urgency / Priority</label>
                            <select name="priority" class="form-select form-select-lg bg-dark text-white border-secondary shadow-none" required>
                                <option value="Low">Low (No immediate impact)</option>
                                <option value="Medium" selected>Medium (Standard request)</option>
                                <option value="High">High (Impacting work/study)</option>
                                <option value="Critical">Critical (Safety hazard)</option>
                            </select>
                        </div>
                    </div>
                    
                    <div class="mb-4">
                        <label class="form-label text-white-50 fw-bold small text-uppercase">Exact Location</label>
                        <input type="text" name="location" class="form-control form-control-lg bg-dark text-white border-secondary shadow-none" placeholder="Building name, Floor, Room Number" required>
                    </div>
                    
                    <div class="mb-4">
                        <label class="form-label text-white-50 fw-bold small text-uppercase">Detailed Description</label>
                        <textarea name="description" class="form-control bg-dark text-white border-secondary shadow-none" rows="4" placeholder="Describe the issue in detail..." required></textarea>
                    </div>
                    
                    <div class="mb-5">
                        <label class="form-label text-white-50 fw-bold small text-uppercase">Attach Photo Evidence (Optional)</label>
                        <input type="file" name="photo" class="form-control bg-dark text-white border-secondary shadow-none" accept=".jpg,.jpeg,.png,.gif">
                        <div class="form-text text-white-50 mt-2"><i class="bi bi-info-circle me-1"></i>Max file size 16MB. JPG or PNG preferred.</div>
                    </div>
                    
                    <div class="d-grid">
                        <button type="submit" class="btn btn-primary btn-lg fw-bold py-3 shadow">Submit Ticket</button>
                    </div>
                </form>
            </div>
        </div>
    </div>
</div>
{% endblock %}""",

        "view_complaint.html": """{% extends "base.html" %}
{% block title %}Ticket #{{ complaint.id }} - CampusFIX{% endblock %}
{% block content %}
<div class="mb-3 mt-2">
    <a href="{{ url_for('dashboard') }}" class="text-decoration-none text-muted"><i class="bi bi-arrow-left me-1"></i>Back to Dashboard</a>
</div>

<div class="row g-4">
    <div class="col-lg-4">
        <div class="card border-0 shadow-sm h-100 border-top border-4 {% if complaint.status == 'Resolved' %}border-success{% elif complaint.status == 'In Progress' %}border-warning{% else %}border-danger{% endif %}">
            <div class="card-header bg-white py-3 d-flex justify-content-between align-items-center">
                <h5 class="fw-bold mb-0">Ticket #{{ complaint.id }}</h5>
                <span class="badge {% if complaint.status == 'Resolved' %}bg-success{% elif complaint.status == 'In Progress' %}bg-warning text-dark{% else %}bg-danger{% endif %} px-3 py-2 rounded-pill">
                    {{ complaint.status }}
                </span>
            </div>
            <div class="card-body">
                <h4 class="fw-bold mb-3 text-dark">{{ complaint.title }}</h4>
                
                <div class="mb-4">
                    <div class="text-uppercase small fw-bold text-muted mb-1">Location</div>
                    <div class="fw-medium"><i class="bi bi-geo-alt text-primary me-2"></i>{{ complaint.location }}</div>
                </div>
                
                <div class="row mb-4">
                    <div class="col-6">
                        <div class="text-uppercase small fw-bold text-muted mb-1">Category</div>
                        <div class="badge bg-light text-dark border">{{ complaint.category }}</div>
                    </div>
                    <div class="col-6">
                        <div class="text-uppercase small fw-bold text-muted mb-1">Priority</div>
                        <div class="badge {% if complaint.priority == 'Critical' %}bg-danger{% elif complaint.priority == 'High' %}bg-warning text-dark{% else %}bg-info text-dark{% endif %}">
                            {{ complaint.priority }}
                        </div>
                    </div>
                </div>
                
                <div class="mb-4">
                    <div class="text-uppercase small fw-bold text-muted mb-2">Description</div>
                    <div class="bg-light p-3 rounded text-dark" style="white-space: pre-wrap; font-size: 0.95rem;">{{ complaint.description }}</div>
                </div>
                
                {% if complaint.image_file %}
                <div class="mb-4">
                    <div class="text-uppercase small fw-bold text-muted mb-2">Attached Photo</div>
                    <a href="{{ url_for('static', filename='uploads/' + complaint.image_file) }}" target="_blank">
                        <img src="{{ url_for('static', filename='uploads/' + complaint.image_file) }}" class="img-fluid rounded border shadow-sm" alt="Issue photo">
                    </a>
                </div>
                {% endif %}
                
                <hr class="my-4">
                
                <div class="d-flex align-items-center justify-content-between">
                    <div>
                        <div class="text-uppercase small fw-bold text-muted mb-1">Reported By</div>
                        <div class="fw-medium d-flex align-items-center">
                            <i class="bi bi-person-circle fs-5 text-secondary me-2"></i>{{ complaint.author.full_name }}
                        </div>
                    </div>
                    <div class="text-end">
                        <div class="text-uppercase small fw-bold text-muted mb-1">Assigned Tech</div>
                        {% if complaint.assigned_to %}
                            <span class="badge bg-primary rounded-pill px-3 py-2"><i class="bi bi-tools me-1"></i>{{ complaint.assignee.full_name }}</span>
                        {% else %}
                        <span class="text-danger small fw-bold fst-italic">Unassigned</span>
                        {% endif %}
                    </div>
                </div>
            </div>
            
            {% if current_user.role in ['Admin', 'Tech'] and complaint.status != 'Resolved' %}
            <div class="card-footer bg-light p-4 border-0">
                <h6 class="fw-bold mb-3"><i class="bi bi-gear-fill me-2 text-primary"></i>Manage Ticket</h6>
                <form action="{{ url_for('update_complaint', id=complaint.id) }}" method="POST">
                    
                    {% if not complaint.assigned_to and current_user.role == 'Tech' %}
                    <div class="form-check mb-3 p-3 bg-white rounded border border-primary">
                        <input class="form-check-input ms-1 me-2" type="checkbox" name="claim_ticket" value="true" id="claimCheck">
                        <label class="form-check-label fw-bold text-primary" for="claimCheck">Claim this ticket</label>
                    </div>
                    {% endif %}
                    
                    <div class="mb-3">
                        <label class="form-label small fw-bold text-muted">Update Status</label>
                        <select name="status" class="form-select form-select-sm">
                            <option value="{{ complaint.status }}" selected>Current: {{ complaint.status }}</option>
                            {% if complaint.status == 'Pending' %}<option value="In Progress">Move to In Progress</option>{% endif %}
                            <option value="Resolved">Mark as Resolved</option>
                            <option value="Cancelled">Cancel Ticket</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-dark w-100 btn-sm fw-bold rounded-pill">Apply Changes</button>
                </form>
            </div>
            {% endif %}
        </div>
    </div>
    
    <div class="col-lg-8">
        <div class="card border-0 shadow-sm h-100 d-flex flex-column">
            <div class="card-header bg-white py-3 border-bottom d-flex align-items-center">
                <i class="bi bi-chat-right-text text-primary fs-5 me-2"></i>
                <h5 class="fw-bold mb-0">Activity & Communication</h5>
            </div>
            
            <div class="card-body overflow-auto flex-grow-1 p-4" style="max-height: 600px; background-color: #fcfcfc;">
                <div class="timeline">
                    {% for item in timeline %}
                        <div class="timeline-item">
                            <div class="text-muted small fw-bold mb-1">{{ item.created_at.strftime('%b %d, %Y - %I:%M %p') }}</div>
                            
                            {% if item.__class__.__name__ == 'AuditLog' %}
                                <div class="d-flex align-items-center text-muted ms-1 bg-white p-2 rounded border shadow-sm d-inline-flex">
                                    <i class="bi bi-info-circle-fill text-secondary me-2"></i>
                                    <span class="small">{{ item.action }} {% if item.user %}by {{ item.user.full_name }}{% endif %}</span>
                                </div>
                            {% else %}
                                <div class="card border-0 shadow-sm mt-1 {% if item.user.role in ['Admin', 'Tech'] %}bg-light border-start border-3 border-primary{% else %}bg-white{% endif %}">
                                    <div class="card-body p-3">
                                        <div class="d-flex align-items-center mb-2">
                                            <div class="bg-{% if item.user.role == 'Student' %}secondary{% else %}primary{% endif %} text-white rounded-circle d-flex align-items-center justify-content-center me-2" style="width: 28px; height: 28px; font-size: 12px;">
                                                {{ item.user.full_name[0] }}
                                            </div>
                                            <strong class="text-dark me-2">{{ item.user.full_name }}</strong>
                                            <span class="badge bg-light text-secondary border" style="font-size: 0.7rem;">{{ item.user.role }}</span>
                                        </div>
                                        <p class="mb-0 text-dark ms-4 ps-1" style="white-space: pre-wrap; font-size: 0.95rem;">{{ item.content }}</p>
                                    </div>
                                </div>
                            {% endif %}
                        </div>
                    {% endfor %}
                </div>
            </div>
            
            {% if complaint.status != 'Resolved' and complaint.status != 'Cancelled' %}
            <div class="card-footer bg-white p-4 border-top">
                <form action="{{ url_for('view_complaint', id=complaint.id) }}" method="POST">
                    <label class="form-label fw-bold text-dark mb-2">{% if current_user.role == 'Student' %}Send message to tech team{% else %}Add note or update for user{% endif %}</label>
                    <div class="input-group">
                        <textarea name="content" class="form-control" rows="2" placeholder="Type your message here..." required></textarea>
                        <button class="btn btn-primary px-4 fw-bold" type="submit"><i class="bi bi-send-fill me-2"></i>Post</button>
                    </div>
                </form>
            </div>
            {% else %}
            <div class="card-footer bg-light p-3 text-center text-muted border-top">
                <i class="bi bi-lock-fill me-2"></i>This ticket is closed. Further communication is disabled.
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}""",

        "manage_users.html": """{% extends "base.html" %}
{% block title %}Manage Users{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4 mt-3">
    <h2 class="fw-bold mb-0"><i class="bi bi-people text-primary me-2"></i>User Directory</h2>
</div>
<div class="card border-0 shadow-sm">
    <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
                <tr>
                    <th class="py-3 px-4">Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Department</th>
                    <th>Status</th>
                    <th class="text-end px-4">Action</th>
                </tr>
            </thead>
            <tbody>
                {% for u in users %}
                <tr>
                    <td class="px-4 fw-bold text-dark">{{ u.full_name }}</td>
                    <td class="text-muted">{{ u.email }}</td>
                    <td>
                        <span class="badge {% if u.role == 'Admin' %}bg-danger{% elif u.role == 'Tech' %}bg-primary{% else %}bg-secondary{% endif %}">
                            {{ u.role }}
                        </span>
                    </td>
                    <td>{{ u.department or '-' }}</td>
                    <td>
                        {% if u.is_active %}<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25 rounded-pill px-3">Active</span>
                        {% else %}<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25 rounded-pill px-3">Suspended</span>{% endif %}
                    </td>
                    <td class="text-end px-4">
                        {% if u.id != current_user.id %}
                        <form action="{{ url_for('toggle_user_status', id=u.id) }}" method="POST" class="d-inline">
                            <button type="submit" class="btn btn-sm {% if u.is_active %}btn-outline-danger{% else %}btn-outline-success{% endif %} rounded-pill px-3">
                                {% if u.is_active %}Suspend{% else %}Activate{% endif %}
                            </button>
                        </form>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}""",

        "inventory.html": """{% extends "base.html" %}
{% block title %}Tech Inventory{% endblock %}
{% block content %}
<div class="d-flex justify-content-between align-items-center mb-4 mt-3">
    <h2 class="fw-bold mb-0"><i class="bi bi-box-seam text-primary me-2"></i>Parts & Inventory</h2>
    {% if current_user.role == 'Admin' %}
    <button class="btn btn-primary rounded-pill" data-bs-toggle="modal" data-bs-target="#addItemModal"><i class="bi bi-plus-lg me-2"></i>Add Item</button>
    {% endif %}
</div>
<div class="row g-4">
    {% for item in items %}
    <div class="col-md-4 col-lg-3">
        <div class="card border-0 shadow-sm h-100 border-top border-4 {% if item.quantity < 5 %}border-danger{% else %}border-success{% endif %}">
            <div class="card-body">
                <div class="d-flex justify-content-between mb-2">
                    <span class="badge bg-light text-dark border">{{ item.category }}</span>
                    {% if item.quantity < 5 %}<span class="badge bg-danger"><i class="bi bi-exclamation-triangle me-1"></i>Low Stock</span>{% endif %}
                </div>
                <h5 class="fw-bold text-dark mb-1">{{ item.item_name }}</h5>
                <h2 class="display-6 fw-bold mb-0 mt-3 {% if item.quantity < 5 %}text-danger{% else %}text-success{% endif %}">{{ item.quantity }} <span class="fs-6 text-muted fw-normal">units</span></h2>
            </div>
            {% if current_user.role == 'Tech' %}
            <div class="card-footer bg-white border-0 pt-0">
                <form action="{{ url_for('update_inventory', id=item.id) }}" method="POST" class="d-flex">
                    <input type="number" name="amount" class="form-control form-control-sm me-2" value="-1" max="0" required>
                    <button type="submit" class="btn btn-dark btn-sm w-100">Use Part</button>
                </form>
            </div>
            {% elif current_user.role == 'Admin' %}
            <div class="card-footer bg-white border-0 pt-0">
                <form action="{{ url_for('update_inventory', id=item.id) }}" method="POST" class="d-flex">
                    <input type="number" name="amount" class="form-control form-control-sm me-2" placeholder="+ qty" required>
                    <button type="submit" class="btn btn-outline-primary btn-sm w-100">Restock</button>
                </form>
            </div>
            {% endif %}
        </div>
    </div>
    {% else %}
    <div class="col-12 text-center py-5">
        <i class="bi bi-box fs-1 text-muted d-block mb-3"></i>
        <p class="text-muted">Inventory is empty.</p>
    </div>
    {% endfor %}
</div>

<div class="modal fade" id="addItemModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content border-0 shadow">
      <div class="modal-header bg-dark text-white border-0">
        <h5 class="modal-title fw-bold">Add New Inventory Item</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <form action="{{ url_for('add_inventory') }}" method="POST">
          <div class="modal-body p-4">
              <div class="mb-3">
                  <label class="form-label small fw-bold text-muted">Item Name</label>
                  <input type="text" name="item_name" class="form-control" required>
              </div>
              <div class="mb-3">
                  <label class="form-label small fw-bold text-muted">Category</label>
                  <select name="category" class="form-select" required>
                      <option value="Electrical">Electrical</option>
                      <option value="Plumbing">Plumbing</option>
                      <option value="HVAC">HVAC</option>
                      <option value="Hardware">Hardware/Tools</option>
                  </select>
              </div>
              <div class="mb-3">
                  <label class="form-label small fw-bold text-muted">Initial Quantity</label>
                  <input type="number" name="quantity" class="form-control" min="0" value="0" required>
              </div>
          </div>
          <div class="modal-footer bg-light border-0">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="submit" class="btn btn-primary fw-bold px-4">Save Item</button>
          </div>
      </form>
    </div>
  </div>
</div>
{% endblock %}"""
    }

    # Generate Error Pages
    error_templates = {
        "404.html": """{% extends "base.html" %}{% block title %}404 - Not Found{% endblock %}{% block content %}<div class="text-center py-5 mt-5"><h1 class="display-1 fw-bold text-primary">404</h1><h3 class="mb-4">Page Not Found</h3><a href="{{ url_for('index') }}" class="btn btn-primary rounded-pill px-4">Return Home</a></div>{% endblock %}""",
        "403.html": """{% extends "base.html" %}{% block title %}403 - Forbidden{% endblock %}{% block content %}<div class="text-center py-5 mt-5"><h1 class="display-1 fw-bold text-danger">403</h1><h3 class="mb-4">Access Denied</h3><p class="text-muted mb-4">You don't have the necessary permissions to view this page.</p><a href="{{ url_for('index') }}" class="btn btn-danger rounded-pill px-4">Return Home</a></div>{% endblock %}""",
        "500.html": """{% extends "base.html" %}{% block title %}500 - Server Error{% endblock %}{% block content %}<div class="text-center py-5 mt-5"><h1 class="display-1 fw-bold text-secondary">500</h1><h3 class="mb-4">Internal Server Error</h3><a href="{{ url_for('index') }}" class="btn btn-secondary rounded-pill px-4">Return Home</a></div>{% endblock %}"""
    }
    templates.update(error_templates)

    # Write all files to disk securely
    for filename, content in templates.items():
        filepath = os.path.join(template_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Generated Enterprise Template: {filename}")

# ==========================================
# 5. AUTHENTICATION & CORE ROUTES
# ==========================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash('Your account has been suspended. Contact an administrator.', 'error')
                return redirect(url_for('login'))
                
            login_user(user)
            db.session.add(AuditLog(action="User Login", user_id=user.id))
            db.session.commit()
            logger.info(f"Successful login for {email}")
            return redirect(url_for('dashboard'))
            
        flash('Invalid email or password.', 'error')
        logger.warning(f"Failed login attempt for {email}")
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
            
        new_user = User(
            full_name=request.form.get('full_name'),
            email=email,
            password_hash=generate_password_hash(request.form.get('password')),
            department=request.form.get('department'),
            role='Student' # Default role for public registration
        )
        db.session.add(new_user)
        db.session.commit()
        db.session.add(AuditLog(action="New User Registered", user_id=new_user.id))
        db.session.commit()
        
        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    db.session.add(AuditLog(action="User Logout", user_id=current_user.id))
    db.session.commit()
    logout_user()
    flash('You have been securely logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.department = request.form.get('department')
        
        new_pass = request.form.get('new_password')
        if new_pass and len(new_pass) >= 8:
            current_user.password_hash = generate_password_hash(new_pass)
            flash('Password updated securely.', 'success')
            
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('profile'))
        
    return render_template('profile.html')

# ==========================================
# 6. DASHBOARD MULTIPLEXER
# ==========================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Routes users to their specific dashboard based on their role."""
    if current_user.role == 'Admin':
        stats = {
            'users': User.query.count(),
            'total_complaints': Complaint.query.count(),
            'active': Complaint.query.filter(Complaint.status.in_(['Pending', 'In Progress'])).count(),
            'resolved': Complaint.query.filter_by(status='Resolved').count()
        }
        logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
        return render_template('admin_dashboard.html', stats=stats, logs=logs)
        
    elif current_user.role == 'Tech':
        assigned = Complaint.query.filter_by(assigned_to=current_user.id).all()
        open_tickets = Complaint.query.filter_by(status='Pending').all()
        return render_template('tech_dashboard.html', assigned=assigned, open_tickets=open_tickets)
        
    else: # Default to Student
        user_complaints = Complaint.query.filter_by(user_id=current_user.id).order_by(Complaint.created_at.desc()).all()
        return render_template('student_dashboard.html', complaints=user_complaints)

@app.route('/admin_dashboard')
@login_required
@role_required('Admin')
def admin_dashboard_view():
    # 1. Get total counts
    total_users = User.query.count()
    total_complaints = Complaint.query.count()
    
    # 2. Calculate status dictionary for Pending/Resolved stats
    status_counts = db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all()
    status_dict = {status: count for status, count in status_counts}
    
    # 3. Calculate category distribution for the progress bars
    category_counts = db.session.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all()
    
    # 4. Get recent audit logs for the live timeline
    recent_activity = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(15).all()
        
    # Pass exactly the variables that the Tailwind HTML expects
    return render_template(
        'admin_dashboard.html', 
        total_users=total_users, 
        total_complaints=total_complaints,
        status_dict=status_dict,
        category_counts=category_counts,
        recent_activity=recent_activity
    )

@app.route('/tech_dashboard')
@login_required
@role_required('Tech', 'Admin')
def tech_dashboard_view():
    # Tech Queue Management
    assigned = Complaint.query.filter_by(assigned_to=current_user.id).filter(Complaint.status != 'Cancelled').order_by(
        db.case((Complaint.priority == 'Critical', 1), (Complaint.priority == 'High', 2), else_=3),
        Complaint.updated_at.desc()
    ).all()
    open_tickets = Complaint.query.filter_by(assigned_to=None, status='Pending').order_by(Complaint.created_at.desc()).all()
    return render_template('tech_dashboard.html', assigned=assigned, open_tickets=open_tickets)


# ==========================================
# 7. TICKET MANAGEMENT ROUTES
# ==========================================

@app.route('/complaint/submit', methods=['GET', 'POST'])
@login_required
def submit_complaint():
    if request.method == 'POST':
        # File handling
        image_filename = None
        if 'photo' in request.files:
            file = request.files['photo']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                image_filename = unique_name

        new_complaint = Complaint(
            title=request.form.get('title'),
            category=request.form.get('category'),
            priority=request.form.get('priority'),
            location=request.form.get('location'),
            description=request.form.get('description'),
            user_id=current_user.id,
            image_file=image_filename
        )
        db.session.add(new_complaint)
        db.session.flush() # Get ID
        
        # System Audit
        db.session.add(AuditLog(action="Ticket Created", user_id=current_user.id, complaint_id=new_complaint.id))
        
        # Notify Admins (Simulated)
        admins = User.query.filter_by(role='Admin').all()
        for admin in admins:
            create_notification(admin.id, f"New {new_complaint.priority} priority ticket: {new_complaint.title}", url_for('view_complaint', id=new_complaint.id))
            
        db.session.commit()
        flash('Issue reported successfully. A technician will review it shortly.', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('submit_complaint.html')

@app.route('/complaint/<int:id>', methods=['GET', 'POST'])
@login_required
def view_complaint(id):
    complaint = db.session.get(Complaint, id)
    if not complaint:
        abort(404)
        
    # Security check: Students can only view their own tickets
    if current_user.role == 'Student' and complaint.user_id != current_user.id:
        abort(403)

    if request.method == 'POST' and 'content' in request.form:
        if complaint.status in ['Resolved', 'Cancelled']:
            flash('Cannot comment on closed tickets.', 'error')
            return redirect(url_for('view_complaint', id=complaint.id))
            
        content = request.form.get('content')
        new_comment = Comment(content=content, user_id=current_user.id, complaint_id=complaint.id)
        db.session.add(new_comment)
        
        # Notifications logic
        if current_user.role in ['Admin', 'Tech']:
            create_notification(complaint.user_id, f"New update on your ticket: {complaint.title}", url_for('view_complaint', id=complaint.id))
        elif complaint.assigned_to:
            create_notification(complaint.assigned_to, f"User replied to ticket #{complaint.id}", url_for('view_complaint', id=complaint.id))
            
        db.session.commit()
        flash('Message posted.', 'success')
        return redirect(url_for('view_complaint', id=complaint.id))
        
    # Build Timeline (Logs + Comments sorted by time)
    logs = AuditLog.query.filter(AuditLog.complaint_id == complaint.id, AuditLog.action != 'Ticket Created').all()
    comments = Comment.query.filter_by(complaint_id=complaint.id).all()
    
    # Merge and sort, pushing creation log to bottom virtually
    creation_log = AuditLog.query.filter_by(complaint_id=complaint.id, action='Ticket Created').first()
    timeline = sorted(chain(logs, comments), key=lambda x: x.created_at, reverse=True)
    if creation_log: timeline.append(creation_log)
    
    return render_template('view_complaint.html', complaint=complaint, timeline=timeline)

@app.route('/complaint/<int:id>/update', methods=['POST'])
@login_required
@role_required('Admin', 'Tech')
def update_complaint(id):
    complaint = db.session.get(Complaint, id)
    if not complaint:
        abort(404)
        
    # Claim Ticket Logic
    if request.form.get('claim_ticket') == 'true' and current_user.role == 'Tech':
        if complaint.assigned_to and complaint.assigned_to != current_user.id:
            flash('Ticket already assigned to another technician.', 'error')
            return redirect(url_for('dashboard'))
            
        complaint.assigned_to = current_user.id
        db.session.add(AuditLog(action="Ticket Claimed", user_id=current_user.id, complaint_id=complaint.id))
        create_notification(complaint.user_id, f"A technician has been assigned to your ticket.", url_for('view_complaint', id=complaint.id))
        
    # Status Update Logic
    new_status = request.form.get('status')
    if new_status and new_status != complaint.status:
        valid_statuses = ['Pending', 'In Progress', 'Resolved', 'Cancelled']
        if new_status in valid_statuses:
            complaint.status = new_status
            if new_status == 'Resolved':
                complaint.resolved_at = datetime.utcnow()
            
            db.session.add(AuditLog(action=f"Status changed to: {new_status}", user_id=current_user.id, complaint_id=complaint.id))
            create_notification(complaint.user_id, f"Ticket status updated to {new_status}", url_for('view_complaint', id=complaint.id))
            
    db.session.commit()
    flash('Ticket successfully updated.', 'success')
    return redirect(url_for('view_complaint', id=complaint.id))

@app.route('/complaint/<int:id>/confirm', methods=['POST'])
@login_required
@role_required('Student')
def confirm_complaint(id):
    complaint = db.session.get(Complaint, id)

    if not complaint:
        abort(404)

    if complaint.user_id != current_user.id:
        abort(403)

    # FIX: Completed the previously incomplete logic here
    complaint.status = "Resolved"
    complaint.resolved_at = datetime.utcnow()
    
    db.session.add(AuditLog(action="Ticket Confirmed Resolved by Student", user_id=current_user.id, complaint_id=complaint.id))
    db.session.commit()
    flash('Ticket successfully confirmed and closed.', 'success')
    return redirect(url_for('view_complaint', id=complaint.id))

# ==========================================
# 8. UTILITY & ADMIN ROUTES
# ==========================================

@app.route('/notifications/<int:id>/read')
@login_required
def read_notification(id):
    notif = db.session.get(Notification, id)
    if notif and notif.user_id == current_user.id:
        notif.is_read = True
        db.session.commit()
        if notif.link:
            return redirect(notif.link)
    return redirect(url_for('dashboard'))

@app.route('/admin/users')
@login_required
@role_required('Admin')
def manage_users():
    users = User.query.order_by(User.role, User.full_name).all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/users/<int:id>/toggle', methods=['POST'])
@login_required
@role_required('Admin')
def toggle_user_status(id):
    if id == current_user.id:
        flash("You cannot suspend your own account.", "error")
        return redirect(url_for('manage_users'))
        
    user = db.session.get(User, id)
    if user:
        user.is_active = not user.is_active
        action_text = "Suspended" if not user.is_active else "Reactivated"
        db.session.add(AuditLog(action=f"User Account {action_text}: {user.email}", user_id=current_user.id))
        db.session.commit()
        flash(f"User {user.full_name} has been {action_text.lower()}.", "success")
        
    return redirect(url_for('manage_users'))

@app.route('/admin/export')
@login_required
@role_required('Admin')
def export_data():
    """Generates a CSV export of all complaints for external analytics."""
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Title', 'Category', 'Priority', 'Status', 'Reported_By', 'Assigned_To', 'Created_At', 'Resolved_At', 'Resolution_Time_Hours'])
    
    complaints = Complaint.query.all()
    for c in complaints:
        resolved_time = ""
        if c.resolved_at:
            delta = c.resolved_at - c.created_at
            resolved_time = round(delta.total_seconds() / 3600, 2)
            
        cw.writerow([
            c.id, c.title, c.category, c.priority, c.status,
            c.author.email if c.author else 'Unknown',
            c.assignee.email if c.assignee else 'Unassigned',
            c.created_at.strftime('%Y-%m-%d %H:%M'),
            c.resolved_at.strftime('%Y-%m-%d %H:%M') if c.resolved_at else '',
            resolved_time
        ])
        
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=campusfix_export_{datetime.now().strftime('%Y%m%d')}.csv"}
    )

# ==========================================
# 9. INVENTORY MANAGEMENT ROUTES
# ==========================================

@app.route('/inventory')
@login_required
@role_required('Admin', 'Tech')
def inventory():
    items = InventoryItem.query.order_by(InventoryItem.category, InventoryItem.item_name).all()
    return render_template('inventory.html', items=items)

@app.route('/inventory/add', methods=['POST'])
@login_required
@role_required('Admin')
def add_inventory():
    item = InventoryItem(
        item_name=request.form.get('item_name'),
        category=request.form.get('category'),
        quantity=int(request.form.get('quantity', 0))
    )
    db.session.add(item)
    db.session.add(AuditLog(action=f"Added new inventory item: {item.item_name}", user_id=current_user.id))
    db.session.commit()
    flash('Item added to inventory.', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/<int:id>/update', methods=['POST'])
@login_required
@role_required('Admin', 'Tech')
def update_inventory(id):
    item = db.session.get(InventoryItem, id)
    if not item:
        abort(404)
        
    try:
        amount = int(request.form.get('amount', 0))
        if amount == 0:
            return redirect(url_for('inventory'))
            
        # Prevent negative stock
        if item.quantity + amount < 0:
            flash(f"Insufficient stock for {item.item_name}. Current: {item.quantity}", 'error')
            return redirect(url_for('inventory'))
            
        item.quantity += amount
        if amount > 0:
            item.last_restocked = datetime.utcnow()
            
        action = "Restocked" if amount > 0 else "Used"
        db.session.add(AuditLog(action=f"{action} {abs(amount)} of {item.item_name}", user_id=current_user.id))
        db.session.commit()
        
        flash(f"Inventory for {item.item_name} updated successfully.", 'success')
    except ValueError:
        flash("Invalid quantity value.", "error")
        
    return redirect(url_for('inventory'))

# ==========================================
# 10. ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

# ==========================================
# 11. DATABASE SEEDER (Massive dummy data)
# ==========================================

def seed_database():
    """Injects comprehensive dummy data into the system for immediate testing."""
    with app.app_context():
        db.create_all()
        
        # Check if already seeded
        if User.query.count() > 0:
            logger.info("Database already populated. Skipping seeder.")
            return
            
        logger.info("Initializing massive database seed...")
        
        # Create Users
        users = [
            User(full_name='System Administrator', email='admin@campus.edu', password_hash=generate_password_hash('Admin@123'), role='Admin', department='IT/Facilities'),
            User(full_name='John Technician', email='tech1@campus.edu', password_hash=generate_password_hash('Tech@123'), role='Tech', department='Electrical'),
            User(full_name='Sarah Fixer', email='tech2@campus.edu', password_hash=generate_password_hash('Tech@123'), role='Tech', department='Plumbing'),
            User(full_name='Alice Student', email='student1@campus.edu', password_hash=generate_password_hash('Student@123'), role='Student', department='Computer Science'),
            User(full_name='Bob Undergraduate', email='student2@campus.edu', password_hash=generate_password_hash('Student@123'), role='Student', department='Business'),
        ]
        db.session.add_all(users)
        db.session.commit() # Commit to get IDs
        
        # Create Inventory
        inventory = [
            InventoryItem(item_name='LED Light Bulbs (60W)', category='Electrical', quantity=45),
            InventoryItem(item_name='Copper Wiring (Spool)', category='Electrical', quantity=12),
            InventoryItem(item_name='PVC Pipe (10ft)', category='Plumbing', quantity=30),
            InventoryItem(item_name='Pipe Sealant', category='Plumbing', quantity=4),
            InventoryItem(item_name='Air Filters (20x20)', category='HVAC', quantity=8),
            InventoryItem(item_name='Ethernet Cable (Cat6)', category='IT', quantity=50),
        ]
        db.session.add_all(inventory)
        db.session.commit()
        
        # Create Dummy Complaints (History and Active)
        past_date = datetime.utcnow() - timedelta(days=5)
        complaints = [
            Complaint(title='Leaking sink in Men\'s Restroom', category='Plumbing', priority='Medium', location='Building A, Floor 2', description='Water is constantly dripping from the middle sink, causing a puddle on the floor.', status='Resolved', user_id=users[3].id, assigned_to=users[2].id, created_at=past_date, resolved_at=past_date + timedelta(hours=4)),
            Complaint(title='Power outage in lab', category='Electrical', priority='Critical', location='Science Block, Room 304', description='Half the computers just shut off. Breaker might have tripped but it smells like burnt plastic.', status='In Progress', user_id=users[4].id, assigned_to=users[1].id, created_at=datetime.utcnow() - timedelta(hours=2)),
            Complaint(title='AC not blowing cold air', category='HVAC', priority='High', location='Library Main Hall', description='It is very humid and hot inside the main study area. The vents are just blowing room temperature air.', status='Pending', user_id=users[3].id, created_at=datetime.utcnow() - timedelta(minutes=45)),
            Complaint(title='Broken chair', category='Structural', priority='Low', location='Lecture Hall C', description='Seat 12 in row 4 has a missing leg.', status='Pending', user_id=users[4].id, created_at=datetime.utcnow() - timedelta(minutes=10)),
        ]
        db.session.add_all(complaints)
        db.session.commit()
        
        # Add Comments and Logs
        c = complaints[1] # The electrical one
        db.session.add(AuditLog(action="Ticket Created", user_id=c.user_id, complaint_id=c.id, created_at=c.created_at))
        db.session.add(AuditLog(action="Ticket Claimed", user_id=users[1].id, complaint_id=c.id, created_at=c.created_at + timedelta(minutes=15)))
        db.session.add(AuditLog(action="Status changed to: In Progress", user_id=users[1].id, complaint_id=c.id, created_at=c.created_at + timedelta(minutes=16)))
        db.session.add(Comment(content="I'm heading over now with the thermal camera to check the breakers.", user_id=users[1].id, complaint_id=c.id, created_at=c.created_at + timedelta(minutes=20)))
        
        db.session.commit()
        logger.info("Database successfully seeded with users, tickets, and inventory.")

# ==========================================
# 12. APPLICATION ENTRY POINT
# ==========================================

if __name__ == '__main__':
    # Build frontend
    initialize_templates()
    
    # Build and seed backend
    seed_database()
    
    # Run Enterprise Server
    logger.info("Starting CampusFIX Enterprise Server on http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)
