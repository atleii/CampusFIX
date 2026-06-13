import os
import logging
from datetime import datetime
from itertools import chain
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import or_, desc, func

# Import Models (Ensure these are defined in your local database.py)
# Note: For this to run, your database.py must have db, User, Complaint, Comment, and AuditLog defined.
from database import db, User, Complaint, Comment, AuditLog

# ==========================================
# 1. APPLICATION CONFIGURATION & SETUP
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'enterprise_campus_fix_secret_999_production_ready_string')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///campusfix_enterprise.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Setup Centralized Logging for Auditing and Debugging
logging.basicConfig(
    level=logging.INFO, 
    format='[%(asctime)s] %(levelname)s - %(module)s.%(funcName)s: %(message)s'
)
logger = logging.getLogger('CampusFixLogger')

db.init_app(app)

# Flask-Login Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Please log in to access this secure page."
login_manager.login_message_category = 'warning'

@login_manager.user_loader
def load_user(user_id):
    """Loads the user by ID for the Flask-Login session."""
    return User.query.get(int(user_id))

# Security Headers Middleware
@app.after_request
def apply_security_headers(response):
    """Applies security headers to every HTTP response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# ==========================================
# 2. HTML TEMPLATE AUTO-GENERATOR
# ==========================================
# This section fulfills the request to embed the template logic directly into the code.
# It creates the necessary frontend files on startup if they don't exist.

def initialize_templates():
    """Creates the templates directory and generates the necessary HTML files."""
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(template_dir, exist_ok=True)

    templates = {
        "base.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}CampusFIX Enterprise{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
    <style>
        body { background-color: #f4f6f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        .navbar-brand { font-weight: bold; letter-spacing: 1px; }
        .card { border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
        .timeline { border-left: 3px solid #e9ecef; padding-left: 1.5rem; position: relative; }
        .timeline-item { margin-bottom: 2rem; position: relative; }
        .timeline-item::before { content: ''; position: absolute; left: -1.9rem; top: 0; width: 15px; height: 15px; border-radius: 50%; background: #0d6efd; border: 3px solid #fff; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('home') }}"><i class="bi bi-tools text-primary me-2"></i>CampusFIX</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav ms-auto">
                    {% if current_user.is_authenticated %}
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link" href="{{ url_for('profile') }}">Profile</a>
                        </li>
                        <li class="nav-item">
                            <a class="nav-link text-danger" href="{{ url_for('logout') }}">Logout ({{ current_user.full_name }})</a>
                        </li>
                    {% else %}
                        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">Login</a></li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>

    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ 'danger' if category == 'error' else category }} alert-dismissible fade show shadow-sm" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </div>

    <footer class="mt-5 py-4 text-center text-muted border-top bg-white">
        <div class="container">
            <p class="mb-0">&copy; {{ datetime.utcnow().year }} CampusFIX Enterprise System. All rights reserved.</p>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>""",

        "404.html": """{% extends "base.html" %}
{% block title %}404 - Page Not Found{% endblock %}
{% block content %}
<div class="row justify-content-center text-center mt-5">
    <div class="col-md-6">
        <h1 class="display-1 text-primary fw-bold">404</h1>
        <h3 class="mb-4">Oops! Page Not Found</h3>
        <p class="text-muted mb-4">The page you are looking for might have been removed, had its name changed, or is temporarily unavailable.</p>
        <a href="{{ url_for('home') }}" class="btn btn-primary btn-lg"><i class="bi bi-house-door me-2"></i>Return to Dashboard</a>
    </div>
</div>
{% endblock %}""",

        "500.html": """{% extends "base.html" %}
{% block title %}500 - Server Error{% endblock %}
{% block content %}
<div class="row justify-content-center text-center mt-5">
    <div class="col-md-6">
        <h1 class="display-1 text-danger fw-bold">500</h1>
        <h3 class="mb-4">Internal Server Error</h3>
        <p class="text-muted mb-4">Something went wrong on our end. Our technical staff has been notified of this issue. Please try again later.</p>
        <a href="{{ url_for('home') }}" class="btn btn-outline-danger btn-lg"><i class="bi bi-arrow-clockwise me-2"></i>Reload System</a>
    </div>
</div>
{% endblock %}""",

        "profile.html": """{% extends "base.html" %}
{% block title %}User Profile - CampusFIX{% endblock %}
{% block content %}
<div class="row justify-content-center">
    <div class="col-lg-8">
        <div class="card border-0 shadow-sm">
            <div class="card-header bg-primary text-white py-3">
                <h5 class="mb-0"><i class="bi bi-person-badge me-2"></i>Manage Profile</h5>
            </div>
            <div class="card-body p-4">
                <form action="{{ url_for('profile') }}" method="POST">
                    <div class="row mb-3">
                        <div class="col-md-6">
                            <label class="form-label text-muted fw-bold">Full Name</label>
                            <input type="text" name="full_name" class="form-control form-control-lg" value="{{ user.full_name }}" required>
                        </div>
                        <div class="col-md-6">
                            <label class="form-label text-muted fw-bold">Email Address</label>
                            <input type="email" class="form-control form-control-lg bg-light" value="{{ user.email }}" disabled>
                            <small class="text-muted">Email cannot be changed.</small>
                        </div>
                    </div>
                    <div class="row mb-4">
                        <div class="col-md-6">
                            <label class="form-label text-muted fw-bold">Department</label>
                            <input type="text" name="department" class="form-control form-control-lg" value="{{ user.department }}">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label text-muted fw-bold">System Role</label>
                            <input type="text" class="form-control form-control-lg bg-light" value="{{ user.role }}" disabled>
                        </div>
                    </div>
                    
                    <hr class="my-4">
                    <h6 class="mb-3 text-uppercase text-muted fw-bold">Security Settings</h6>
                    
                    <div class="mb-4">
                        <label class="form-label text-muted fw-bold">Change Password (Optional)</label>
                        <input type="password" name="new_password" class="form-control form-control-lg" placeholder="Leave blank to keep current password">
                        <small class="text-muted">Must be at least 8 characters long.</small>
                    </div>
                    
                    <div class="d-grid gap-2 d-md-flex justify-content-md-end">
                        <button type="submit" class="btn btn-primary btn-lg px-5">Save Changes</button>
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
<div class="container-fluid py-2">
    <div class="d-flex justify-content-between align-items-center mb-4 bg-white p-4 rounded shadow-sm border-start border-5 {% if complaint.status == 'Resolved' %}border-success{% elif complaint.status == 'Pending' %}border-danger{% else %}border-warning{% endif %}">
        <div>
            <h2 class="mb-1 fw-bold text-dark">Ticket #{{ complaint.id }}: {{ complaint.title }}</h2>
            <p class="text-muted mb-0"><i class="bi bi-calendar-event me-2"></i>Filed on {{ complaint.created_at.strftime('%B %d, %Y at %I:%M %p') }}</p>
        </div>
        <div class="text-end">
            <span class="badge rounded-pill fs-6 px-4 py-2 
                {% if complaint.status == 'Resolved' %}bg-success
                {% elif complaint.status == 'In Progress' %}bg-warning text-dark
                {% else %}bg-danger{% endif %}">
                <i class="bi bi-activity me-1"></i> {{ complaint.status }}
            </span>
        </div>
    </div>

    <div class="row g-4">
        <div class="col-lg-5">
            <div class="card shadow-sm border-0 h-100">
                <div class="card-header bg-dark text-white py-3">
                    <h5 class="mb-0"><i class="bi bi-info-circle me-2"></i>Issue Details</h5>
                </div>
                <div class="card-body p-4">
                    <table class="table table-borderless mb-4">
                        <tbody>
                            <tr class="border-bottom">
                                <th scope="row" class="text-muted w-35 py-3"><i class="bi bi-tags me-2"></i>Category</th>
                                <td class="py-3 fw-bold">{{ complaint.category }}</td>
                            </tr>
                            <tr class="border-bottom">
                                <th scope="row" class="text-muted py-3"><i class="bi bi-geo-alt me-2"></i>Location</th>
                                <td class="py-3">{{ complaint.location }}</td>
                            </tr>
                            <tr class="border-bottom">
                                <th scope="row" class="text-muted py-3"><i class="bi bi-exclamation-triangle me-2"></i>Priority</th>
                                <td class="py-3">
                                    <span class="badge 
                                        {% if complaint.priority == 'Critical' %}bg-danger
                                        {% elif complaint.priority == 'High' %}bg-warning text-dark
                                        {% else %}bg-info text-dark{% endif %}">
                                        {{ complaint.priority }}
                                    </span>
                                </td>
                            </tr>
                            <tr>
                                <th scope="row" class="text-muted py-3"><i class="bi bi-person-workspace me-2"></i>Assigned Tech</th>
                                <td class="py-3">
                                    {% if complaint.assigned_to %}
                                        <span class="fw-bold text-primary">{{ complaint.assignee.full_name }}</span>
                                    {% else %}
                                        <em class="text-danger">Unassigned</em>
                                    {% endif %}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                    
                    <h6 class="text-muted text-uppercase mb-3 fw-bold">Full Description</h6>
                    <div class="bg-light p-4 rounded border text-break" style="min-height: 150px; white-space: pre-wrap;">{{ complaint.description }}</div>
                </div>
            </div>
        </div>

        <div class="col-lg-7">
            <div class="card shadow-sm border-0 h-100 d-flex flex-column">
                <div class="card-header bg-white border-bottom py-3 d-flex justify-content-between align-items-center">
                    <h5 class="mb-0 text-dark fw-bold"><i class="bi bi-clock-history me-2 text-primary"></i>Progress Timeline</h5>
                </div>
                
                <div class="card-body overflow-auto flex-grow-1" style="max-height: 600px; background-color: #f8f9fa;">
                    <div class="timeline">
                        {% for event in timeline %}
                        <div class="timeline-item">
                            <div class="text-muted small mb-2 fw-bold">
                                {{ event.created_at.strftime('%b %d, %Y at %I:%M %p') }}
                            </div>
                            <div class="card border-0 shadow-sm {% if event.action %}border-start border-primary border-4{% endif %}">
                                <div class="card-body py-3 px-4">
                                    {% if event.action %}
                                        <div class="d-flex align-items-center">
                                            <i class="bi bi-gear-fill text-primary fs-4 me-3"></i>
                                            <div>
                                                <strong class="text-dark d-block">System/Tech Update</strong>
                                                <span class="text-muted">{{ event.action }}</span>
                                            </div>
                                        </div>
                                    {% elif event.content %}
                                        <div class="d-flex align-items-start">
                                            <div class="bg-secondary text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 40px; height: 40px;">
                                                {{ event.user.full_name[0] | upper }}
                                            </div>
                                            <div>
                                                <strong class="text-dark d-block">{{ event.user.full_name }} <span class="badge bg-light text-dark ms-2 border">{{ event.user.role }}</span></strong>
                                                <p class="mb-0 mt-1 text-secondary">{{ event.content }}</p>
                                            </div>
                                        </div>
                                    {% endif %}
                                </div>
                            </div>
                        </div>
                        {% else %}
                        <div class="text-center py-5">
                            <i class="bi bi-inbox text-muted" style="font-size: 3rem;"></i>
                            <p class="text-muted mt-3">No activity recorded yet.</p>
                        </div>
                        {% endfor %}
                    </div>
                </div>

                <div class="card-footer bg-white p-4 border-top shadow-sm">
                    {% if complaint.status != 'Resolved' %}
                        
                        {% if current_user.role in ['Tech', 'Admin'] %}
                            <form action="{{ url_for('update_complaint', id=complaint.id) }}" method="POST">
                                {% if not complaint.assigned_to %}
                                <div class="alert alert-warning border-warning border-start border-4 mb-3 d-flex align-items-center">
                                    <div class="form-check mb-0 w-100">
                                        <input class="form-check-input fs-5" type="checkbox" name="claim_ticket" value="true" id="claimTicket">
                                        <label class="form-check-label fw-bold text-dark ms-2 pt-1" for="claimTicket">
                                            Claim this ticket to begin resolution tracking
                                        </label>
                                    </div>
                                </div>
                                {% endif %}

                                <div class="row g-3">
                                    <div class="col-md-4">
                                        <label class="form-label text-muted fw-bold">Update Status</label>
                                        <select name="status" class="form-select form-select-lg">
                                            <option value="{{ complaint.status }}" selected>Current: {{ complaint.status }}</option>
                                            {% if complaint.status != 'In Progress' %}<option value="In Progress">In Progress</option>{% endif %}
                                            <option value="Resolved">Resolved</option>
                                        </select>
                                    </div>
                                    <div class="col-md-8">
                                        <label class="form-label text-muted fw-bold">Progress Note (Visible to Student)</label>
                                        <input type="text" name="progress_note" class="form-control form-control-lg" placeholder="E.g., Parts ordered, inspecting site...">
                                    </div>
                                </div>
                                <div class="d-grid mt-4">
                                    <button type="submit" class="btn btn-primary btn-lg"><i class="bi bi-save me-2"></i>Update Ticket</button>
                                </div>
                            </form>
                        
                        {% elif current_user.role == 'Student' %}
                            <form action="{{ url_for('view_complaint', id=complaint.id) }}" method="POST">
                                <label class="form-label text-muted fw-bold">Add a Comment or Query</label>
                                <div class="input-group input-group-lg">
                                    <input type="text" name="content" class="form-control" placeholder="Type your message to the tech team here..." required>
                                    <button class="btn btn-dark px-4" type="submit"><i class="bi bi-send-fill me-2"></i>Post</button>
                                </div>
                            </form>
                        {% endif %}
                    
                    {% else %}
                        <div class="alert alert-success mb-0 d-flex align-items-center p-3">
                            <i class="bi bi-check-circle-fill fs-2 me-3"></i>
                            <div>
                                <h5 class="mb-0 fw-bold">Issue Resolved</h5>
                                <p class="mb-0">This ticket was marked completed on {{ complaint.resolved_at.strftime('%B %d, %Y') }}. Further updates are disabled.</p>
                            </div>
                        </div>
                    {% endif %}
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}""",

        "admin_dashboard.html": """{% extends "base.html" %}
{% block title %}Admin Control Center - CampusFIX{% endblock %}
{% block content %}
<div class="container-fluid py-4">
    <div class="row mb-4 align-items-center">
        <div class="col-md-6">
            <h2 class="mb-0 fw-bold text-dark"><i class="bi bi-speedometer text-primary me-2"></i>Admin Control Center</h2>
            <p class="text-muted mb-0">System-wide analytics and performance metrics.</p>
        </div>
        <div class="col-md-6 text-md-end mt-3 mt-md-0">
            <a href="{{ url_for('manage_users') }}" class="btn btn-outline-primary"><i class="bi bi-people me-2"></i>Manage Users</a>
            <button class="btn btn-primary ms-2" onclick="location.reload();"><i class="bi bi-arrow-clockwise me-2"></i>Refresh Data</button>
        </div>
    </div>

    <div class="row g-4 mb-5">
        <div class="col-xl-3 col-md-6">
            <div class="card bg-primary text-white border-0 shadow h-100 py-2">
                <div class="card-body">
                    <div class="row no-gutters align-items-center">
                        <div class="col mr-2">
                            <div class="text-xs font-weight-bold text-uppercase mb-1">Total Users</div>
                            <div class="h2 mb-0 font-weight-bold">{{ total_users }}</div>
                        </div>
                        <div class="col-auto"><i class="bi bi-people-fill fs-1 text-white-50"></i></div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-xl-3 col-md-6">
            <div class="card bg-dark text-white border-0 shadow h-100 py-2">
                <div class="card-body">
                    <div class="row no-gutters align-items-center">
                        <div class="col mr-2">
                            <div class="text-xs font-weight-bold text-uppercase mb-1">Total Complaints</div>
                            <div class="h2 mb-0 font-weight-bold">{{ total_complaints }}</div>
                        </div>
                        <div class="col-auto"><i class="bi bi-folder-fill fs-1 text-white-50"></i></div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-xl-3 col-md-6">
            <div class="card bg-warning text-dark border-0 shadow h-100 py-2">
                <div class="card-body">
                    <div class="row no-gutters align-items-center">
                        <div class="col mr-2">
                            <div class="text-xs font-weight-bold text-uppercase mb-1">Pending/In-Progress</div>
                            <div class="h2 mb-0 font-weight-bold">{{ status_dict.get('Pending', 0) + status_dict.get('In Progress', 0) }}</div>
                        </div>
                        <div class="col-auto"><i class="bi bi-hourglass-split fs-1 text-dark-50"></i></div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-xl-3 col-md-6">
            <div class="card bg-success text-white border-0 shadow h-100 py-2">
                <div class="card-body">
                    <div class="row no-gutters align-items-center">
                        <div class="col mr-2">
                            <div class="text-xs font-weight-bold text-uppercase mb-1">Resolved Issues</div>
                            <div class="h2 mb-0 font-weight-bold">{{ status_dict.get('Resolved', 0) }}</div>
                        </div>
                        <div class="col-auto"><i class="bi bi-check-circle-fill fs-1 text-white-50"></i></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="row g-4 mb-4">
        <div class="col-lg-6">
            <div class="card border-0 shadow-sm h-100">
                <div class="card-header bg-white py-3">
                    <h6 class="m-0 font-weight-bold text-dark">Complaints by Status</h6>
                </div>
                <div class="card-body d-flex justify-content-center align-items-center">
                    <canvas id="statusChart" style="max-height: 300px;"></canvas>
                </div>
            </div>
        </div>
        <div class="col-lg-6">
            <div class="card border-0 shadow-sm h-100">
                <div class="card-header bg-white py-3">
                    <h6 class="m-0 font-weight-bold text-dark">Complaints by Category</h6>
                </div>
                <div class="card-body d-flex justify-content-center align-items-center">
                    <canvas id="categoryChart" style="max-height: 300px;"></canvas>
                </div>
            </div>
        </div>
    </div>

    <div class="card border-0 shadow-sm">
        <div class="card-header bg-dark text-white py-3">
            <h6 class="m-0 font-weight-bold"><i class="bi bi-list-columns-reverse me-2"></i>Live System Audit Trail (Last 10 Events)</h6>
        </div>
        <div class="card-body p-0">
            <div class="table-responsive">
                <table class="table table-hover mb-0">
                    <thead class="table-light">
                        <tr>
                            <th class="px-4 py-3">Timestamp</th>
                            <th class="py-3">User Executing</th>
                            <th class="py-3">Ticket ID</th>
                            <th class="py-3">Action Description</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for log in recent_activity %}
                        <tr>
                            <td class="px-4 text-muted small">{{ log.created_at.strftime('%Y-%m-%d %H:%M:%S') }}</td>
                            <td class="fw-bold">{{ log.user.full_name }}</td>
                            <td><a href="{{ url_for('view_complaint', id=log.complaint_id) }}" class="badge bg-primary text-decoration-none">#{{ log.complaint_id }}</a></td>
                            <td>{{ log.action }}</td>
                        </tr>
                        {% else %}
                        <tr><td colspan="4" class="text-center py-4 text-muted">No recent activity found in the system.</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
    document.addEventListener("DOMContentLoaded", function() {
        // Parse Jinja Data into Javascript Objects securely
        const statusData = {{ status_dict | tojson }};
        const categoryDataRaw = {{ category_counts | tojson }};
        
        // Setup Status Chart (Doughnut)
        const ctxStatus = document.getElementById('statusChart').getContext('2d');
        new Chart(ctxStatus, {
            type: 'doughnut',
            data: {
                labels: Object.keys(statusData),
                datasets: [{
                    data: Object.values(statusData),
                    backgroundColor: ['#dc3545', '#ffc107', '#198754', '#0dcaf0'],
                    borderWidth: 1
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
        });

        // Setup Category Chart (Bar)
        const labelsCat = categoryDataRaw.map(item => item[0]);
        const dataCat = categoryDataRaw.map(item => item[1]);
        
        const ctxCat = document.getElementById('categoryChart').getContext('2d');
        new Chart(ctxCat, {
            type: 'bar',
            data: {
                labels: labelsCat,
                datasets: [{
                    label: 'Number of Tickets',
                    data: dataCat,
                    backgroundColor: '#0d6efd',
                    borderRadius: 4
                }]
            },
            options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
        });
    });
</script>
{% endblock %}"""
    }

    # Write each template to the templates directory
    for filename, content in templates.items():
        filepath = os.path.join(template_dir, filename)
        if not os.path.exists(filepath):
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Generated missing template file: {filepath}")

# ==========================================
# 3. CUSTOM DECORATORS (RBAC)
# ==========================================

def roles_required(*roles):
    """
    Role-Based Access Control (RBAC) Decorator.
    Blocks users who do not possess the required roles from accessing sensitive routes.
    """
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.role not in roles:
                logger.warning(f"SECURITY ALERT: Unauthorized access attempt by {current_user.email} (Role: {current_user.role}) to endpoint {request.path}")
                abort(403) # Trigger 403 Forbidden Error Page
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

# ==========================================
# 4. DATABASE INITIALIZATION & SEEDING
# ==========================================

def setup_database():
    """Initializes tables and injects default administrative accounts if missing."""
    with app.app_context():
        db.create_all()
        # Seed an Admin and a Tech Staff if none exist in the DB
        if not User.query.filter_by(email='admin@campus.edu').first():
            admin = User(
                full_name='System Administrator',
                email='admin@campus.edu',
                password_hash=generate_password_hash('Admin@123', method='pbkdf2:sha256'),
                role='Admin',
                department='IT Operations',
                is_active=True
            )
            tech = User(
                full_name='Bob The Builder',
                email='tech@campus.edu',
                password_hash=generate_password_hash('Tech@123', method='pbkdf2:sha256'),
                role='Tech',
                department='Maintenance',
                is_active=True
            )
            db.session.add_all([admin, tech])
            db.session.commit()
            logger.info("Database initialized and seeded with default Admin & Tech accounts.")

# ==========================================
# 5. CORE ROUTING & AUTHENTICATION
# ==========================================

@app.route('/')
def home():
    """Root redirector based on authentication status."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user authentication, session creation, and role-based redirection."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Please provide both email and password credentials.', 'danger')
            return render_template('login.html')

        user = User.query.filter_by(email=email).first()
        
        # Verify Password against Hash
        if user and check_password_hash(user.password_hash, password):
            # Check Account Status
            if getattr(user, 'is_active', True) == False:
                logger.info(f"Access Denied: Deactivated account attempted login - {email}")
                flash('Your account has been deactivated. Please contact administration.', 'danger')
                return redirect(url_for('login'))
                
            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Authentication Successful: {user.email} (Role: {user.role})")
            
            # Intelligent Role Routing
            role_routes = {'Admin': 'admin_dashboard', 'Tech': 'tech_dashboard'}
            return redirect(url_for(role_routes.get(user.role, 'dashboard')))
            
        flash('Invalid email credentials or password.', 'danger')
        logger.warning(f"Failed authentication attempt for email: {email}")
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Terminates the user session securely."""
    logger.info(f"Session terminated manually by user: {current_user.email}")
    logout_user()
    flash('You have been securely logged out of the system.', 'info')
    return redirect(url_for('home'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Allows users to update personal data and alter passwords."""
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.department = request.form.get('department')
        
        new_password = request.form.get('new_password')
        if new_password:
            if len(new_password) >= 8:
                current_user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                flash('Profile and security credentials updated successfully.', 'success')
            else:
                flash('Security Error: New password must be at least 8 characters long.', 'danger')
                return redirect(url_for('profile'))
        else:
            flash('Profile details updated successfully.', 'success')
            
        db.session.commit()
        return redirect(url_for('profile'))
        
    return render_template('profile.html', user=current_user)

# ==========================================
# 6. COMPLAINT MANAGEMENT & PROGRESS ENGINE
# ==========================================

@app.route('/dashboard')
@login_required
@roles_required('Student', 'Admin')
def dashboard():
    """Student dashboard displaying personal complaints and status metrics."""
    page = request.args.get('page', 1, type=int)
    
    # Restrict scope specifically to the currently logged-in user
    base_query = Complaint.query.filter_by(user_id=current_user.id)
    pagination = base_query.order_by(desc(Complaint.created_at)).paginate(page=page, per_page=10)
    
    # Generate Quick Stats
    stats = {
        'total': base_query.count(),
        'resolved': base_query.filter_by(status='Resolved').count(),
        'active': base_query.filter(Complaint.status.in_(['Pending', 'In Progress'])).count()
    }
    
    return render_template('student_dashboard.html', complaints=pagination.items, pagination=pagination, stats=stats)

@app.route('/complaint/<int:id>', methods=['GET', 'POST'])
@login_required
def view_complaint(id):
    """
    Unified Ticket View: 
    Renders issue details, processes comments, and generates the chronological Progress Timeline.
    """
    complaint = Complaint.query.get_or_404(id)
    
    # Ownership Validation Check: Prevent IDOR (Insecure Direct Object Reference)
    if current_user.role == 'Student' and complaint.user_id != current_user.id:
        logger.warning(f"SECURITY ALERT: IDOR attempt by {current_user.email} on ticket #{id}")
        abort(403)
        
    # Process Incoming Comments (For both Techs and Students)
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if content:
            comment = Comment(content=content, user_id=current_user.id, complaint_id=complaint.id)
            db.session.add(comment)
            db.session.commit()
            flash('Your message has been securely appended to the ticket timeline.', 'success')
            return redirect(url_for('view_complaint', id=complaint.id))
        flash('Input Error: Comment payload cannot be empty.', 'warning')
            
    # Assemble the Chronological Timeline Engine
    # Extract both System Logs and User Comments
    logs = AuditLog.query.filter_by(complaint_id=complaint.id).all()
    comments = Comment.query.filter_by(complaint_id=complaint.id).all()
    
    # Interleave and sort by strict UTC creation timestamp
    timeline = sorted(chain(logs, comments), key=lambda item: item.created_at)
            
    return render_template('view_complaint.html', complaint=complaint, timeline=timeline)

@app.route('/complaint/<int:id>/update', methods=['POST'])
@login_required
@roles_required('Tech', 'Admin')
def update_complaint(id):
    """
    Tech Workflow Engine: 
    Processes ticket status updates, ownership claims, and injects granular progress notes.
    """
    complaint = Complaint.query.get_or_404(id)
    new_status = request.form.get('status')
    progress_note = request.form.get('progress_note', '').strip()
    claim_ticket = request.form.get('claim_ticket') == 'true'
    
    updates_made = False

    # 1. Ticket Claiming Subsystem
    if claim_ticket and not complaint.assigned_to:
        complaint.assigned_to = current_user.id
        db.session.add(AuditLog(
            action=f"Ownership Transfer: Ticket assigned to technician {current_user.full_name}.", 
            user_id=current_user.id, 
            complaint_id=complaint.id
        ))
        updates_made = True

    # 2. Status Mutation Subsystem
    if new_status and new_status != complaint.status:
        # Prevent status transitions on orphaned tickets
        if not complaint.assigned_to and new_status != 'Pending':
            flash('Workflow Restriction: You must claim ownership of the ticket before altering its status.', 'danger')
            return redirect(url_for('view_complaint', id=complaint.id))

        old_status = complaint.status
        complaint.status = new_status
        
        if new_status == 'Resolved':
            complaint.resolved_at = datetime.utcnow()
            
        # Construct Dynamic Audit Payload
        action_text = f"Status Transition: Moved from [{old_status}] to [{new_status}]."
        if progress_note:
            action_text += f" Official Tech Note: {progress_note}"
            
        db.session.add(AuditLog(action=action_text, user_id=current_user.id, complaint_id=complaint.id))
        updates_made = True
        progress_note = "" # Nullify to prevent duplicate logging below
    
    # 3. Standalone Progress Note Injection
    if progress_note:
        db.session.add(AuditLog(
            action=f"Maintenance Log: {progress_note}", 
            user_id=current_user.id, 
            complaint_id=complaint.id
        ))
        updates_made = True

    # 4. Final Transaction Commit
    if updates_made:
        db.session.commit()
        flash('Database updated: Ticket attributes modified successfully.', 'success')
    else:
        flash('System Notice: No modifying actions were detected in your request.', 'info')

    return redirect(url_for('view_complaint', id=complaint.id))

# ==========================================
# 7. ADMINISTRATOR DASHBOARD & SYSTEM ANALYTICS
# ==========================================

@app.route('/admin')
@login_required
@roles_required('Admin')
def admin_dashboard():
    """Generates complex datasets and feeds them to the Admin Control Center."""
    total_users = User.query.count()
    total_complaints = Complaint.query.count()
    
    # Aggregate data by status for Chart.js
    status_counts = db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all()
    status_dict = dict(status_counts)
    
    # Aggregate data by category for Chart.js
    category_counts = db.session.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all()
    
    # Pull recent chronologically descending system activity
    recent_activity = AuditLog.query.order_by(desc(AuditLog.created_at)).limit(10).all()
    
    return render_template(
        'admin_dashboard.html', 
        total_users=total_users, 
        total_complaints=total_complaints,
        status_dict=status_dict,
        category_counts=category_counts,
        recent_activity=recent_activity
    )

@app.route('/admin/users', methods=['GET'])
@login_required
@roles_required('Admin')
def manage_users():
    """Admin endpoint to view and filter user accounts."""
    search = request.args.get('search', '')
    query = User.query
    if search:
        query = query.filter(User.email.ilike(f'%{search}%') | User.full_name.ilike(f'%{search}%'))
        
    users = query.order_by(User.created_at.desc()).all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/users/<int:id>/toggle_status', methods=['POST'])
@login_required
@roles_required('Admin')
def toggle_user_status(id):
    """Allows administrators to soft-delete (deactivate) users."""
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('Safety Protocol: You cannot deactivate your own administrative account.', 'danger')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        action = "Activated" if user.is_active else "Deactivated"
        flash(f'Operation Successful: User account {action} in the directory.', 'success')
        logger.warning(f"ADMIN ACTION: {current_user.email} {action.lower()} account {user.email}")
        
    return redirect(url_for('manage_users'))

# ==========================================
# 8. ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def not_found_error(error):
    """Catches invalid routes and returns the 404 template."""
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    """Catches unauthorized access and returns a secure error page."""
    # Assuming we have a standard flash message for this in the base template
    flash("Error 403: You do not have the required permissions to view this resource.", "danger")
    return redirect(url_for('home'))

@app.errorhandler(500)
def internal_error(error):
    """Catches critical backend crashes, protects DB integrity, and logs the event."""
    db.session.rollback() # Protect DB integrity from hanging transactions
    logger.critical(f"FATAL INTERNAL SERVER ERROR: {error}")
    return render_template('500.html'), 500

# ==========================================
# 9. API ENDPOINTS (For Async Operations)
# ==========================================

@app.route('/api/stats', methods=['GET'])
@login_required
@roles_required('Admin')
def api_get_stats():
    """Provides a JSON data stream for external or async charting libraries."""
    resolved = Complaint.query.filter_by(status='Resolved').count()
    pending = Complaint.query.filter_by(status='Pending').count()
    in_progress = Complaint.query.filter_by(status='In Progress').count()
    
    return jsonify({
        'status': 'success',
        'timestamp': datetime.utcnow().isoformat(),
        'data': {
            'resolved': resolved,
            'pending': pending,
            'in_progress': in_progress
        }
    })

# ==========================================
# 10. BOOTSTRAP AND EXECUTION
# ==========================================

if __name__ == '__main__':
    # 1. Dynamically build the required HTML files on disk
    initialize_templates()
    
    # 2. Setup Database Structure
    setup_database()
    
    # 3. Launch Application Server
    # Use threaded=True for better concurrent performance handling in development
    app.run(debug=True, port=5000, threaded=True)
