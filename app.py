import os
import sqlite3
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_mail import Mail, Message
from dateutil.relativedelta import relativedelta
from werkzeug.utils import secure_filename

# --- Flask Application Setup ---
app = Flask(__name__)
app.secret_key = 'your_super_secret_key'  # Replace with a secure secret key
app.config['DATABASE'] = 'database.db'

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload directory exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# --- Flask-Mail Configuration ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'akhilroyal151@gmail.com'  # <-- REPLACE with your Gmail address
app.config['MAIL_PASSWORD'] = 'sqdt prwr vlbf yzjb'      # <-- REPLACE with your App Password
mail = Mail(app)

# --- Leave Constants and Alert Threshold ---
NORMAL_MONTHLY_LIMIT = 4
MEDICAL_ANNUAL_LIMIT = 20 
FACULTY_ALERT_THRESHOLD_MINUTES = 30 # Time (in minutes) after forwarding to send a reminder
MINIMUM_ATTENDANCE_REQUIRED = 75.0 # Example Policy: Faculty must enforce this

# --- Database Setup ---

def get_db():
    """Connects to the SQLite database."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Closes the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Creates the necessary tables in the database if they don't exist."""
    db = get_db()
    try:
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
    except sqlite3.OperationalError as e:
        print(f"Database schema already exists or is locked: {e}")

# Initialize the database on startup
with app.app_context():
    init_db()

# --- Helper Functions ---

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user(user_id):
    """Fetches a user by their ID."""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    return user

def get_user_by_email(email):
    """Fetches a user by their email."""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    return user

def send_email_notification(recipient_email, subject, body):
    """Sends an email using Flask-Mail."""
    try:
        msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[recipient_email])
        msg.body = body
        mail.send(msg)
        print(f"Email sent successfully to {recipient_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")


def get_leave_template(student, leave_request, cr_name, faculty_name, salutation):
    """Generates the formal leave request letter content for CR/Faculty."""
    
    # Ensure dates are strings for strptime conversion
    start_date_str = leave_request['start_date']
    end_date_str = leave_request['end_date']
    
    try:
        # Check if dates are already datetime objects (from the database)
        if isinstance(leave_request['start_date'], datetime):
            start_dt = leave_request['start_date']
            end_dt = leave_request['end_date']
        else:
            start_dt = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date_str, '%Y-%m-%d')
            
    except TypeError:
        # Fallback for manual string conversion if needed
        start_dt = datetime.strptime(str(start_date_str), '%Y-%m-%d')
        end_dt = datetime.strptime(str(end_date_str), '%Y-%m-%d')

    days_requested = (end_dt - start_dt).days + 1
    
    template = f"""
Subject: Formal Leave Request - {student['first_name']} {student['second_name']} ({leave_request['leave_type']})

Date: {datetime.now().strftime('%Y-%m-%d')}

To,
The Faculty In-Charge ({faculty_name})
Cc: The Class Representative ({cr_name})
{student['branch']} Department
[College/Institution Name]

Dear Sir/Madam,

I am writing this letter to formally request a {leave_request['leave_type']} leave of absence from my academic duties.

Details of the Request:
- **Student Name:** {student['first_name']} {student['second_name']}
- **College ID:** {student['college_id']}
- **Branch:** {student['branch']}
- **Leave Type:** {leave_request['leave_type']}
- **Duration:** {start_dt.strftime('%B %d, %Y')} to {end_dt.strftime('%B %d, %Y')}
- **Total Days:** {days_requested} day(s)
- **Reason:** {leave_request['reason']}
- **Medical Certificate Attached:** {'Yes' if leave_request.get('medical_cert_path') else 'No'}

I assure you that I will catch up on all missed work immediately upon my return. I request that my leave be kindly approved.

{salutation}

Yours sincerely,

{student['first_name']} {student['second_name']}
Contact: {student['email']}
"""
    return template


def check_leave_limit(student_id, leave_type, start_date_str, end_date_str):
    """Checks if the leave request exceeds the specific limits (4 days/month Normal, 20 days/year Medical)."""
    db = get_db()
    
    try:
        leave_start = datetime.strptime(start_date_str, '%Y-%m-%d')
        leave_end = datetime.strptime(end_date_str, '%Y-%m-%d')
    except ValueError:
        return False, "Invalid date format provided."

    days_requested = (leave_end - leave_start).days + 1

    if days_requested <= 0:
         return False, "Leave duration must be at least one day."

    if leave_type == 'Normal':
        # Check against monthly limit (4 days per month)
        month_start = leave_start.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)
        
        # Calculate approved Normal Leave days this month
        total_days_this_month = db.execute(
            """
            SELECT SUM(JULIANDAY(end_date) - JULIANDAY(start_date) + 1) AS total
            FROM leave_requests 
            WHERE student_id = ? AND status = 'Approved' AND leave_type = 'Normal'
            AND start_date BETWEEN ? AND ?
            """,
            (student_id, month_start.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d'))
        ).fetchone()['total'] or 0

        if (total_days_this_month + days_requested) > NORMAL_MONTHLY_LIMIT:
            return False, f"Normal Leave limit exceeded. Maximum is {NORMAL_MONTHLY_LIMIT} days per month."

    elif leave_type == 'Medical':
        # Check against annual limit (20 days per year, assuming academic year starts in Jan for simplicity)
        year_start = leave_start.replace(month=1, day=1)
        year_end = leave_start.replace(month=12, day=31)

        # Calculate approved Medical Leave days this year
        total_days_this_year = db.execute(
            """
            SELECT SUM(JULIANDAY(end_date) - JULIANDAY(start_date) + 1) AS total
            FROM leave_requests 
            WHERE student_id = ? AND status = 'Approved' AND leave_type = 'Medical'
            AND start_date BETWEEN ? AND ?
            """,
            (student_id, year_start.strftime('%Y-%m-%d'), year_end.strftime('%Y-%m-%d'))
        ).fetchone()['total'] or 0
        
        if (total_days_this_year + days_requested) > MEDICAL_ANNUAL_LIMIT:
            return False, f"Medical Leave limit exceeded. Maximum is {MEDICAL_ANNUAL_LIMIT} days per year."

    return True, "Limit not exceeded."


def calculate_current_balance(student_id):
    """Calculates the current leave balance for Normal (monthly) and Medical (annual)."""
    db = get_db()
    now = datetime.now()
    
    # --- Normal Leave Balance (Monthly) ---
    month_start = now.replace(day=1).strftime('%Y-%m-%d')
    month_end = (now.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)).strftime('%Y-%m-%d')
    
    approved_normal = db.execute(
        """
        SELECT SUM(JULIANDAY(end_date) - JULIANDAY(start_date) + 1) AS total
        FROM leave_requests 
        WHERE student_id = ? AND status = 'Approved' AND leave_type = 'Normal'
        AND start_date BETWEEN ? AND ?
        """,
        (student_id, month_start, month_end)
    ).fetchone()['total'] or 0
    
    normal_balance = NORMAL_MONTHLY_LIMIT - approved_normal

    # --- Medical Leave Balance (Annual) ---
    year_start = now.replace(month=1, day=1).strftime('%Y-%m-%d')
    year_end = now.replace(month=12, day=31).strftime('%Y-%m-%d')

    approved_medical = db.execute(
        """
        SELECT SUM(JULIANDAY(end_date) - JULIANDAY(start_date) + 1) AS total
        FROM leave_requests 
        WHERE student_id = ? AND status = 'Approved' AND leave_type = 'Medical'
        AND start_date BETWEEN ? AND ?
        """,
        (student_id, year_start, year_end)
    ).fetchone()['total'] or 0
    
    medical_balance = MEDICAL_ANNUAL_LIMIT - approved_medical

    return {
        'normal_balance': max(0, normal_balance),
        'medical_balance': max(0, medical_balance)
    }

def get_request_summary(user_id):
    """Calculates the total number of approved, rejected, and pending requests."""
    db = get_db()
    
    approved = db.execute("SELECT COUNT(id) AS count FROM leave_requests WHERE student_id = ? AND status = 'Approved'", (user_id,)).fetchone()['count']
    rejected = db.execute("SELECT COUNT(id) AS count FROM leave_requests WHERE student_id = ? AND status = 'Rejected'", (user_id,)).fetchone()['count']
    pending = db.execute("SELECT COUNT(id) AS count FROM leave_requests WHERE student_id = ? AND status IN ('Pending', 'Forwarded')", (user_id,)).fetchone()['count']

    return {
        'approved': approved,
        'rejected': rejected,
        'pending': pending
    }

def get_compliance_status(user_id):
    """Determines the user's primary compliance status (used for Scorecard)."""
    db = get_db()
    
    # 1. Check Attendance Compliance (if user is student)
    user = get_user(user_id)
    if user['role'] == 'student':
        if user['attendance_percentage'] < MINIMUM_ATTENDANCE_REQUIRED:
            return "At Risk (Attendance)", "Your attendance is below the institutional minimum.", "danger"

        # 2. Check Leave Limit Overuse (last 3 months)
        three_months_ago = (datetime.now() - relativedelta(months=3)).strftime('%Y-%m-%d')
        recent_rejected = db.execute(
            "SELECT COUNT(id) AS count FROM leave_requests WHERE student_id = ? AND status = 'Rejected' AND created_at > ?", 
            (user_id, three_months_ago)
        ).fetchone()['count']
        
        if recent_rejected >= 3:
            return "Warning (High Rejection)", "You have high recent rejections. Review attendance.", "warning"

    return "Good Standing", "All compliance metrics are currently within policy limits.", "success"


# --- Routes ---

@app.route('/')
def index():
    """Renders the Home Page (index.html) on the root URL."""
    return render_template('index.html') 

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handles user signup."""
    if request.method == 'POST':
        try:
            db = get_db()
            first_name = request.form['first_name']
            second_name = request.form['second_name']
            email = request.form['email']
            branch = request.form['branch']
            role = request.form['role']
            college_id = request.form['college_id']
            password = request.form['password']
            confirm_password = request.form['confirm_password']

            if password != confirm_password:
                flash('Passwords do not match.', 'error')
                return render_template('signup.html')

            hashed_password = generate_password_hash(password)
            verification_token = str(uuid.uuid4())
            default_attendance = 0.0

            db.execute(
                "INSERT INTO users (first_name, second_name, email, branch, role, college_id, password_hash, verification_token, attendance_percentage) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (first_name, second_name, email, branch, role, college_id, hashed_password, verification_token, default_attendance)
            )
            db.commit()

            # Send email verification link
            subject = "Account Verification - Student Leave Management System"
            verification_link = url_for('verify_email', token=verification_token, _external=True)
            body = f"Hello {first_name},\n\nThank you for signing up. Please click the link below to verify your email address:\n\n{verification_link}\n\nThis link will redirect you to the login page.\n\nThank you,\nSLMS Team"
            send_email_notification(email, subject, body)

            return redirect(url_for('check_email'))

        except sqlite3.IntegrityError:
            flash('Email or College ID already exists.', 'error')
            return render_template('signup.html')
    
    return render_template('signup.html')

@app.route('/check_email')
def check_email():
    """New page to tell the user to check their email."""
    return render_template('check_email.html')

@app.route('/verify_email/<token>')
def verify_email(token):
    """Handles email verification."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE verification_token = ?", (token,)).fetchone()
    
    if user:
        db.execute("UPDATE users SET is_verified = 1 WHERE verification_token = ?", (token,))
        db.commit()
        flash("Your email has been successfully verified! You can now log in.", 'success')
        return redirect(url_for('login'))
    else:
        flash("The verification link is invalid or has expired.", 'error')
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ? AND role = ?', (email, role)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            # Check for the existence of the column before trying to read it
            if 'is_verified' in user.keys() and not user['is_verified']:
                flash('Please verify your email address before logging in.', 'error')
                return render_template('login.html')
            
            session['user_id'] = user['id']
            session['role'] = user['role']
            
            if role == 'student':
                return redirect(url_for('student_dashboard'))
            elif role == 'cr':
                return redirect(url_for('cr_dashboard'))
            elif role == 'faculty':
                return redirect(url_for('faculty_dashboard'))
            elif role == 'admin':
                return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid email, password or role.', 'error')
            return render_template('login.html')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs the user out."""
    session.clear()
    return redirect(url_for('index'))

@app.route('/student_dashboard', methods=['GET', 'POST'])
def student_dashboard():
    """Student dashboard logic."""
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))

    user = get_user(session['user_id'])
    db = get_db()
    
    leave_balance = calculate_current_balance(user['id'])
    request_summary = get_request_summary(user['id'])
    compliance_status = get_compliance_status(user['id'])
    
    # Handle leave application form submission
    if request.method == 'POST':
        reason = request.form['reason']
        start_date_str = request.form['start_date']
        end_date_str = request.form['end_date']
        leave_type = request.form['leave_type'] 
        salutation = request.form['salutation'] 
        medical_cert_path = None

        # 1. Handle File Upload (Mandatory for Medical Leave)
        if leave_type == 'Medical':
            if 'medical_cert' not in request.files or request.files['medical_cert'].filename == '':
                flash("Medical Leave requires a medical certificate file (PDF, JPG, PNG).", "error")
                return redirect(url_for('student_dashboard'))
            
            file = request.files['medical_cert']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{user['college_id']}_{uuid.uuid4().hex}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                medical_cert_path = filepath
            else:
                flash("Invalid file type. Only PDF, JPG, JPEG, PNG are allowed.", "error")
                return redirect(url_for('student_dashboard'))

        # 2. Check leave limits
        can_apply, message = check_leave_limit(user['id'], leave_type, start_date_str, end_date_str)
        if not can_apply:
            flash(message, "error")
            return redirect(url_for('student_dashboard'))

        # 3. Find CR and Faculty for the student's branch (Departmental Linkage Check)
        cr = db.execute("SELECT id, email, first_name FROM users WHERE role = 'cr' AND branch = ?", (user['branch'],)).fetchone()
        faculty = db.execute("SELECT id, email, first_name FROM users WHERE role = 'faculty' AND branch = ?", (user['branch'],)).fetchone()
        
        if not cr:
            flash(f"CR not found for {user['branch']} department. Cannot submit.", "error")
            return redirect(url_for('student_dashboard'))
        if not faculty:
            flash(f"Faculty not found for {user['branch']} department. Cannot submit.", "error")
            return redirect(url_for('student_dashboard'))


        # 4. Insert Request
        db.execute(
            "INSERT INTO leave_requests (student_id, reason, start_date, end_date, leave_type, status, cr_id, faculty_id, medical_cert_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user['id'], reason, start_date_str, end_date_str, leave_type, 'Pending', cr['id'] if cr else None, faculty['id'] if faculty else None, medical_cert_path)
        )
        db.commit()

        # 5. Generate Formal Leave Letter Content
        cr_name = cr['first_name'] if cr else "CR Not Found"
        faculty_name = faculty['first_name'] if faculty else "Faculty Not Found"
        
        new_request = {
            'start_date': start_date_str,
            'end_date': end_date_str,
            'reason': reason,
            'leave_type': leave_type,
            'medical_cert_path': medical_cert_path
        }
        leave_letter = get_leave_template(user, new_request, cr_name, faculty_name, salutation)


        # 6. Send specific email notifications
        if cr:
            subject = f"ACTION REQUIRED: New {leave_type} Leave Request from {user['branch']}"
            body = (f"Hello {cr['first_name']},\n\n"
                    f"A new {leave_type} leave request has been submitted by a student in your branch. "
                    f"Please go and check your dashboard to review and approve the leaves.\n\n"
                    f"*** LEAVE REQUEST FORMAL TEMPLATE ***\n"
                    f"{leave_letter}\n\n"
                    f"Thank you,\nSLMS Team")
            send_email_notification(cr['email'], subject, body)
        
        if faculty:
            subject = f"ALERT: New {leave_type} Leave Request Submitted by Student (Awaiting CR Forward)"
            body = (f"Hello {faculty['first_name']},\n\n"
                    f"A {leave_type} leave request has been submitted by a student in {user['branch']} branch. "
                    f"The Class Representative (CR) has been notified to review and forward it to you.\n\n"
                    f"Thank you,\nSLMS Team")
            send_email_notification(faculty['email'], subject, body)

        flash(f"{leave_type} Leave request submitted successfully! {salutation}", "success")
        return redirect(url_for('student_dashboard'))

    leave_requests = db.execute(
        'SELECT lr.*, u.first_name, u.second_name, u.email, u.college_id FROM leave_requests lr JOIN users u ON lr.student_id = u.id WHERE lr.student_id = ? ORDER BY lr.created_at DESC',
        (user['id'],)
    ).fetchall()


    return render_template('student_dashboard.html', user=user, leave_requests=leave_requests, balance=leave_balance, summary=request_summary, compliance=compliance_status)

@app.route('/profile', methods=['GET', 'POST'])
def update_profile():
    """Handles updating student profile details."""
    if 'user_id' not in session or session['role'] != 'student':
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    db = get_db()
    
    if request.method == 'POST':
        first_name = request.form['first_name']
        second_name = request.form['second_name']
        email = request.form['email']
        
        # Check for email conflict (must be unique, unless it's the current user's email)
        existing_user = db.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone()
        if existing_user:
            flash('Error: This email is already registered to another user.', 'error')
            return redirect(url_for('student_dashboard'))

        try:
            db.execute(
                "UPDATE users SET first_name = ?, second_name = ?, email = ? WHERE id = ?",
                (first_name, second_name, email, user_id)
            )
            db.commit()
            flash('Profile details updated successfully!', 'success')
            return redirect(url_for('student_dashboard'))
        except sqlite3.IntegrityError:
             flash('Error: Could not update profile due to data conflict.', 'error')
             return redirect(url_for('student_dashboard'))

    # If GET, user will be redirected back to dashboard with the modal open 
    return redirect(url_for('student_dashboard'))


@app.route('/cr_dashboard', methods=['GET', 'POST'])
def cr_dashboard():
    """CR dashboard logic."""
    if 'user_id' not in session or session['role'] != 'cr':
        return redirect(url_for('login'))

    user = get_user(session['user_id'])
    db = get_db()
    
    if request.method == 'POST':
        leave_id = request.form['leave_id']
        leave_request = db.execute('SELECT * FROM leave_requests WHERE id = ?', (leave_id,)).fetchone()
        
        if leave_request:
            # Update status and SAVE FORWARD TIME
            db.execute(
                "UPDATE leave_requests SET status = 'Forwarded', cr_id = ?, forward_time = ? WHERE id = ?",
                (user['id'], datetime.now(), leave_id)
            )
            db.commit()
            
            # Send specific email to faculty
            faculty = get_user(leave_request['faculty_id'])
            student = get_user(leave_request['student_id'])
            
            # Get necessary names for template generation
            cr_name = user['first_name']
            faculty_name = faculty['first_name'] if faculty else "Faculty Not Found"
            
            # --- Prepare request data for template generation ---
            leave_request_data = {
                'start_date': leave_request['start_date'].strftime('%Y-%m-%d'),
                'end_date': leave_request['end_date'].strftime('%Y-%m-%d'),
                'reason': leave_request['reason'],
                'leave_type': leave_request['leave_type']
            }
            
            leave_letter = get_leave_template(student, leave_request_data, cr_name, faculty_name, "Thank you for your consideration.")
            
            if faculty:
                subject = f"ACTION URGENT: {leave_request['leave_type']} Request FORWARDED by CR"
                body = (f"Hello {faculty['first_name']},\n\nA {leave_request['leave_type']} request from {student['first_name']} in your branch has been **FORWARDED** for your immediate approval. "
                        f"Please go and check your dashboard to approve/reject the leave. \n\n"
                        f"*** FORMAL LEAVE LETTER FOR APPROVAL ***\n"
                        f"{leave_letter}\n\n"
                        f"Thank you,\nSLMS Team")
                send_email_notification(faculty['email'], subject, body)

    pending_requests = db.execute(
        'SELECT lr.*, u.first_name, u.second_name, u.college_id, u.branch FROM leave_requests lr JOIN users u ON lr.student_id = u.id WHERE u.branch = ? AND lr.status IN (?, ?) ORDER BY lr.created_at DESC',
        (user['branch'], 'Pending', 'Forwarded')
    ).fetchall()
    
    return render_template('cr_dashboard.html', user=user, pending_requests=pending_requests)

@app.route('/faculty_dashboard', methods=['GET', 'POST'])
def faculty_dashboard():
    """Faculty dashboard logic."""
    if 'user_id' not in session or session['role'] != 'faculty':
        return redirect(url_for('login'))
    
    faculty_user = get_user(session['user_id'])
    db = get_db()
    
    # --- 1. ATTENDANCE SUBMISSION/UPDATE LOGIC ---
    if request.method == 'POST' and 'attendance_id' in request.form and 'action' not in request.form:
        student_id_to_update = request.form.get('attendance_id')
        new_percentage = request.form.get('attendance_percentage')
        
        try:
            new_percentage = float(new_percentage)
            if 0.0 <= new_percentage <= 100.0:
                db.execute(
                    "UPDATE users SET attendance_percentage = ? WHERE id = ?",
                    (new_percentage, student_id_to_update)
                )
                db.commit()
                flash(f"Attendance updated to {new_percentage}% for student ID {student_id_to_update}.", "success")
            else:
                flash("Attendance percentage must be between 0 and 100.", "error")
        except ValueError:
            flash("Invalid attendance percentage entered.", "error")
        
        # Prevent the page from processing a leave action after an attendance update
        return redirect(url_for('faculty_dashboard'))

    # --- 2. Check for Overdue Alerts every time the dashboard loads ---
    overdue_requests = db.execute(
        """
        SELECT lr.*, u.first_name, u.email
        FROM leave_requests lr
        JOIN users u ON lr.student_id = u.id
        WHERE lr.faculty_id = ? 
        AND lr.status = 'Forwarded' 
        AND lr.forward_time IS NOT NULL
        """,
        (faculty_user['id'],)
    ).fetchall()

    for req in overdue_requests:
        # NOTE: req['forward_time'] is a datetime.datetime object thanks to row_factory
        forward_time_dt = req['forward_time']
        time_elapsed = datetime.now() - forward_time_dt
        
        # Check if the request is older than the ALERT THRESHOLD (30 minutes)
        if time_elapsed > timedelta(minutes=FACULTY_ALERT_THRESHOLD_MINUTES):
            
            # Send the reminder email (simulates the recurring alert)
            subject = f"URGENT REMINDER: Overdue {req['leave_type']} Request Needs Approval"
            body = (f"Hello {faculty_user['first_name']},\n\n"
                    f"The {req['leave_type']} leave request from {req['first_name']} "
                    f"has been awaiting your approval for over {FACULTY_ALERT_THRESHOLD_MINUTES} minutes. "
                    f"Please log in to the system immediately to approve or reject the request.\n\n"
                    f"Thank you,\nSLMS Team")
            send_email_notification(faculty_user['email'], subject, body)
            
    # --- 3. Handle Approval/Rejection ---
    if request.method == 'POST' and 'leave_id' in request.form:
        leave_id = request.form['leave_id']
        action = request.form['action']
        status = 'Approved' if action == 'accept' else 'Rejected'
        
        # Get student's current attendance before final action
        student_id = db.execute("SELECT student_id FROM leave_requests WHERE id = ?", (leave_id,)).fetchone()['student_id']
        student_attendance = get_user(student_id)['attendance_percentage']
        
        if status == 'Approved' and student_attendance < MINIMUM_ATTENDANCE_REQUIRED:
            flash(f"Cannot Approve: Student's attendance is {student_attendance}% which is below the minimum required {MINIMUM_ATTENDANCE_REQUIRED}%.", "error")
            return redirect(url_for('faculty_dashboard'))
        
        db.execute(
            "UPDATE leave_requests SET status = ? WHERE id = ?",
            (status, leave_id)
        )
        db.commit()

        leave_request = db.execute('SELECT student_id, leave_type, start_date, end_date FROM leave_requests WHERE id = ?', (leave_id,)).fetchone()
        student = get_user(leave_request['student_id'])
        
        # --- Notification 1: Send confirmation email to student ---
        send_email_notification(
            student['email'], 
            f"{leave_request['leave_type']} Request {status}", 
            f"Your {leave_request['leave_type']} leave request has been {status} by the faculty. Please check your dashboard for details."
        )

        # --- Notification 2: Alert all other subject faculty in the department (New Feature) ---
        if status == 'Approved':
            # Get all faculty emails in the same branch, excluding the approving faculty
            other_faculty = db.execute(
                "SELECT email FROM users WHERE role = 'faculty' AND branch = ? AND id != ?",
                (faculty_user['branch'], faculty_user['id'])
            ).fetchall()
            
            if other_faculty:
                # Prepare a concise email for subject faculty
                subject = f"APPROVED LEAVE ALERT: {student['first_name']} {student['second_name']} - {leave_request['leave_type']}"
                body = (f"Please be advised that {student['first_name']} {student['second_name']} ({student['college_id']}) "
                        f"has an approved {leave_request['leave_type']} leave.\n\n"
                        f"ABSENCE DATES: {leave_request['start_date'].strftime('%Y-%m-%d')} to {leave_request['end_date'].strftime('%Y-%m-%d')}\n\n"
                        f"ACTION REQUIRED: Please mark the student absent in your subject records for these dates.\n\n"
                        f"Thank you, SLMS Alert System")

                # Send email to all other faculty emails found
                for faculty_record in other_faculty:
                    send_email_notification(faculty_record['email'], subject, body)


    # --- 4. Fetch Requests & Students in Faculty's Branch ---
    
    # Fetch all students for the Attendance Management Table
    all_students_in_branch = db.execute(
        'SELECT id, first_name, second_name, college_id, attendance_percentage FROM users WHERE role = "student" AND branch = ?',
        (faculty_user['branch'],)
    ).fetchall()

    # Fetch forwarded requests for the Leave Review Table
    forwarded_requests = db.execute(
        'SELECT lr.*, u.first_name, u.second_name, u.college_id, u.branch, u.attendance_percentage FROM leave_requests lr JOIN users u ON lr.student_id = u.id WHERE u.branch = ? AND lr.status IN (?, ?) ORDER BY lr.created_at DESC',
        (faculty_user['branch'], 'Pending', 'Forwarded')
    ).fetchall()
    

    return render_template('faculty_dashboard.html', 
                           user=faculty_user, 
                           forwarded_requests=forwarded_requests, 
                           all_students=all_students_in_branch,
                           min_attendance=MINIMUM_ATTENDANCE_REQUIRED)

@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    """Admin dashboard logic."""
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    user = get_user(session['user_id'])
    db = get_db()
    
    # --- System Health Data (New Feature for Admin) ---
    total_users = db.execute("SELECT COUNT(id) FROM users").fetchone()[0]
    unverified_users = db.execute("SELECT COUNT(id) FROM users WHERE is_verified = 0").fetchone()[0]
    pending_requests_count = db.execute("SELECT COUNT(id) FROM leave_requests WHERE status IN ('Pending', 'Forwarded')").fetchone()[0]
    
    # Example Query for non-compliant students (low attendance)
    non_compliant_students = db.execute("SELECT COUNT(id) FROM users WHERE role = 'student' AND attendance_percentage < ?", (MINIMUM_ATTENDANCE_REQUIRED,)).fetchone()[0]

    system_health = {
        'total_users': total_users,
        'unverified_users': unverified_users,
        'pending_requests': pending_requests_count,
        'non_compliant_students': non_compliant_students
    }


    if request.method == 'POST':
        action = request.form.get('action')
        user_id = request.form.get('user_id')

        if action == 'delete':
            db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            db.commit()
        elif action == 'edit':
            pass
    
    all_users = db.execute('SELECT * FROM users ORDER BY role, first_name').fetchall()
    
    report_data = None
    if request.args.get('report_start') and request.args.get('report_end'):
        start_date = request.args.get('report_start')
        end_date = request.args.get('report_end')
        report_data = db.execute(
            'SELECT lr.*, u.first_name, u.second_name, u.branch, u.role FROM leave_requests lr JOIN users u ON lr.student_id = u.id WHERE start_date BETWEEN ? AND ? ORDER BY created_at',
            (start_date, end_date)
        ).fetchall()

    return render_template('admin_dashboard.html', user=user, all_users=all_users, report_data=report_data, system_health=system_health)

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)