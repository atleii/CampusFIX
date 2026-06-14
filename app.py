"""
=============================================================================
CampusFIX Enterprise Monolith - Professional Pastel Light Mode
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
                   flash, abort, jsonify, Response, session)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, login_user, logout_user, 
                         login_required, current_user, UserMixin)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import func, desc

# ==========================================
# 1. APPLICATION CONFIGURATION & SETUP
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super_secret_campusfix_key_999')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///campusfix_tailwind.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

# Context processor for datetime
@app.context_processor
def inject_now():
    return {'datetime': datetime}

# ==========================================
# 2. DATABASE MODELS
# ==========================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Student') 
    department = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    complaints_filed = db.relationship('Complaint', foreign_keys='Complaint.user_id', backref='author', lazy=True)
    complaints_assigned = db.relationship('Complaint', foreign_keys='Complaint.assigned_to', backref='assignee', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True, order_by="desc(Notification.created_at)")

class Complaint(db.Model):
    __tablename__ = 'complaints'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), nullable=False) 
    location = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='Pending', index=True)
    image_file = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    comments = db.relationship('Comment', backref='complaint', lazy=True, cascade="all, delete-orphan")
    audit_logs = db.relationship('AuditLog', backref='complaint', lazy=True, cascade="all, delete-orphan")

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=False)
    
    user = db.relationship('User', backref='comments')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    complaint_id = db.Column(db.Integer, db.ForeignKey('complaints.id'), nullable=True)
    
    user = db.relationship('User')

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

class InventoryItem(db.Model):
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
# 3. RBAC DECORATORS 
# ==========================================

def role_required(*roles):
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
    notif = Notification(user_id=user_id, message=message, link=link)
    db.session.add(notif)


# ==========================================
# 4. TEMPLATE AUTO-GENERATOR (LIGHT/PASTEL UI UPDATE)
# ==========================================

def initialize_templates():
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
    <title>CampusFix Enterprise</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .custom-scrollbar::-webkit-scrollbar { width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: #f8fafc; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 font-sans antialiased min-h-screen flex flex-col selection:bg-blue-200 selection:text-blue-900">

    <nav class="bg-white/90 backdrop-blur-md border-b border-slate-200 px-6 py-4 sticky top-0 z-50 shadow-sm">
        <div class="max-w-7xl mx-auto flex justify-between items-center">
            
            <a href="/" class="flex items-center gap-3 group">
                <div class="bg-blue-600 text-white font-black rounded-xl px-3 py-1.5 shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform duration-300">CF</div>
                <span class="font-bold text-2xl tracking-tight text-slate-800">CampusFix</span>
            </a>
            
            {% if current_user.is_authenticated %}
            <div class="flex items-center gap-6">
                {% if current_user.role == 'Admin' %}
                    <a href="{{ url_for('admin_dashboard') }}" class="text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors">Admin Panel</a>
                    <a href="{{ url_for('manage_users') }}" class="text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors">Users</a>
                    <a href="{{ url_for('inventory') }}" class="text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors">Inventory</a>
                {% elif current_user.role == 'Tech' %}
                    <a href="{{ url_for('dashboard') }}" class="text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors">Tech Board</a>
                    <a href="{{ url_for('inventory') }}" class="text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors">Inventory</a>
                {% else %}
                    <a href="{{ url_for('dashboard') }}" class="text-sm font-semibold text-slate-600 hover:text-blue-600 transition-colors">My Tickets</a>
                {% endif %}

                <div class="h-6 w-px bg-slate-300 mx-1"></div>
                
                <div class="relative group cursor-pointer pt-1">
                    <div class="text-slate-500 hover:text-blue-600 transition-colors flex items-center">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path></svg>
                        
                        {% set unread = current_user.notifications|selectattr("is_read", "equalto", false)|list|length %}
                        {% if unread > 0 %}
                        <span class="absolute -top-1 -right-2 bg-rose-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full shadow-md animate-pulse">{{ unread }}</span>
                        {% endif %}
                    </div>
                    
                    <div class="absolute right-0 mt-4 w-80 bg-white border border-slate-200 rounded-2xl shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-300 transform origin-top group-hover:translate-y-1 z-50 overflow-hidden">
                        <div class="p-4 bg-slate-50 border-b border-slate-200">
                            <h3 class="text-sm font-bold text-slate-800 flex items-center gap-2">
                                <span class="w-2 h-2 rounded-full bg-blue-500"></span> Notifications
                            </h3>
                        </div>
                        <div class="max-h-72 overflow-y-auto custom-scrollbar">
                            {% for notif in current_user.notifications[:6] %}
                            <a href="{{ url_for('read_notification', id=notif.id) }}" class="block p-4 border-b border-slate-100 hover:bg-slate-50 transition-colors {% if not notif.is_read %}bg-blue-50/50 border-l-4 border-l-blue-500{% else %}border-l-4 border-l-transparent{% endif %}">
                                <p class="text-sm {% if not notif.is_read %}text-slate-900 font-semibold{% else %}text-slate-600{% endif %}">{{ notif.message }}</p>
                                <p class="text-[10px] font-bold text-slate-400 mt-1.5 uppercase tracking-wide">{{ notif.created_at.strftime('%b %d, %H:%M') }}</p>
                            </a>
                            {% else %}
                            <div class="p-8 text-center text-sm text-slate-400 flex flex-col items-center">
                                <svg class="w-8 h-8 mb-2 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path></svg>
                                All caught up!
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                </div>

                <a href="{{ url_for('profile') }}" class="flex items-center gap-3 group ml-2 bg-slate-50 hover:bg-slate-100 px-3 py-1.5 rounded-full border border-slate-200 transition-colors">
                    <div class="w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold shadow-sm">
                        {{ current_user.full_name[0] }}
                    </div>
                    <span class="text-sm font-bold text-slate-700 group-hover:text-blue-600 transition">{{ current_user.full_name.split(' ')[0] }}</span>
                </a>
                <a href="{{ url_for('logout') }}" class="text-sm font-semibold text-slate-500 hover:text-rose-500 transition ml-2">Logout</a>
            </div>
            {% endif %}
        </div>
    </nav>

    <div class="max-w-4xl mx-auto w-full mt-6 px-6 fixed top-20 left-1/2 -translate-x-1/2 z-50 pointer-events-none" id="flash-container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="pointer-events-auto p-4 mb-3 rounded-xl text-sm font-bold shadow-lg flex items-center gap-3 transform transition-all
                        {% if category == 'error' %}bg-rose-50 text-rose-800 border border-rose-200
                        {% elif category == 'warning' %}bg-amber-50 text-amber-800 border border-amber-200
                        {% else %}bg-emerald-50 text-emerald-800 border border-emerald-200{% endif %}">
                        {{ message }}
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>

    <main class="flex-grow p-6">
        {% block content %}{% endblock %}
    </main>
    
    <footer class="bg-white text-slate-500 text-sm font-medium text-center py-6 border-t border-slate-200 mt-auto">
        <div class="flex items-center justify-center gap-2">
            <span class="w-2 h-2 rounded-full bg-blue-500"></span>
            &copy; {{ datetime.utcnow().year }} CampusFIX Enterprise.
        </div>
    </footer>
</body>
</html>""",

        # ------------------------------------------------------------------
        # ADMIN DASHBOARD
        # ------------------------------------------------------------------
        "admin_dashboard.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-7xl mx-auto mt-4 space-y-8">
    
    <div class="flex justify-between items-end">
        <div>
            <h1 class="text-3xl font-black text-slate-800 tracking-tight">System Overview</h1>
            <p class="text-sm font-medium text-slate-500 mt-1">Real-time campus infrastructure analytics.</p>
        </div>
        <div>
            <a href="{{ url_for('export_data') }}" class="px-5 py-2.5 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 rounded-xl text-sm font-bold transition-all shadow-sm flex items-center gap-2 hover:shadow-md">
                <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Export CSV
            </a>
        </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="bg-blue-50 p-6 rounded-2xl border border-blue-100 shadow-sm relative overflow-hidden group transform hover:-translate-y-1 transition-all duration-300">
            <div class="absolute -right-6 -top-6 w-32 h-32 bg-white/40 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-700"></div>
            <p class="text-blue-600 text-xs font-bold uppercase tracking-wider mb-2">Total Users</p>
            <h3 class="text-4xl font-black text-blue-900 drop-shadow-sm">{{ total_users }}</h3>
        </div>
        
        <div class="bg-purple-50 p-6 rounded-2xl border border-purple-100 shadow-sm relative overflow-hidden group transform hover:-translate-y-1 transition-all duration-300">
            <div class="absolute -right-6 -top-6 w-32 h-32 bg-white/40 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-700"></div>
            <p class="text-purple-600 text-xs font-bold uppercase tracking-wider mb-2">Total Reports</p>
            <h3 class="text-4xl font-black text-purple-900 drop-shadow-sm">{{ total_complaints }}</h3>
        </div>

        <div class="bg-amber-50 p-6 rounded-2xl border border-amber-100 shadow-sm relative overflow-hidden group transform hover:-translate-y-1 transition-all duration-300">
            <div class="absolute -right-6 -top-6 w-32 h-32 bg-white/40 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-700"></div>
            <p class="text-amber-600 text-xs font-bold uppercase tracking-wider mb-2">Active / Pending</p>
            <h3 class="text-4xl font-black text-amber-900 drop-shadow-sm">{{ status_dict.get('Pending', 0) + status_dict.get('In Progress', 0) }}</h3>
        </div>

        <div class="bg-emerald-50 p-6 rounded-2xl border border-emerald-100 shadow-sm relative overflow-hidden group transform hover:-translate-y-1 transition-all duration-300">
            <div class="absolute -right-6 -top-6 w-32 h-32 bg-white/40 rounded-full blur-2xl group-hover:scale-150 transition-transform duration-700"></div>
            <p class="text-emerald-600 text-xs font-bold uppercase tracking-wider mb-2">Successfully Resolved</p>
            <h3 class="text-4xl font-black text-emerald-900 drop-shadow-sm">{{ status_dict.get('Resolved', 0) }}</h3>
        </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        <div class="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div class="p-6 border-b border-slate-100 bg-slate-50/50">
                <h3 class="text-base font-bold text-slate-800 flex items-center gap-2">
                    <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
                    Issues by Category
                </h3>
            </div>
            <table class="w-full text-left text-sm">
                <thead class="bg-slate-50 text-slate-500 text-xs uppercase font-bold tracking-wider border-b border-slate-200">
                    <tr>
                        <th class="px-6 py-4">Category Name</th>
                        <th class="px-6 py-4 text-right">Volume</th>
                        <th class="px-6 py-4 text-right w-2/5">Distribution</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    {% for category, count in category_counts %}
                    <tr class="hover:bg-slate-50 transition-colors group">
                        <td class="px-6 py-5 font-bold text-slate-700">{{ category }}</td>
                        <td class="px-6 py-5 text-right font-medium text-slate-500">{{ count }}</td>
                        <td class="px-6 py-5 text-right">
                            <div class="flex items-center justify-end gap-4">
                                <span class="text-slate-500 font-bold text-xs w-8">{{ ((count / total_complaints) * 100) | round(1) if total_complaints > 0 else 0 }}%</span>
                                <div class="w-32 h-2.5 bg-slate-100 rounded-full overflow-hidden shadow-inner border border-slate-200/50">
                                    <div class="h-full bg-blue-400 rounded-full" style="width: {{ (count / total_complaints) * 100 if total_complaints > 0 else 0 }}%"></div>
                                </div>
                            </div>
                        </td>
                    </tr>
                    {% else %}
                    <tr><td colspan="3" class="px-6 py-12 text-center text-slate-400 font-medium">No data available yet.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col h-[450px]">
            <div class="p-6 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center z-10">
                <h3 class="text-base font-bold text-slate-800 flex items-center gap-2">
                    <span class="relative flex h-3 w-3">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
                    </span>
                    Live Activity
                </h3>
            </div>
            <div class="flex-1 overflow-y-auto p-6 custom-scrollbar space-y-5">
                {% for log in recent_activity %}
                <div class="flex gap-4 group">
                    <div class="w-9 h-9 rounded-full bg-slate-50 border border-slate-200 flex items-center justify-center shrink-0 text-slate-400">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    </div>
                    <div>
                        <p class="text-sm font-semibold text-slate-700 leading-snug">{{ log.action }}</p>
                        <p class="text-[11px] font-bold text-slate-400 mt-1 uppercase tracking-wide">
                            {% if log.user %}By <span class="text-blue-500">{{ log.user.full_name }}</span> &bull;{% endif %}
                            {{ log.created_at.strftime('%H:%M, %b %d') }}
                        </p>
                    </div>
                </div>
                {% else %}
                <div class="flex flex-col items-center justify-center h-full text-slate-400">
                    <svg class="w-12 h-12 mb-3 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <p class="text-sm font-medium">No recent activity.</p>
                </div>
                {% endfor %}
            </div>
        </div>

    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # MAIN DASHBOARD
        # ------------------------------------------------------------------
        "dashboard.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
    
    <div class="lg:col-span-1">
        <div class="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm sticky top-24 border-t-4 border-t-blue-500">
            <h3 class="text-xl font-black text-slate-800 mb-6 flex items-center gap-2">
                <svg class="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                Report an Issue
            </h3>
            <form action="{{ url_for('submit_complaint') }}" method="POST" class="space-y-5">
                <div>
                    <label class="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Category</label>
                    <select name="category" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all shadow-inner">
                        <option value="Electrical">⚡ Electrical / Lighting</option>
                        <option value="Plumbing">💧 Plumbing / Water</option>
                        <option value="HVAC">❄️ HVAC (Heating/AC)</option>
                        <option value="Furniture">🪑 Furniture / Structural</option>
                        <option value="IT/Network">💻 IT / Network</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Location</label>
                    <input type="text" name="location" placeholder="e.g. Room 302, Library" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all shadow-inner placeholder-slate-400">
                </div>
                <div>
                    <label class="block text-xs font-bold text-slate-500 uppercase tracking-wide mb-2">Description</label>
                    <textarea name="description" rows="4" placeholder="Describe the problem in detail..." required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all shadow-inner placeholder-slate-400"></textarea>
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold py-3.5 rounded-xl transition-all shadow-md transform hover:-translate-y-0.5 focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
                    Submit Report &rarr;
                </button>
            </form>
        </div>
    </div>

    <div class="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden h-fit">
        <div class="px-6 py-5 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
            <h3 class="text-lg font-bold text-slate-800 flex items-center gap-2">
                <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                {% if current_user.role in ['Admin', 'Tech'] %}Global Ticket Queue{% else %}My Active Complaints{% endif %}
            </h3>
        </div>
        
        <div class="overflow-x-auto min-h-[500px]">
            <table class="w-full text-left text-sm">
                <thead class="bg-slate-50 text-slate-500 text-xs uppercase font-bold tracking-wider border-b border-slate-200">
                    <tr>
                        <th class="px-6 py-4">Issue Details</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4 text-right">Action</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    {% for complaint in complaints %}
                    <tr class="hover:bg-slate-50 transition-colors group">
                        <td class="px-6 py-5">
                            <div class="flex items-center gap-2 mb-1.5">
                                <span class="text-xs font-bold font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">#{{ complaint.id }}</span>
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-blue-50 text-blue-600 border border-blue-100">{{ complaint.category }}</span>
                            </div>
                            <p class="font-bold text-slate-800 text-base">{{ complaint.location }}</p>
                            <p class="text-slate-500 text-sm mt-1 truncate max-w-[250px] font-medium">{{ complaint.description }}</p>
                        </td>
                        <td class="px-6 py-5">
                            {% if complaint.status == 'Pending' %}
                                <span class="px-3 py-1.5 rounded-full text-xs font-bold bg-rose-100 text-rose-700 border border-rose-200 inline-flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span>Pending</span>
                            {% elif complaint.status == 'In Progress' %}
                                <span class="px-3 py-1.5 rounded-full text-xs font-bold bg-amber-100 text-amber-700 border border-amber-200 inline-flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></span>In Progress</span>
                            {% else %}
                                <span class="px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 border border-emerald-200 inline-flex items-center gap-1.5"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Resolved</span>
                            {% endif %}
                        </td>
                        <td class="px-6 py-5 text-right">
                            {% if current_user.role in ['Admin', 'Tech'] %}
                            <form action="{{ url_for('update_status', complaint_id=complaint.id) }}" method="POST" class="inline-flex flex-col gap-3 items-end">
                                <select name="status" class="bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 text-xs font-bold text-slate-700 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner cursor-pointer" onchange="this.form.submit()">
                                    <option value="Pending" {% if complaint.status == 'Pending' %}selected{% endif %}>Pending</option>
                                    <option value="In Progress" {% if complaint.status == 'In Progress' %}selected{% endif %}>In Progress</option>
                                    <option value="Resolved" {% if complaint.status == 'Resolved' %}selected{% endif %}>Resolved</option>
                                </select>
                                <a href="{{ url_for('view_complaint', id=complaint.id) }}" class="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors flex items-center gap-1">Open Full Ticket <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg></a>
                            </form>
                            {% else %}
                                <a href="{{ url_for('view_complaint', id=complaint.id) }}" class="bg-white hover:bg-slate-50 text-slate-700 font-bold px-4 py-2 rounded-lg text-xs transition-all shadow-sm border border-slate-200">View Details</a>
                            {% endif %}
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="3" class="px-6 py-20 text-center text-slate-400">
                            <div class="bg-slate-50 w-20 h-20 rounded-full flex items-center justify-center mx-auto mb-4 border border-slate-100">
                                <svg class="w-10 h-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
                            </div>
                            <p class="font-bold text-lg text-slate-600">Queue is Empty</p>
                            <p class="text-sm mt-1">No complaints found at the moment.</p>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # DETAILED TICKET VIEW
        # ------------------------------------------------------------------
        "view_complaint.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-6xl mx-auto">
    <div class="mb-6">
        <a href="{{ url_for('dashboard') }}" class="inline-flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-slate-800 transition-colors bg-white px-4 py-2 rounded-lg border border-slate-200 shadow-sm">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
            Back to Dashboard
        </a>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div class="lg:col-span-1 space-y-6">
            <div class="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm relative overflow-hidden">
                <div class="absolute top-0 left-0 w-full h-1.5 
                    {% if complaint.status == 'Resolved' %}bg-emerald-500
                    {% elif complaint.status == 'In Progress' %}bg-amber-500
                    {% else %}bg-rose-500{% endif %}">
                </div>

                <div class="flex justify-between items-start mb-6 mt-2">
                    <h2 class="text-2xl font-black text-slate-800">Ticket <span class="text-slate-400 font-mono">#{{ complaint.id }}</span></h2>
                    {% if complaint.status == 'Resolved' %}
                        <span class="px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 border border-emerald-200">Resolved</span>
                    {% elif complaint.status == 'In Progress' %}
                        <span class="px-3 py-1.5 rounded-full text-xs font-bold bg-amber-100 text-amber-700 border border-amber-200">In Progress</span>
                    {% else %}
                        <span class="px-3 py-1.5 rounded-full text-xs font-bold bg-rose-100 text-rose-700 border border-rose-200">Pending</span>
                    {% endif %}
                </div>
                
                <div class="space-y-5">
                    <div>
                        <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Category & Location</p>
                        <p class="text-base text-slate-800 font-bold flex items-center gap-2">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-blue-50 text-blue-600 border border-blue-100">{{ complaint.category }}</span> 
                            {{ complaint.location }}
                        </p>
                    </div>
                    <div>
                        <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Description</p>
                        <div class="bg-slate-50 p-4 rounded-xl border border-slate-200 shadow-inner">
                            <p class="text-sm text-slate-700 whitespace-pre-wrap font-medium leading-relaxed">{{ complaint.description }}</p>
                        </div>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-4 pt-5 border-t border-slate-100">
                        <div>
                            <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Reported By</p>
                            <div class="flex items-center gap-2.5">
                                <div class="w-7 h-7 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-xs font-bold text-slate-600">
                                    {{ complaint.author.full_name[0] }}
                                </div>
                                <p class="text-sm font-bold text-slate-700">{{ complaint.author.full_name.split()[0] }}</p>
                            </div>
                        </div>
                        <div>
                            <p class="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-2">Assigned Solver</p>
                            {% if complaint.assigned_to %}
                            <div class="flex items-center gap-2">
                                <span class="w-2 h-2 rounded-full bg-blue-500"></span>
                                <p class="text-sm text-blue-600 font-bold truncate">{{ complaint.assignee.full_name.split()[0] }}</p>
                            </div>
                            {% else %}
                            <p class="text-sm text-rose-500 font-bold italic flex items-center gap-1.5">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                Unassigned
                            </p>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>

            {% if current_user.role in ['Admin', 'Tech'] and complaint.status != 'Resolved' %}
            <div class="bg-white rounded-2xl border border-blue-200 p-6 shadow-sm relative overflow-hidden group">
                <div class="absolute -right-10 -top-10 w-32 h-32 bg-blue-50 rounded-full blur-2xl transition-colors duration-500"></div>
                <h3 class="text-sm font-black text-slate-800 mb-5 flex items-center gap-2 uppercase tracking-wide">
                    <svg class="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    Action Panel
                </h3>
                
                <form action="{{ url_for('update_complaint', id=complaint.id) }}" method="POST" class="space-y-5 relative z-10">
                    
                    {% if not complaint.assigned_to and current_user.role == 'Tech' %}
                    <label class="flex items-center gap-3 p-4 bg-blue-50 border border-blue-200 rounded-xl cursor-pointer hover:bg-blue-100 transition-colors shadow-inner">
                        <input type="checkbox" name="claim_ticket" value="true" class="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer">
                        <span class="text-sm text-blue-700 font-bold">Claim this ticket</span>
                    </label>
                    {% endif %}

                    {% if current_user.role == 'Admin' %}
                    <div>
                        <label class="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Assign Solver</label>
                        <select name="assigned_to" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
                            <option value="">-- Unassigned --</option>
                            {% for solver in solvers %}
                                <option value="{{ solver.id }}" {% if complaint.assigned_to == solver.id %}selected{% endif %}>
                                    {{ solver.full_name }} ({{ solver.role }})
                                </option>
                            {% endfor %}
                        </select>
                    </div>
                    {% endif %}
                    
                    <div>
                        <label class="block text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Update Status</label>
                        <select name="status" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
                            <option value="{{ complaint.status }}" selected>Current: {{ complaint.status }}</option>
                            {% if complaint.status == 'Pending' %}
                                <option value="In Progress">Move to In Progress</option>
                            {% elif complaint.status == 'In Progress' %}
                                <option value="Pending">Revert to Pending</option>
                            {% endif %}
                            <option value="Resolved">Mark as Resolved</option>
                        </select>
                    </div>
                    <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold py-3 rounded-xl transition-all shadow-md transform hover:-translate-y-0.5 focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
                        Apply Changes
                    </button>
                </form>
            </div>
            {% endif %}
        </div>

        <div class="lg:col-span-2 bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col h-[700px] overflow-hidden">
            <div class="px-6 py-5 border-b border-slate-100 bg-slate-50/50">
                <h3 class="text-lg font-black text-slate-800 flex items-center gap-2">
                    <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    Activity Timeline
                </h3>
            </div>
            
            <div class="flex-1 overflow-y-auto p-8 custom-scrollbar space-y-8 bg-slate-50/30">
                {% for item in timeline %}
                    <div class="relative pl-8 border-l-2 border-slate-200">
                        <div class="absolute w-4 h-4 bg-white border-2 border-blue-500 rounded-full -left-[9px] top-1"></div>
                        
                        <div class="mb-2 flex items-center gap-3">
                            <span class="text-[11px] font-bold text-slate-400 uppercase tracking-widest">{{ item.created_at.strftime('%b %d, %I:%M %p') }}</span>
                        </div>
                        
                        {% if item.__class__.__name__ == 'AuditLog' %}
                            <div class="inline-block bg-slate-50 border border-slate-200 rounded-lg px-4 py-2.5 shadow-sm">
                                <p class="text-xs font-bold text-slate-600 flex items-center gap-2">
                                    <svg class="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                    {{ item.action }}
                                </p>
                            </div>
                        {% else %}
                            <div class="bg-white border border-slate-200 rounded-xl p-5 mt-2 shadow-sm relative overflow-hidden group {% if item.user.role in ['Admin', 'Tech'] %}border-l-4 border-l-blue-500{% endif %}">
                                
                                <div class="flex items-center gap-3 mb-3 relative z-10">
                                    <div class="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-xs font-bold text-slate-600">
                                        {{ item.user.full_name[0] }}
                                    </div>
                                    <div>
                                        <span class="font-bold text-sm text-slate-800 block">{{ item.user.full_name }}</span>
                                        <span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 uppercase tracking-wider inline-block mt-0.5">{{ item.user.role }}</span>
                                    </div>
                                </div>
                                <p class="text-sm font-medium text-slate-600 leading-relaxed relative z-10">{{ item.content }}</p>
                            </div>
                        {% endif %}
                    </div>
                {% endfor %}
            </div>
            
            {% if complaint.status != 'Resolved' %}
            <div class="p-6 border-t border-slate-100 bg-slate-50">
                <form action="{{ url_for('view_complaint', id=complaint.id) }}" method="POST" class="flex gap-3">
                    <input type="text" name="content" placeholder="Type a message or update..." required class="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner placeholder-slate-400">
                    <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl text-sm font-bold transition-all shadow-md transform hover:-translate-y-0.5 focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 flex items-center gap-2">
                        Send <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
                    </button>
                </form>
            </div>
            {% else %}
            <div class="p-6 border-t border-slate-100 bg-slate-50 text-center flex flex-col items-center justify-center">
                <div class="w-10 h-10 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mb-2">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                </div>
                <p class="text-sm font-bold text-slate-500">This ticket is resolved and permanently closed.</p>
            </div>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # USER MANAGEMENT
        # ------------------------------------------------------------------
        "manage_users.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-6xl mx-auto">
    <div class="flex justify-between items-center mb-8">
        <h2 class="text-3xl font-black text-slate-800 tracking-tight">User Directory</h2>
    </div>
    
    <div class="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
                <thead class="bg-slate-50 text-slate-500 text-xs uppercase font-bold tracking-wider border-b border-slate-200">
                    <tr>
                        <th class="px-6 py-4">Name</th>
                        <th class="px-6 py-4">Email</th>
                        <th class="px-6 py-4">Role</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4 text-right">Action</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    {% for u in users %}
                    <tr class="hover:bg-slate-50 transition-colors group">
                        <td class="px-6 py-5 font-bold text-slate-700 flex items-center gap-3">
                            <div class="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-xs text-slate-600">{{ u.full_name[0] }}</div>
                            {{ u.full_name }}
                        </td>
                        <td class="px-6 py-5 text-slate-500 font-medium">{{ u.email }}</td>
                        <td class="px-6 py-5">
                            <span class="px-3 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-wider border {% if u.role == 'Admin' %}bg-purple-50 text-purple-600 border-purple-200{% elif u.role == 'Tech' %}bg-blue-50 text-blue-600 border-blue-200{% else %}bg-slate-100 text-slate-600 border-slate-200{% endif %}">
                                {{ u.role }}
                            </span>
                        </td>
                        <td class="px-6 py-5">
                            {% if u.is_active %}
                                <span class="text-emerald-600 text-xs font-bold flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-emerald-500"></span> Active</span>
                            {% else %}
                                <span class="text-rose-600 text-xs font-bold flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-rose-500"></span> Suspended</span>
                            {% endif %}
                        </td>
                        <td class="px-6 py-5 text-right">
                            {% if u.id != current_user.id %}
                            <form action="{{ url_for('toggle_user_status', id=u.id) }}" method="POST" class="inline">
                                <button type="submit" class="text-xs font-bold px-4 py-2 rounded-lg border transition-all transform hover:-translate-y-0.5 {% if u.is_active %}bg-rose-50 border-rose-200 text-rose-600 hover:bg-rose-600 hover:text-white hover:border-rose-600 shadow-sm{% else %}bg-emerald-50 border-emerald-200 text-emerald-600 hover:bg-emerald-600 hover:text-white hover:border-emerald-600 shadow-sm{% endif %}">
                                    {% if u.is_active %}Suspend{% else %}Reactivate{% endif %}
                                </button>
                            </form>
                            {% else %}
                            <span class="text-xs font-bold text-slate-400 italic">You</span>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # INVENTORY
        # ------------------------------------------------------------------
        "inventory.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-7xl mx-auto">
    <div class="flex justify-between items-end mb-8">
        <h2 class="text-3xl font-black text-slate-800 tracking-tight">Parts & Inventory</h2>
        {% if current_user.role == 'Admin' %}
        <button onclick="document.getElementById('addModal').classList.remove('hidden')" class="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-all shadow-md flex items-center gap-2 transform hover:-translate-y-0.5">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg> Add New Item
        </button>
        {% endif %}
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
        {% for item in items %}
        <div class="bg-white p-6 rounded-2xl border shadow-sm transition-all duration-300 transform hover:-translate-y-1 hover:shadow-lg {% if item.quantity < 5 %}border-rose-200 hover:border-rose-300{% else %}border-slate-200 hover:border-blue-200{% endif %} relative overflow-hidden group">
            
            <div class="flex justify-between items-start mb-5 relative z-10">
                <span class="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded bg-slate-100 text-slate-500 border border-slate-200">{{ item.category }}</span>
                {% if item.quantity < 5 %}
                <span class="text-[10px] font-bold text-rose-700 flex items-center gap-1 bg-rose-100 px-2 py-1 rounded border border-rose-200 animate-pulse">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg> Low Stock
                </span>
                {% endif %}
            </div>
            
            <h3 class="text-lg font-black text-slate-800 mb-1 relative z-10 truncate">{{ item.item_name }}</h3>
            
            <div class="flex items-end gap-2 mb-6 relative z-10">
                <span class="text-5xl font-black {% if item.quantity < 5 %}text-rose-600{% else %}text-slate-800{% endif %}">{{ item.quantity }}</span>
                <span class="text-xs font-bold text-slate-400 pb-1.5 uppercase tracking-wide">units</span>
            </div>
            
            <div class="pt-5 border-t border-slate-100 relative z-10">
                <form action="{{ url_for('update_inventory', id=item.id) }}" method="POST" class="flex gap-3">
                    {% if current_user.role == 'Tech' %}
                        <input type="hidden" name="amount" value="-1">
                        <button type="submit" class="w-full bg-slate-50 border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-bold py-2.5 rounded-xl transition-all shadow-sm active:scale-95">Mark 1 Used</button>
                    {% else %}
                        <input type="number" name="amount" placeholder="+ qty" required class="w-20 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs font-bold text-slate-800 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 focus:outline-none shadow-inner placeholder-slate-400 text-center">
                        <button type="submit" class="flex-1 bg-white hover:bg-blue-50 border border-slate-200 hover:border-blue-200 text-blue-600 hover:text-blue-700 text-xs font-bold py-2 rounded-xl transition-all shadow-sm active:scale-95">Restock</button>
                    {% endif %}
                </form>
            </div>
        </div>
        {% else %}
        <div class="col-span-full py-20 text-center text-slate-500 bg-white rounded-3xl border border-slate-200 shadow-sm">
            <div class="bg-slate-50 w-24 h-24 rounded-full flex items-center justify-center mx-auto mb-5 border border-slate-100">
                <svg class="w-10 h-10 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"></path></svg>
            </div>
            <p class="font-bold text-xl text-slate-700 mb-1">Inventory is empty</p>
            <p class="text-sm">Click "Add New Item" to start tracking parts.</p>
        </div>
        {% endfor %}
    </div>
</div>

<div id="addModal" class="hidden fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex justify-center items-center z-50">
    <div class="bg-white w-full max-w-md p-8 rounded-3xl border border-slate-200 shadow-2xl transform transition-all">
        <div class="flex justify-between items-center mb-6">
            <h3 class="text-xl font-black text-slate-800">Add Inventory Item</h3>
            <button onclick="document.getElementById('addModal').classList.add('hidden')" class="text-slate-400 hover:text-slate-600 bg-slate-50 hover:bg-slate-100 w-8 h-8 rounded-full flex items-center justify-center transition-colors">&times;</button>
        </div>
        <form action="{{ url_for('add_inventory') }}" method="POST" class="space-y-5">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Item Name</label>
                <input type="text" name="item_name" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Category</label>
                <select name="category" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
                    <option value="Electrical">Electrical</option>
                    <option value="Plumbing">Plumbing</option>
                    <option value="HVAC">HVAC</option>
                    <option value="Hardware">Hardware/Tools</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Initial Quantity</label>
                <input type="number" name="quantity" min="0" value="0" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold py-3.5 rounded-xl transition-all shadow-md transform hover:-translate-y-0.5 mt-2">Add to Database</button>
        </form>
    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # PROFILE 
        # ------------------------------------------------------------------
        "profile.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-2xl mx-auto mt-12">
    <div class="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden">
        
        <div class="p-10 border-b border-slate-100 text-center relative overflow-hidden bg-slate-50/50">
            <div class="w-28 h-28 mx-auto rounded-full bg-blue-50 border-4 border-white flex items-center justify-center text-4xl font-black text-blue-600 relative z-10 shadow-md">
                {{ current_user.full_name[0] }}
            </div>
            <h2 class="text-3xl font-black text-slate-800 mt-6 relative z-10">{{ current_user.full_name }}</h2>
            <p class="text-sm font-bold text-slate-500 mt-2 relative z-10 flex items-center justify-center gap-3">
                <span>{{ current_user.email }}</span> 
                <span class="w-1.5 h-1.5 rounded-full bg-slate-300"></span> 
                <span class="px-2.5 py-0.5 bg-white rounded border border-slate-200 text-blue-600">{{ current_user.role }}</span>
            </p>
        </div>
        
        <div class="p-10">
            <h3 class="text-[11px] font-black text-slate-400 mb-6 uppercase tracking-widest flex items-center gap-2">
                <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
                Personal Details
            </h3>
            <form action="{{ url_for('profile') }}" method="POST" class="space-y-6">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Full Name</label>
                        <input type="text" name="full_name" value="{{ current_user.full_name }}" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Department / Major</label>
                        <input type="text" name="department" value="{{ current_user.department or '' }}" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
                    </div>
                </div>
                
                <div class="pt-8 border-t border-slate-100 mt-8">
                    <h3 class="text-[11px] font-black text-slate-400 mb-6 uppercase tracking-widest flex items-center gap-2">
                        <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                        Security
                    </h3>
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">New Password <span class="text-slate-400 normal-case tracking-normal">(leave blank to keep current)</span></label>
                        <input type="password" name="new_password" class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner">
                    </div>
                </div>
                
                <div class="pt-8 mt-8 text-right">
                    <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3.5 rounded-xl text-sm font-bold transition-all shadow-md transform hover:-translate-y-0.5">Save Changes</button>
                </div>
            </form>
        </div>
    </div>
</div>
{% endblock %}""",

        # ------------------------------------------------------------------
        # LOGIN & REGISTER
        # ------------------------------------------------------------------
        "login.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-md mx-auto mt-16 relative">
    
    <div class="bg-white p-10 rounded-3xl border border-slate-200 shadow-xl relative">
        <div class="text-center mb-10">
            <div class="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-6 border border-blue-100">
                <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
            </div>
            <h2 class="text-3xl font-black text-slate-800 tracking-tight">Welcome Back</h2>
            <p class="text-sm font-medium text-slate-500 mt-2">Sign in to your CampusFIX account</p>
        </div>
        
        <form method="POST" action="{{ url_for('login') }}" class="space-y-6">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Email Address</label>
                <input type="email" name="email" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner transition-colors">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Password</label>
                <input type="password" name="password" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner transition-colors">
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold py-4 rounded-xl transition-all shadow-md transform hover:-translate-y-0.5 mt-2">
                Secure Sign In &rarr;
            </button>
        </form>
        
        <div class="mt-8 text-center pt-6 border-t border-slate-100">
            <p class="text-sm font-medium text-slate-500">Don't have an account? <a href="{{ url_for('register') }}" class="text-blue-600 hover:text-blue-700 transition-colors font-bold">Register</a></p>
        </div>
    </div>
</div>
{% endblock %}""",

        "register.html": """{% extends "base.html" %}
{% block content %}
<div class="max-w-md mx-auto mt-16 relative">
    
    <div class="bg-white p-10 rounded-3xl border border-slate-200 shadow-xl relative">
        <div class="text-center mb-10">
            <div class="w-16 h-16 bg-blue-50 rounded-2xl flex items-center justify-center mx-auto mb-6 border border-blue-100">
                <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path></svg>
            </div>
            <h2 class="text-3xl font-black text-slate-800 tracking-tight">Create Account</h2>
            <p class="text-sm font-medium text-slate-500 mt-2">Join CampusFIX today</p>
        </div>
        
        <form method="POST" action="{{ url_for('register') }}" class="space-y-6">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Full Name</label>
                <input type="text" name="full_name" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner transition-colors">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Email Address</label>
                <input type="email" name="email" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner transition-colors">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Password</label>
                <input type="password" name="password" required class="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3.5 text-sm font-medium text-slate-800 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 shadow-inner transition-colors">
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold py-4 rounded-xl transition-all shadow-md transform hover:-translate-y-0.5 mt-2">
                Create Student Account &rarr;
            </button>
        </form>
        
        <div class="mt-8 text-center pt-6 border-t border-slate-100">
            <p class="text-sm font-medium text-slate-500">Already registered? <a href="{{ url_for('login') }}" class="text-blue-600 hover:text-blue-700 transition-colors font-bold">Sign In</a></p>
        </div>
    </div>
</div>
{% endblock %}"""
    }

    # Write files
    for filename, content in templates.items():
        filepath = os.path.join(template_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Generated Tailwind template: {filename}")

# ==========================================
# 5. CORE ROUTES & AUTH
# ==========================================

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'Admin':
            return redirect(url_for('admin_dashboard'))
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
                flash('Your account has been suspended.', 'error')
                return redirect(url_for('login'))
                
            login_user(user)
            db.session.add(AuditLog(action=f"User Logged In: {user.role}", user_id=user.id))
            db.session.commit()
            
            if user.role == 'Admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('dashboard'))
            
        flash('Invalid email or password.', 'error')
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
            role='Student'
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    db.session.add(AuditLog(action="User Logged Out", user_id=current_user.id))
    db.session.commit()
    logout_user()
    flash('You have been logged out.', 'success')
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


# ==========================================
# 6. DASHBOARDS
# ==========================================

@app.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    if current_user.role in ['Admin', 'Tech']:
        complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    else:
        complaints = Complaint.query.filter_by(user_id=current_user.id).order_by(Complaint.created_at.desc()).all()
        
    return render_template('dashboard.html', complaints=complaints)


@app.route('/admin_dashboard', methods=['GET'])
@login_required
@role_required('Admin')
def admin_dashboard():
    total_users = User.query.count()
    total_complaints = Complaint.query.count()
    
    status_counts = db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all()
    status_dict = {status: count for status, count in status_counts}
    
    category_counts = db.session.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all()
    
    recent_activity = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(15).all()
    
    return render_template(
        'admin_dashboard.html', 
        total_users=total_users, 
        total_complaints=total_complaints,
        status_dict=status_dict,
        category_counts=category_counts,
        recent_activity=recent_activity
    )

# ==========================================
# 7. COMPLAINT ENGINE ACTIONS 
# ==========================================

@app.route('/submit_complaint', methods=['POST'])
@login_required
def submit_complaint():
    new_complaint = Complaint(
        category=request.form.get('category'),
        location=request.form.get('location'),
        description=request.form.get('description'),
        user_id=current_user.id
    )
    db.session.add(new_complaint)
    db.session.flush() 
    
    db.session.add(AuditLog(
        action=f"New {new_complaint.category} ticket filed by {current_user.full_name}", 
        user_id=current_user.id, 
        complaint_id=new_complaint.id
    ))
    
    admins = User.query.filter_by(role='Admin').all()
    for admin in admins:
        create_notification(admin.id, f"New ticket filed: {new_complaint.category} Issue", url_for('view_complaint', id=new_complaint.id))
        
    db.session.commit()
    flash('Your report has been submitted and is pending review.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/complaint/<int:id>', methods=['GET', 'POST'])
@login_required
def view_complaint(id):
    complaint = db.session.get(Complaint, id)
    if not complaint:
        abort(404)
        
    if current_user.role == 'Student' and complaint.user_id != current_user.id:
        abort(403)

    if request.method == 'POST' and 'content' in request.form:
        if complaint.status in ['Resolved', 'Cancelled']:
            flash('Cannot comment on closed tickets.', 'warning')
            return redirect(url_for('view_complaint', id=complaint.id))
            
        content = request.form.get('content')
        new_comment = Comment(content=content, user_id=current_user.id, complaint_id=complaint.id)
        db.session.add(new_comment)
        
        if current_user.role in ['Admin', 'Tech']:
            create_notification(complaint.user_id, f"New tech update on Ticket #{complaint.id}", url_for('view_complaint', id=complaint.id))
        elif complaint.assigned_to:
            create_notification(complaint.assigned_to, f"User replied to Ticket #{complaint.id}", url_for('view_complaint', id=complaint.id))
            
        db.session.commit()
        flash('Message sent.', 'success')
        return redirect(url_for('view_complaint', id=complaint.id))
        
    logs = AuditLog.query.filter(AuditLog.complaint_id == complaint.id).all()
    comments = Comment.query.filter_by(complaint_id=complaint.id).all()
    timeline = sorted(chain(logs, comments), key=lambda x: x.created_at, reverse=True)
    
    solvers = User.query.filter(User.role.in_(['Tech', 'Admin'])).all()
    
    return render_template('view_complaint.html', complaint=complaint, timeline=timeline, solvers=solvers)

@app.route('/update_complaint/<int:id>', methods=['POST'])
@login_required
@role_required('Admin', 'Tech')
def update_complaint(id):
    complaint = db.session.get(Complaint, id)
    if not complaint:
        abort(404)
        
    if request.form.get('claim_ticket') == 'true' and current_user.role == 'Tech' and not complaint.assigned_to:
        complaint.assigned_to = current_user.id
        db.session.add(AuditLog(action=f"Ticket Claimed by {current_user.full_name}", user_id=current_user.id, complaint_id=complaint.id))
        create_notification(complaint.user_id, f"A technician has claimed your ticket #{complaint.id}", url_for('view_complaint', id=complaint.id))
        
    assigned_tech_id = request.form.get('assigned_to')
    if assigned_tech_id and current_user.role == 'Admin':
        if str(complaint.assigned_to) != assigned_tech_id:
            complaint.assigned_to = int(assigned_tech_id)
            assigned_user = db.session.get(User, complaint.assigned_to)
            if assigned_user:
                db.session.add(AuditLog(action=f"Ticket Assigned to {assigned_user.full_name} by Admin", user_id=current_user.id, complaint_id=complaint.id))
                create_notification(assigned_user.id, f"You've been assigned Ticket #{complaint.id}", url_for('view_complaint', id=complaint.id))
                create_notification(complaint.user_id, "A technician has been assigned to your ticket.", url_for('view_complaint', id=complaint.id))

    new_status = request.form.get('status')
    if new_status and new_status != complaint.status:
        old_status = complaint.status
        complaint.status = new_status
        if new_status == 'Resolved':
            complaint.resolved_at = datetime.utcnow()
            
        db.session.add(AuditLog(action=f"Status changed to: {new_status}", user_id=current_user.id, complaint_id=complaint.id))
        create_notification(complaint.user_id, f"Ticket #{complaint.id} status updated to {new_status}.", url_for('view_complaint', id=complaint.id))
            
    db.session.commit()
    flash('Ticket updated successfully.', 'success')
    return redirect(url_for('view_complaint', id=complaint.id))

@app.route('/update_status/<int:complaint_id>', methods=['POST'])
@login_required
@role_required('Admin', 'Tech')
def update_status(complaint_id):
    complaint = Complaint.query.get_or_404(complaint_id)
    new_status = request.form.get('status')
    
    if new_status and new_status != complaint.status:
        old_status = complaint.status
        complaint.status = new_status
        
        if new_status == 'Resolved':
            complaint.resolved_at = datetime.utcnow()
            
        db.session.add(AuditLog(
            action=f"Ticket #{complaint.id} status updated: {old_status} -> {new_status}", 
            user_id=current_user.id, 
            complaint_id=complaint.id
        ))
        
        create_notification(complaint.user_id, f"Ticket #{complaint.id} status updated to {new_status}.", url_for('view_complaint', id=complaint.id))
        
        db.session.commit()
        flash(f'Ticket #{complaint.id} marked as {new_status}.', 'success')
        
    return redirect(url_for('dashboard'))

# ==========================================
# 8. ADMIN & INVENTORY ROUTES
# ==========================================

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
        action = "Suspended" if not user.is_active else "Reactivated"
        db.session.add(AuditLog(action=f"User Account {action}: {user.email}", user_id=current_user.id))
        db.session.commit()
        flash(f"User {user.full_name} {action.lower()}.", "success")
        
    return redirect(url_for('manage_users'))

@app.route('/admin/export')
@login_required
@role_required('Admin')
def export_data():
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Category', 'Status', 'Location', 'Reported_By', 'Created_At', 'Resolved_At'])
    
    complaints = Complaint.query.all()
    for c in complaints:
        cw.writerow([
            c.id, c.category, c.status, c.location,
            c.author.email if c.author else 'Unknown',
            c.created_at.strftime('%Y-%m-%d %H:%M'),
            c.resolved_at.strftime('%Y-%m-%d %H:%M') if c.resolved_at else ''
        ])
        
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename=campusfix_export.csv"})

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
    db.session.commit()
    flash('Item added to inventory.', 'success')
    return redirect(url_for('inventory'))

@app.route('/inventory/<int:id>/update', methods=['POST'])
@login_required
@role_required('Admin', 'Tech')
def update_inventory(id):
    item = db.session.get(InventoryItem, id)
    if not item: abort(404)
        
    try:
        amount = int(request.form.get('amount', 0))
        if amount == 0: return redirect(url_for('inventory'))
            
        if item.quantity + amount < 0:
            flash(f"Insufficient stock for {item.item_name}.", 'error')
            return redirect(url_for('inventory'))
            
        item.quantity += amount
        if amount > 0: item.last_restocked = datetime.utcnow()
            
        db.session.commit()
        flash(f"Inventory updated.", 'success')
    except ValueError:
        flash("Invalid quantity value.", "error")
        
    return redirect(url_for('inventory'))

# ==========================================
# 9. DATABASE SEEDER
# ==========================================

def seed_database():
    """Injects dummy data into the system for testing."""
    with app.app_context():
        db.create_all()
        
        if User.query.count() > 0:
            return 
            
        logger.info("Initializing massive database seed...")
        
        admin = User(full_name='System Admin', email='admin@campus.edu', password_hash=generate_password_hash('Admin@123'), role='Admin')
        tech = User(full_name='Lead Technician', email='tech@campus.edu', password_hash=generate_password_hash('Tech@123'), role='Tech')
        student = User(full_name='Test Student', email='student@campus.edu', password_hash=generate_password_hash('Student@123'), role='Student')
        
        db.session.add_all([admin, tech, student])
        db.session.commit()
        
        inventory = [
            InventoryItem(item_name='LED Light Bulbs', category='Electrical', quantity=45),
            InventoryItem(item_name='PVC Pipe', category='Plumbing', quantity=3),
            InventoryItem(item_name='Air Filters', category='HVAC', quantity=8),
        ]
        db.session.add_all(inventory)

        c1 = Complaint(category='Electrical', location='Library 2nd Floor', description='Lights are flickering heavily above the main desk.', status='Pending', user_id=student.id)
        c2 = Complaint(category='Plumbing', location='Dorm A Restroom', description='Water leak near the sinks.', status='In Progress', user_id=student.id, assigned_to=tech.id)
        c3 = Complaint(category='IT/Network', location='Science Lab 4', description='No wifi signal on the east side of the room.', status='Resolved', user_id=student.id, assigned_to=tech.id, resolved_at=datetime.utcnow())
        
        db.session.add_all([c1, c2, c3])
        db.session.commit()
        
        db.session.add(AuditLog(action="New Electrical ticket filed by Test Student", user_id=student.id, complaint_id=c1.id))
        db.session.add(AuditLog(action="Ticket Claimed by Lead Technician", user_id=tech.id, complaint_id=c2.id))
        db.session.add(AuditLog(action="Ticket #3 status updated: In Progress -> Resolved", user_id=tech.id, complaint_id=c3.id))
        
        create_notification(admin.id, "Welcome to CampusFIX. System is ready.", "/admin_dashboard")
        create_notification(student.id, "Ticket #2 has been claimed by Lead Technician.", "/complaint/2")
        
        db.session.commit()
        logger.info("Database successfully seeded.")

# ==========================================
# 10. APPLICATION ENTRY POINT
# ==========================================

if __name__ == '__main__':
    initialize_templates()
    seed_database()
    app.run(debug=True, host='127.0.0.1', port=5000)
