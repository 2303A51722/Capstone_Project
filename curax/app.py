import os
import re
import uuid
import secrets
from pathlib import Path
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session,
    abort, send_from_directory, current_app
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from database import get_db, init_app as init_database

load_dotenv()
csrf = CSRFProtect()

ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_FILE_SIZE = 10 * 1024 * 1024
ROLES = {"patient", "doctor", "diagnostic", "insurance"}
CATEGORIES = ["Lab Report", "Prescription", "Diagnostic Report", "Blood Test",
              "X-Ray", "MRI", "ECG", "Discharge Summary", "Other"]

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "dev-only-change-this-secret"),
        DATABASE_PATH=os.getenv("DATABASE_PATH", str(Path(app.instance_path) / "curax.db")),
        UPLOAD_FOLDER=os.getenv("UPLOAD_FOLDER", str(Path(app.root_path) / "uploads")),
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", MAX_FILE_SIZE)),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    csrf.init_app(app)
    init_database(app)

    @app.context_processor
    def inject_globals():
        return {"current_user": get_current_user(), "categories": CATEGORIES}

    def add_notification(user_id, message):
        db = get_db()
        db.execute("INSERT INTO notifications(user_id,message) VALUES(?,?)", (user_id, message))
        db.commit()

    def get_current_user():
        uid = session.get("user_id")
        if not uid:
            return None
        return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not get_current_user():
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped

    def roles_required(*roles):
        def decorator(view):
            @wraps(view)
            @login_required
            def wrapped(*args, **kwargs):
                user = get_current_user()
                if user["role"] not in roles:
                    abort(403)
                return view(*args, **kwargs)
            return wrapped
        return decorator

    def dashboard_endpoint(role):
        return {"patient":"patient_dashboard", "doctor":"doctor_dashboard",
                "diagnostic":"diagnostic_dashboard", "insurance":"insurance_dashboard"}[role]

    def can_access_patient(patient_id, user=None):
        user = user or get_current_user()
        if not user:
            return False
        if user["role"] == "patient":
            return user["id"] == patient_id
        if user["role"] == "doctor":
            row = get_db().execute(
                "SELECT 1 FROM doctor_patient_access WHERE doctor_id=? AND patient_id=?",
                (user["id"], patient_id)).fetchone()
            return row is not None
        if user["role"] in ("diagnostic", "insurance"):
            return True
        return False

    def require_patient_access(patient_id):
        if not can_access_patient(patient_id):
            abort(403)

    def patient_code():
        return "CX-" + secrets.token_hex(4).upper()

    def file_signature_ok(ext, data):
        if ext == "pdf":
            return data.startswith(b"%PDF-")
        if ext in ("jpg", "jpeg"):
            return data.startswith(b"\xff\xd8\xff")
        if ext == "png":
            return data.startswith(b"\x89PNG\r\n\x1a\n")
        return False

    def save_upload(file_storage, patient_id, title, category, description=""):
        if not file_storage or not file_storage.filename:
            raise ValueError("Choose a file to upload.")
        original = secure_filename(file_storage.filename)
        if not original or "." not in original:
            raise ValueError("Invalid filename.")
        ext = original.rsplit(".", 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError("Only PDF, JPG, JPEG and PNG files are allowed.")
        data = file_storage.read(MAX_FILE_SIZE + 1)
        if len(data) > MAX_FILE_SIZE:
            raise ValueError("File must be 10 MB or smaller.")
        if not file_signature_ok(ext, data):
            raise ValueError("The file content does not match its extension.")
        mime = {"pdf":"application/pdf","jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png"}[ext]
        stored = uuid.uuid4().hex + "." + ext
        target = upload_directory() / stored
        target.write_bytes(data)
        db = get_db()
        cur = db.execute("""INSERT INTO medical_records
            (patient_id,uploaded_by,title,category,description,stored_name,original_name,mime_type)
            VALUES(?,?,?,?,?,?,?,?)""",
            (patient_id, get_current_user()["id"], title.strip(), category, description.strip(),
             stored, original, mime))
        db.commit()
        return cur.lastrowid

    def upload_directory():
        path = Path(app.config["UPLOAD_FOLDER"])
        path.mkdir(parents=True, exist_ok=True)
        return path

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            message = request.form.get("message", "").strip()
            if not name or not email or not message or len(message) > 3000:
                flash("Please complete all fields. Message must be under 3000 characters.", "danger")
            else:
                # Contact submissions are acknowledged; no external email service is configured.
                flash("Thank you. Your message has been received by the application. Email delivery is not configured.", "success")
                return redirect(url_for("contact"))
        return render_template("contact.html")

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            role = request.form.get("role", "").strip()
            if not all([username, email, password, full_name, role]):
                flash("Complete all required fields.", "danger")
            elif role not in ROLES:
                flash("Choose a valid account role.", "danger")
            elif len(password) < 8:
                flash("Password must contain at least 8 characters.", "danger")
            elif not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
                flash("Username must be 3–30 characters and use letters, numbers, dot, dash or underscore.", "danger")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                flash("Enter a valid email address.", "danger")
            else:
                db = get_db()
                try:
                    cur = db.execute("""INSERT INTO users(username,email,password_hash,role,full_name,phone)
                        VALUES(?,?,?,?,?,?)""",
                        (username, email, generate_password_hash(password), role, full_name, phone))
                    uid = cur.lastrowid
                    if role == "patient":
                        db.execute("INSERT INTO patients(user_id,patient_code) VALUES(?,?)", (uid, patient_code()))
                    elif role == "doctor":
                        db.execute("INSERT INTO doctors(user_id,specialization,registration_number,workplace) VALUES(?,?,?,?)",
                                   (uid, request.form.get("specialization","").strip(),
                                    request.form.get("registration_number","").strip(),
                                    request.form.get("workplace","").strip()))
                    elif role == "diagnostic":
                        db.execute("INSERT INTO diagnostic_centers(user_id,center_name,address,license_number) VALUES(?,?,?,?)",
                                   (uid, request.form.get("organization_name",full_name).strip(),
                                    request.form.get("organization_address","").strip(),
                                    request.form.get("license_number","").strip()))
                    else:
                        db.execute("INSERT INTO insurance_providers(user_id,company_name,address,support_phone) VALUES(?,?,?,?)",
                                   (uid, request.form.get("organization_name",full_name).strip(),
                                    request.form.get("organization_address","").strip(), phone))
                    db.commit()
                    flash("Account created. You can now log in.", "success")
                    return redirect(url_for("login"))
                except Exception as exc:
                    db.rollback()
                    if "UNIQUE" in str(exc).upper():
                        flash("That username or email is already registered.", "danger")
                    else:
                        current_app.logger.exception("Registration failed")
                        flash("Registration could not be completed.", "danger")
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            identity = request.form.get("identity", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE",
                                    (identity, identity)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                session["linked_accounts"] = [user["id"]]
                flash(f"Welcome, {user['full_name']}.", "success")
                return redirect(url_for(dashboard_endpoint(user["role"])))
            flash("Invalid username/email or password.", "danger")
        return render_template("login.html")

    @app.route("/switch-account", methods=["GET", "POST"])
    @login_required
    def switch_account():
        """Switch only among accounts individually authenticated in this session."""
        db = get_db()
        active = get_current_user()
        ids = [i for i in session.get("linked_accounts", []) if isinstance(i, int)]
        if active["id"] not in ids:
            ids.append(active["id"])
        if request.method == "POST":
            action = request.form.get("action", "")
            if action == "switch":
                try:
                    target_id = int(request.form.get("account_id", ""))
                except ValueError:
                    abort(400)
                if target_id not in ids:
                    abort(403)
                target = db.execute("SELECT id,role FROM users WHERE id=?", (target_id,)).fetchone()
                if not target:
                    abort(404)
                session["user_id"] = target["id"]
                session.modified = True
                return redirect(url_for(dashboard_endpoint(target["role"])))
            if action == "add":
                identity = request.form.get("identity", "").strip()
                password = request.form.get("password", "")
                target = db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE", (identity, identity)).fetchone()
                if target and check_password_hash(target["password_hash"], password):
                    if target["id"] not in ids:
                        ids.append(target["id"])
                    session["linked_accounts"] = ids
                    session["user_id"] = target["id"]
                    flash("Account added. You can now switch between your signed-in accounts.", "success")
                    return redirect(url_for(dashboard_endpoint(target["role"])))
                flash("Invalid username/email or password.", "danger")
            else:
                abort(400)
        accounts = []
        for uid in ids:
            account = db.execute("SELECT id,full_name,role FROM users WHERE id=?", (uid,)).fetchone()
            if account:
                accounts.append(account)
        return render_template("switch_account.html", accounts=accounts)

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            # For this local student project, avoid exposing whether an account exists.
            if user:
                flash("Password reset by email is not yet configured. Please contact the application administrator.", "info")
            else:
                flash("If the account exists, reset instructions would be sent.", "info")
            return redirect(url_for("login"))
        return render_template("forgot_password.html")

    @app.get("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("index"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        return redirect(url_for(dashboard_endpoint(get_current_user()["role"])))

    @app.get("/dashboard/patient")
    @roles_required("patient")
    def patient_dashboard():
        user = get_current_user()
        db = get_db()
        patient = db.execute("SELECT * FROM patients WHERE user_id=?", (user["id"],)).fetchone()
        records = db.execute("SELECT * FROM medical_records WHERE patient_id=? ORDER BY uploaded_at DESC LIMIT 5",
                             (user["id"],)).fetchall()
        claims = db.execute("SELECT * FROM insurance_claims WHERE patient_id=? ORDER BY submitted_at DESC LIMIT 5",
                            (user["id"],)).fetchall()
        prescriptions = db.execute("SELECT p.*,u.full_name AS doctor_name FROM prescriptions p JOIN users u ON u.id=p.doctor_id WHERE p.patient_id=? ORDER BY p.created_at DESC LIMIT 5",
                                   (user["id"],)).fetchall()
        return render_template("patient_dashboard.html", patient=patient, records=records, claims=claims,
                               prescriptions=prescriptions)

    @app.get("/dashboard/doctor")
    @roles_required("doctor")
    def doctor_dashboard():
        user = get_current_user()
        patients = get_db().execute("""SELECT u.id,u.full_name,u.email,p.patient_code
            FROM doctor_patient_access a JOIN users u ON u.id=a.patient_id
            JOIN patients p ON p.user_id=u.id WHERE a.doctor_id=? ORDER BY u.full_name""",
            (user["id"],)).fetchall()
        return render_template("doctor_dashboard.html", patients=patients)

    @app.get("/dashboard/diagnostic")
    @roles_required("diagnostic")
    def diagnostic_dashboard():
        user = get_current_user()
        reports = get_db().execute("""SELECT d.*,u.full_name AS patient_name,p.patient_code
            FROM diagnostic_reports d JOIN users u ON u.id=d.patient_id
            JOIN patients p ON p.user_id=u.id WHERE d.center_id=? ORDER BY d.created_at DESC LIMIT 10""",
            (user["id"],)).fetchall()
        return render_template("diagnostic_dashboard.html", reports=reports)

    @app.get("/dashboard/insurance")
    @roles_required("insurance")
    def insurance_dashboard():
        user = get_current_user()
        db = get_db()
        claims = db.execute("""SELECT c.*,u.full_name AS patient_name,p.patient_code
            FROM insurance_claims c JOIN users u ON u.id=c.patient_id
            JOIN patients p ON p.user_id=u.id WHERE c.provider_id=?
            ORDER BY c.submitted_at DESC""", (user["id"],)).fetchall()
        counts = {s: db.execute("SELECT COUNT(*) n FROM insurance_claims WHERE provider_id=? AND status=?",
                                (user["id"],s)).fetchone()["n"]
                  for s in ("Submitted","Under Review","Approved","Rejected")}
        return render_template("insurance_dashboard.html", claims=claims, counts=counts)

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        user = get_current_user()
        db = get_db()
        if request.method == "POST":
            full_name = request.form.get("full_name","").strip()
            phone = request.form.get("phone","").strip()
            if not full_name:
                flash("Full name is required.", "danger")
            else:
                db.execute("UPDATE users SET full_name=?,phone=? WHERE id=?", (full_name,phone,user["id"]))
                if user["role"] == "patient":
                    db.execute("UPDATE patients SET date_of_birth=?,gender=?,address=?,emergency_contact=? WHERE user_id=?",
                               (request.form.get("date_of_birth",""),request.form.get("gender",""),
                                request.form.get("address",""),request.form.get("emergency_contact",""),user["id"]))
                elif user["role"] == "doctor":
                    db.execute("UPDATE doctors SET specialization=?,registration_number=?,workplace=? WHERE user_id=?",
                               (request.form.get("specialization",""),request.form.get("registration_number",""),
                                request.form.get("workplace",""),user["id"]))
                elif user["role"] == "diagnostic":
                    db.execute("UPDATE diagnostic_centers SET center_name=?,address=?,license_number=? WHERE user_id=?",
                               (request.form.get("organization_name",""),request.form.get("organization_address",""),
                                request.form.get("license_number",""),user["id"]))
                elif user["role"] == "insurance":
                    db.execute("UPDATE insurance_providers SET company_name=?,address=?,support_phone=? WHERE user_id=?",
                               (request.form.get("organization_name",""),request.form.get("organization_address",""),
                                phone,user["id"]))
                db.commit()
                flash("Profile updated.", "success")
                return redirect(url_for("profile"))
        extra = None
        table = {"patient":"patients","doctor":"doctors","diagnostic":"diagnostic_centers",
                 "insurance":"insurance_providers"}[user["role"]]
        extra = db.execute(f"SELECT * FROM {table} WHERE user_id=?", (user["id"],)).fetchone()
        return render_template("profile.html", user=user, extra=extra)

    @app.route("/records", methods=["GET", "POST"])
    @login_required
    def records():
        user = get_current_user()
        db = get_db()
        if request.method == "POST":
            if user["role"] not in ("patient", "doctor", "diagnostic"):
                abort(403)
            if user["role"] == "patient":
                pid = user["id"]
            else:
                try:
                    pid = int(request.form.get("patient_id",""))
                except ValueError:
                    flash("Enter a valid patient account ID.", "danger")
                    return redirect(url_for("records"))
            require_patient_access(pid)
            patient = db.execute("SELECT id FROM users WHERE id=? AND role='patient'", (pid,)).fetchone()
            if not patient:
                abort(404)
            title = request.form.get("title","").strip()
            category = request.form.get("category","")
            if not title or category not in CATEGORIES:
                flash("Enter a title and valid category.", "danger")
            else:
                try:
                    save_upload(request.files.get("file"), pid, title, category, request.form.get("description",""))
                    add_notification(pid, f"A medical record was uploaded: {title}.")
                    flash("Medical record uploaded successfully.", "success")
                except ValueError as exc:
                    flash(str(exc), "danger")
            return redirect(url_for("records"))
        query = request.args.get("q","").strip()
        category = request.args.get("category","").strip()
        if user["role"] == "patient":
            sql = "SELECT r.*,u.full_name AS uploader FROM medical_records r JOIN users u ON u.id=r.uploaded_by WHERE r.patient_id=?"
            params = [user["id"]]
        elif user["role"] == "doctor":
            sql = """SELECT r.*,u.full_name AS uploader FROM medical_records r
                JOIN users u ON u.id=r.uploaded_by JOIN doctor_patient_access a ON a.patient_id=r.patient_id
                WHERE a.doctor_id=?"""
            params = [user["id"]]
        elif user["role"] == "diagnostic":
            sql = "SELECT r.*,u.full_name AS uploader FROM medical_records r JOIN users u ON u.id=r.uploaded_by WHERE r.uploaded_by=?"
            params = [user["id"]]
        else:
            sql = """SELECT r.*,u.full_name AS uploader FROM medical_records r
                JOIN users u ON u.id=r.uploaded_by JOIN insurance_claims c ON c.patient_id=r.patient_id
                JOIN claim_documents cd ON cd.claim_id=c.id AND cd.record_id=r.id WHERE c.provider_id=?"""
            params = [user["id"]]
        if query:
            sql += " AND (r.title LIKE ? OR r.description LIKE ? OR r.original_name LIKE ?)"
            params += [f"%{query}%"] * 3
        if category in CATEGORIES:
            sql += " AND r.category=?"
            params.append(category)
        sql += " ORDER BY r.uploaded_at DESC"
        rows = db.execute(sql, params).fetchall()
        return render_template("medical_reports.html", records=rows, query=query, selected_category=category)

    @app.get("/records/<int:record_id>/download")
    @login_required
    def download_record(record_id):
        user = get_current_user()
        row = get_db().execute("SELECT * FROM medical_records WHERE id=?", (record_id,)).fetchone()
        if not row:
            abort(404)
        if user["role"] == "patient":
            allowed = row["patient_id"] == user["id"]
        elif user["role"] == "doctor":
            allowed = can_access_patient(row["patient_id"], user)
        elif user["role"] == "diagnostic":
            allowed = row["uploaded_by"] == user["id"]
        else:
            allowed = get_db().execute("""SELECT 1 FROM claim_documents cd
                JOIN insurance_claims c ON c.id=cd.claim_id WHERE cd.record_id=? AND c.provider_id=?""",
                (record_id,user["id"])).fetchone() is not None
        if not allowed:
            abort(403)
        return send_from_directory(upload_directory(), row["stored_name"],
                                   as_attachment=True, download_name=row["original_name"],
                                   mimetype=row["mime_type"])

    @app.post("/records/<int:record_id>/delete")
    @roles_required("patient")
    def delete_record(record_id):
        user = get_current_user()
        db = get_db()
        row = db.execute("SELECT * FROM medical_records WHERE id=? AND patient_id=?",
                         (record_id,user["id"])).fetchone()
        if not row:
            abort(404)
        path = Path(current_app.config["UPLOAD_FOLDER"]) / row["stored_name"]
        db.execute("DELETE FROM medical_records WHERE id=?", (record_id,))
        db.commit()
        if path.exists():
            path.unlink()
        flash("Record deleted.", "success")
        return redirect(url_for("records"))

    @app.route("/doctor/patients", methods=["GET", "POST"])
    @roles_required("doctor")
    def doctor_patients():
        user = get_current_user()
        db = get_db()
        if request.method == "POST":
            code = request.form.get("patient_code","").strip().upper()
            patient = db.execute("""SELECT u.id,u.full_name,p.patient_code FROM patients p
                JOIN users u ON u.id=p.user_id WHERE p.patient_code=?""", (code,)).fetchone()
            if not patient:
                flash("No patient found with that Patient ID.", "danger")
            else:
                db.execute("INSERT OR IGNORE INTO doctor_patient_access(doctor_id,patient_id) VALUES(?,?)",
                           (user["id"],patient["id"]))
                db.commit()
                add_notification(patient["id"], f"Doctor {user['full_name']} was added to your records access list. Contact the administrator if this was not authorized.")
                flash(f"Patient {patient['full_name']} added to your authorized list.", "success")
            return redirect(url_for("doctor_patients"))
        patients = db.execute("""SELECT u.id,u.full_name,u.email,p.patient_code
            FROM doctor_patient_access a JOIN users u ON u.id=a.patient_id
            JOIN patients p ON p.user_id=u.id WHERE a.doctor_id=?""", (user["id"],)).fetchall()
        return render_template("doctor_patients.html", patients=patients)

    @app.route("/doctor/patients/<int:patient_id>", methods=["GET"])
    @roles_required("doctor")
    def doctor_patient_detail(patient_id):
        require_patient_access(patient_id)
        db = get_db()
        patient = db.execute("""SELECT u.*,p.* FROM users u JOIN patients p ON p.user_id=u.id
            WHERE u.id=?""", (patient_id,)).fetchone()
        records = db.execute("SELECT * FROM medical_records WHERE patient_id=? ORDER BY uploaded_at DESC",
                             (patient_id,)).fetchall()
        prescriptions = db.execute("SELECT * FROM prescriptions WHERE patient_id=? ORDER BY created_at DESC",
                                   (patient_id,)).fetchall()
        return render_template("doctor_patient_detail.html", patient=patient, records=records,
                               prescriptions=prescriptions)

    @app.post("/doctor/prescriptions")
    @roles_required("doctor")
    def add_prescription():
        try:
            pid = int(request.form.get("patient_id",""))
        except ValueError:
            abort(400)
        require_patient_access(pid)
        diagnosis = request.form.get("diagnosis","").strip()
        if not diagnosis:
            flash("Diagnosis notes are required.", "danger")
        else:
            db = get_db()
            db.execute("""INSERT INTO prescriptions(patient_id,doctor_id,diagnosis,treatment_notes,medication_notes)
                VALUES(?,?,?,?,?)""", (pid,get_current_user()["id"],diagnosis,
                request.form.get("treatment_notes","").strip(),request.form.get("medication_notes","").strip()))
            db.commit()
            add_notification(pid, "A doctor added a prescription/clinical note to your account.")
            flash("Prescription note saved.", "success")
        return redirect(url_for("doctor_patient_detail", patient_id=pid))

    @app.post("/doctor/records")
    @roles_required("doctor")
    def doctor_upload_record():
        try:
            pid = int(request.form.get("patient_id", ""))
        except ValueError:
            abort(400)
        require_patient_access(pid)
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "")
        if not title or category not in CATEGORIES:
            flash("Enter a title and valid category.", "danger")
        else:
            try:
                save_upload(request.files.get("file"), pid, title, category,
                            request.form.get("description", ""))
                add_notification(pid, f"Your doctor uploaded a medical document: {title}.")
                flash("Medical report uploaded.", "success")
            except ValueError as exc:
                flash(str(exc), "danger")
        return redirect(url_for("doctor_patient_detail", patient_id=pid))

    @app.route("/diagnostic/tests", methods=["GET", "POST"])
    @roles_required("diagnostic")
    def diagnostic_tests():
        user = get_current_user()
        db = get_db()
        if request.method == "POST":
            code = request.form.get("patient_code","").strip().upper()
            patient = db.execute("""SELECT u.id FROM patients p JOIN users u ON u.id=p.user_id
                WHERE p.patient_code=?""", (code,)).fetchone()
            test_name = request.form.get("test_name","").strip()
            if not patient or not test_name:
                flash("Enter a valid Patient ID and test name.", "danger")
            else:
                try:
                    record_id = None
                    if request.files.get("file") and request.files["file"].filename:
                        record_id = save_upload(request.files["file"], patient["id"], test_name,
                            request.form.get("category","Diagnostic Report"),
                            request.form.get("findings",""))
                    db.execute("""INSERT INTO diagnostic_reports(patient_id,center_id,test_name,test_date,findings,record_id)
                        VALUES(?,?,?,?,?,?)""", (patient["id"],user["id"],test_name,
                        request.form.get("test_date",""),request.form.get("findings",""),record_id))
                    db.commit()
                    add_notification(patient["id"], f"Diagnostic report added: {test_name}.")
                    flash("Diagnostic test details saved.", "success")
                except ValueError as exc:
                    flash(str(exc), "danger")
            return redirect(url_for("diagnostic_tests"))
        reports = db.execute("""SELECT d.*,u.full_name AS patient_name,p.patient_code
            FROM diagnostic_reports d JOIN users u ON u.id=d.patient_id
            JOIN patients p ON p.user_id=u.id WHERE d.center_id=? ORDER BY d.created_at DESC""",
            (user["id"],)).fetchall()
        return render_template("diagnostic_tests.html", reports=reports)

    @app.route("/claims", methods=["GET", "POST"])
    @login_required
    def claims():
        user = get_current_user()
        db = get_db()
        if request.method == "POST":
            if user["role"] != "patient":
                abort(403)
            try:
                amount = float(request.form.get("claim_amount","0"))
                provider_id = int(request.form.get("provider_id",""))
            except ValueError:
                flash("Enter a valid provider and claim amount.", "danger")
                return redirect(url_for("claims"))
            policy = request.form.get("policy_number","").strip()
            hospital = request.form.get("hospital_name","").strip()
            treatment = request.form.get("treatment_details","").strip()
            exists = db.execute("""SELECT id FROM insurance_policies WHERE patient_id=?
                AND provider_id=? AND policy_number=?""", (user["id"],provider_id,policy)).fetchone()
            if amount <= 0 or not policy or not hospital or not treatment or not exists:
                flash("Provide valid claim details and a policy already linked to your account.", "danger")
            else:
                ref = "CLM-" + secrets.token_hex(5).upper()
                db.execute("""INSERT INTO insurance_claims(claim_ref,patient_id,provider_id,policy_number,
                    claim_amount,hospital_name,treatment_details) VALUES(?,?,?,?,?,?,?)""",
                    (ref,user["id"],provider_id,policy,amount,hospital,treatment))
                claim_id = db.execute("SELECT id FROM insurance_claims WHERE claim_ref=?", (ref,)).fetchone()["id"]
                for rid in request.form.getlist("record_ids"):
                    rec = db.execute("SELECT id FROM medical_records WHERE id=? AND patient_id=?",
                                     (rid,user["id"])).fetchone()
                    if rec:
                        db.execute("INSERT OR IGNORE INTO claim_documents(claim_id,record_id) VALUES(?,?)",
                                   (claim_id,rec["id"]))
                db.commit()
                add_notification(provider_id, f"New insurance claim submitted: {ref}.")
                flash(f"Claim submitted. Reference: {ref}", "success")
                return redirect(url_for("claims"))
        if user["role"] == "patient":
            my_claims = db.execute("""SELECT c.*,u.full_name AS provider_name FROM insurance_claims c
                JOIN users u ON u.id=c.provider_id WHERE c.patient_id=? ORDER BY c.submitted_at DESC""",
                (user["id"],)).fetchall()
            providers = db.execute("SELECT id,full_name FROM users WHERE role='insurance' ORDER BY full_name").fetchall()
            policies = db.execute("""SELECT ip.*,u.full_name AS provider_name FROM insurance_policies ip
                JOIN users u ON u.id=ip.provider_id WHERE ip.patient_id=?""", (user["id"],)).fetchall()
            records = db.execute("SELECT id,title,category FROM medical_records WHERE patient_id=?",
                                 (user["id"],)).fetchall()
            return render_template("claims.html", claims=my_claims, providers=providers,
                                   policies=policies, records=records)
        if user["role"] == "insurance":
            my_claims = db.execute("""SELECT c.*,u.full_name AS patient_name,p.patient_code
                FROM insurance_claims c JOIN users u ON u.id=c.patient_id
                JOIN patients p ON p.user_id=u.id WHERE c.provider_id=? ORDER BY c.submitted_at DESC""",
                (user["id"],)).fetchall()
            return render_template("claims.html", claims=my_claims, providers=[], policies=[], records=[])
        abort(403)

    @app.post("/claims/<int:claim_id>/review")
    @roles_required("insurance")
    def review_claim(claim_id):
        status = request.form.get("status","")
        remarks = request.form.get("remarks","").strip()
        if status not in ("Under Review","Approved","Rejected"):
            abort(400)
        if status == "Rejected" and not remarks:
            flash("A rejection reason is required.", "danger")
            return redirect(url_for("claims"))
        db = get_db()
        claim = db.execute("SELECT * FROM insurance_claims WHERE id=? AND provider_id=?",
                           (claim_id,get_current_user()["id"])).fetchone()
        if not claim:
            abort(404)
        db.execute("""UPDATE insurance_claims SET status=?,remarks=?,reviewed_by=?,updated_at=CURRENT_TIMESTAMP
            WHERE id=?""", (status,remarks,get_current_user()["id"],claim_id))
        db.commit()
        add_notification(claim["patient_id"], f"Your claim {claim['claim_ref']} status changed to {status}.")
        flash("Claim status updated.", "success")
        return redirect(url_for("claims"))

    @app.route("/insurance/policies", methods=["GET", "POST"])
    @roles_required("insurance")
    def policies():
        user = get_current_user()
        db = get_db()
        if request.method == "POST":
            code = request.form.get("patient_code","").strip().upper()
            patient = db.execute("SELECT user_id FROM patients WHERE patient_code=?", (code,)).fetchone()
            policy = request.form.get("policy_number","").strip()
            if not patient or not policy:
                flash("Enter a valid Patient ID and policy number.", "danger")
            else:
                try:
                    db.execute("""INSERT INTO insurance_policies(patient_id,provider_id,policy_number,coverage_details,valid_until)
                        VALUES(?,?,?,?,?)""", (patient["user_id"],user["id"],policy,
                        request.form.get("coverage_details","").strip(),request.form.get("valid_until","")))
                    db.commit()
                    add_notification(patient["user_id"], f"An insurance policy ({policy}) was linked to your account.")
                    flash("Policy linked to patient.", "success")
                except Exception:
                    db.rollback()
                    flash("That policy number is already registered with this provider.", "danger")
            return redirect(url_for("policies"))
        rows = db.execute("""SELECT ip.*,u.full_name AS patient_name,p.patient_code FROM insurance_policies ip
            JOIN users u ON u.id=ip.patient_id JOIN patients p ON p.user_id=u.id
            WHERE ip.provider_id=? ORDER BY ip.created_at DESC""", (user["id"],)).fetchall()
        return render_template("policies.html", policies=rows)

    @app.get("/notifications")
    @login_required
    def notifications():
        user = get_current_user()
        db = get_db()
        rows = db.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC",
                          (user["id"],)).fetchall()
        db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user["id"],))
        db.commit()
        return render_template("notifications.html", notifications=rows)

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="You do not have permission to access this resource."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="The page or record could not be found."), 404

    @app.errorhandler(413)
    def too_large(_error):
        flash("Upload too large. Maximum file size is 10 MB.", "danger")
        return redirect(request.referrer or url_for("dashboard"))

    @app.errorhandler(500)
    def server_error(_error):
        current_app.logger.exception("Unexpected application error")
        return render_template("error.html", code=500, message="An unexpected error occurred."), 500

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=os.getenv("FLASK_DEBUG","0") == "1")
