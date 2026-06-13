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

# Import Models (Ensure these are defined in your database.py)
from database import db, User, Complaint, Comment, AuditLog

# ==========================================
# 1. APPLICATION CONFIGURATION & SETUP
# ==========================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'enterprise_campus_fix_secret_999')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///campusfix_enterprise.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Setup Logging for Auditing and Debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('CampusFixLogger')

db.init_app(app)

# Flask-Login Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'error'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==========================================
# 2. CUSTOM DECORATORS (RBAC)
# ==========================================

def roles_required(*roles):
    """Decorator to ensure only specific roles can access a route."""
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                logger.warning(f"Unauthorized access attempt by {current_user.email if current_user.is_authenticated else 'Anonymous'} to {request.path}")
                abort(403) # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

# ==========================================
# 3. DATABASE INITIALIZATION & SEEDING
# ==========================================

with app.app_context():
    db.create_all()
    # Seed an Admin and a Tech Staff if none exist
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
        logger.info("Database seeded with default Admin and Tech accounts.")

# ==========================================
# 4. AUTHENTICATION & PROFILE ROUTES
# ==========================================

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            if getattr(user, 'is_active', True) == False:
                flash('Your account has been deactivated. Contact administration.', 'error')
                return redirect(url_for('login'))
                
            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"User login successful: {user.email}")
            
            # Redirect based on role
            if user.role == 'Admin':
                return redirect(url_for('admin_dashboard'))
            elif user.role == 'Tech':
                return redirect(url_for('tech_dashboard'))
            return redirect(url_for('dashboard'))
            
        flash('Invalid email or password.', 'error')
        logger.warning(f"Failed login attempt for email: {email}")
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('full_name').strip()
        email = request.form.get('email').strip().lower()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Basic Validation
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
            
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('register'))
            
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('register'))

        new_user = User(
            full_name=name,
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256'),
            role='Student',
            department=request.form.get('department', 'General'),
            is_active=True
        )
        
        db.session.add(new_user)
        db.session.commit()
        logger.info(f"New user registered: {email}")
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logger.info(f"User logged out: {current_user.email}")
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.department = request.form.get('department')
        
        new_password = request.form.get('new_password')
        if new_password:
            if len(new_password) >= 8:
                current_user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                flash('Profile and password updated successfully.', 'success')
            else:
                flash('New password must be at least 8 characters.', 'error')
                return redirect(url_for('profile'))
        else:
            flash('Profile updated successfully.', 'success')
            
        db.session.commit()
        return redirect(url_for('profile'))
        
    return render_template('profile.html', user=current_user)

# ==========================================
# 5. CORE COMPLAINT MANAGEMENT & PROGRESS
# ==========================================

@app.route('/dashboard')
@login_required
@roles_required('Student', 'Admin')
def dashboard():
    page = request.args.get('page', 1, type=int)
    
    # Students see only their own, Admins could theoretically see all here if bypassing admin_dashboard
    query = Complaint.query.filter_by(user_id=current_user.id)
    pagination = query.order_by(desc(Complaint.created_at)).paginate(page=page, per_page=10)
    
    stats = {
        'total': query.count(),
        'resolved': query.filter_by(status='Resolved').count(),
        'pending': query.filter_by(status='Pending').count(),
        'in_progress': query.filter_by(status='In Progress').count()
    }
    
    return render_template('student_dashboard.html', complaints=pagination.items, pagination=pagination, stats=stats)

@app.route('/complaint/new', methods=['GET', 'POST'])
@login_required
@roles_required('Student')
def new_complaint():
    if request.method == 'POST':
        new_comp = Complaint(
            title=request.form.get('title'),
            category=request.form.get('category'),
            location=request.form.get('location'),
            priority=request.form.get('priority', 'Medium'),
            description=request.form.get('description'),
            user_id=current_user.id,
            status='Pending'
        )
        db.session.add(new_comp)
        db.session.commit()
        
        # Create initial audit log
        log = AuditLog(action="Complaint submitted and pending review", user_id=current_user.id, complaint_id=new_comp.id)
        db.session.add(log)
        db.session.commit()
        
        flash('Issue reported successfully.', 'success')
        return redirect(url_for('dashboard'))
        
    return render_template('new_complaint.html')

@app.route('/complaint/<int:id>', methods=['GET', 'POST'])
@login_required
def view_complaint(id):
    """
    Displays the complaint details alongside a unified 'Progress Timeline'
    consisting of both Audit Logs (status changes) and user Comments.
    """
    complaint = Complaint.query.get_or_404(id)
    
    # Security: Ensure students only see their own complaints
    if current_user.role == 'Student' and complaint.user_id != current_user.id:
        abort(403)
        
    # Handle New Comments (User & Tech interaction)
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            comment = Comment(content=content, user_id=current_user.id, complaint_id=complaint.id)
            db.session.add(comment)
            db.session.commit()
            flash('Comment added.', 'success')
            return redirect(url_for('view_complaint', id=complaint.id))
            
    # Compile Progress Timeline
    logs = AuditLog.query.filter_by(complaint_id=complaint.id).all()
    comments = Comment.query.filter_by(complaint_id=complaint.id).all()
    
    # Merge logs and comments into a single list sorted by creation date to show true progress
    timeline = sorted(chain(logs, comments), key=lambda x: x.created_at)
            
    return render_template('view_complaint.html', complaint=complaint, timeline=timeline)

# ==========================================
# 6. TECH STAFF DASHBOARD & WORKFLOW
# ==========================================

@app.route('/tech')
@login_required
@roles_required('Tech', 'Admin')
def tech_dashboard():
    # Tech sees unassigned complaints OR complaints assigned to them
    query = Complaint.query.filter(or_(Complaint.assigned_to == None, Complaint.assigned_to == current_user.id))
    
    status_filter = request.args.get('status')
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
        
    complaints = query.order_by(
        db.case(
            (Complaint.priority == 'Critical', 1),
            (Complaint.priority == 'High', 2),
            (Complaint.priority == 'Medium', 3),
            (Complaint.priority == 'Low', 4)
        ),
        desc(Complaint.created_at)
    ).all()
    
    return render_template('tech_dashboard.html', complaints=complaints)

@app.route('/complaint/<int:id>/update', methods=['POST'])
@login_required
@roles_required('Tech', 'Admin')
def update_complaint(id):
    """Allows tech staff to update status, claim tickets, and add progress notes."""
    complaint = Complaint.query.get_or_404(id)
    new_status = request.form.get('status')
    progress_note = request.form.get('progress_note') # New field for granular progress
    
    # Handle Ticket Claiming
    if request.form.get('claim_ticket') == 'true' and not complaint.assigned_to:
        complaint.assigned_to = current_user.id
        db.session.add(AuditLog(action=f"Ticket claimed and assigned to {current_user.full_name}", user_id=current_user.id, complaint_id=complaint.id))

    # Handle Status Changes
    if new_status and new_status != complaint.status:
        old_status = complaint.status
        complaint.status = new_status
        
        if new_status == 'Resolved':
            complaint.resolved_at = datetime.utcnow()
            
        action_text = f"Status updated from '{old_status}' to '{new_status}'."
        if progress_note:
            action_text += f" Note: {progress_note}"
            
        log = AuditLog(action=action_text, user_id=current_user.id, complaint_id=complaint.id)
        db.session.add(log)
    
    # Handle standalone progress notes without status change
    elif progress_note:
        log = AuditLog(action=f"Progress Update: {progress_note}", user_id=current_user.id, complaint_id=complaint.id)
        db.session.add(log)

    db.session.commit()
    flash('Complaint updated successfully.', 'success')
    return redirect(url_for('view_complaint', id=complaint.id))

# ==========================================
# 7. ADMINISTRATOR DASHBOARD & SYSTEM MANAGEMENT
# ==========================================

@app.route('/admin')
@login_required
@roles_required('Admin')
def admin_dashboard():
    total_users = User.query.count()
    total_complaints = Complaint.query.count()
    
    status_counts = db.session.query(Complaint.status, func.count(Complaint.id)).group_by(Complaint.status).all()
    status_dict = dict(status_counts)
    
    category_counts = db.session.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all()
    
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
    user = User.query.get_or_404(id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        action = "Activated" if user.is_active else "Deactivated"
        flash(f'User account {action} successfully.', 'success')
        logger.warning(f"Admin {current_user.email} {action.lower()} account {user.email}")
        
    return redirect(url_for('manage_users'))

# ==========================================
# 8. ERROR HANDLING (CUSTOM PAGES)
# ==========================================

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback() # Rollback bad DB transactions
    logger.error(f"Server Error: {error}")
    return render_template('500.html'), 500

# ==========================================
# 9. API ENDPOINTS (For Async Frontend)
# ==========================================

@app.route('/api/stats', methods=['GET'])
@login_required
@roles_required('Admin')
def api_get_stats():
    """Provides JSON data for charting libraries like Chart.js"""
    resolved = Complaint.query.filter_by(status='Resolved').count()
    pending = Complaint.query.filter_by(status='Pending').count()
    in_progress = Complaint.query.filter_by(status='In Progress').count()
    
    return jsonify({
        'status': 'success',
        'data': {
            'resolved': resolved,
            'pending': pending,
            'in_progress': in_progress
        }
    })

# ==========================================
# 10. APP EXECUTION
# ==========================================

if __name__ == '__main__':
    # Use threaded=True for better concurrent performance in development
    app.run(debug=True, port=5000, threaded=True)
