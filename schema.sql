CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    second_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    branch TEXT NOT NULL,
    role TEXT NOT NULL,
    college_id TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 0,         -- REQUIRED for Email Verification
    verification_token TEXT UNIQUE,                 -- REQUIRED for Email Verification
    attendance_percentage REAL DEFAULT 0.0          -- REQUIRED for Faculty Attendance
);

CREATE TABLE IF NOT EXISTS leave_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    leave_type TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    forward_time TIMESTAMP,                         -- CRITICAL: Missing column for timed alerts
    cr_id INTEGER,
    faculty_id INTEGER,
    FOREIGN KEY(student_id) REFERENCES users(id),
    FOREIGN KEY(cr_id) REFERENCES users(id),
    FOREIGN KEY(faculty_id) REFERENCES users(id)
);
