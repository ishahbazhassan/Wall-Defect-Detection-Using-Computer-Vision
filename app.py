import os
import sys
import base64
import logging
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.utils import secure_filename
from config import Config
from models import db, User, ImageJob
from processing import detect_defects
from flaskwebgui import FlaskUI

# ======================================================
# Determine BASE_DIR (for both normal & compiled .exe runs)
# ======================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS 
else:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ======================================================
# Flask App Setup
# ======================================================
app = Flask(__name__)
app.config.from_object(Config)

app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")
app.config["PROCESSED_FOLDER"] = os.path.join(BASE_DIR, "processed")
instance_path = os.path.join(BASE_DIR, "instance")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(instance_path, 'app.db')}"

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["PROCESSED_FOLDER"], exist_ok=True)
os.makedirs(instance_path, exist_ok=True)

db.init_app(app)

# ======================================================
# Login Manager
# ======================================================
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ======================================================
# Forms
# ======================================================
class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    submit = SubmitField("Register")

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")

# ======================================================
# Helpers
# ======================================================
def allowed(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]

def admin_required(func):
    """Decorator to restrict access to admin users."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return func(*args, **kwargs)
    return wrapper

# ======================================================
# Routes
# ======================================================
@app.route("/")
def home():
    jobs = []
    if current_user.is_authenticated:
        jobs = ImageJob.query.filter_by(user_id=current_user.id).order_by(ImageJob.created_at.desc()).all()
    return render_template("upload.html", jobs=jobs)

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash("Email already exists.", "warning")
            return redirect(url_for("register"))
        u = User(email=form.email.data)
        u.set_password(form.password.data)
        db.session.add(u)
        db.session.commit()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))
    return render_template("auth_register.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        u = User.query.filter_by(email=form.email.data).first()
        if u and u.check_password(form.password.data):
            login_user(u)
            return redirect(url_for("home"))
        flash("Invalid credentials.", "danger")
    return render_template("auth_login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

# ======================================================
# Image Upload and Processing
# ======================================================
@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("image")
    if not f or f.filename == "":
        flash("Please select an image.", "warning")
        return redirect(url_for("home"))
    if not allowed(f.filename):
        flash("Only PNG/JPG/JPEG images are allowed.", "danger")
        return redirect(url_for("home"))

    filename = secure_filename(f.filename)
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    f.save(save_path)

    job = ImageJob(user_id=current_user.id, original_path=save_path)
    db.session.add(job)
    db.session.commit()

    processed_name = f"{job.id}_{filename}"
    processed_path = os.path.join(app.config["PROCESSED_FOLDER"], processed_name)

    try:
        count = detect_defects(save_path, processed_path)
    except Exception as e:
        flash(f"Image processing failed: {e}", "danger")
        db.session.delete(job)
        db.session.commit()
        return redirect(url_for("home"))

    job.processed_path = processed_path
    job.defect_count = count
    db.session.commit()

    return redirect(url_for("results", job_id=job.id))

@app.route("/results/<int:job_id>")
@login_required
def results(job_id):
    job = ImageJob.query.get_or_404(job_id)
    if job.user_id != current_user.id and not current_user.is_admin:
        return "Forbidden", 403

    processed_filename = os.path.basename(job.processed_path)
    original_filename = os.path.basename(job.original_path)

    return render_template("results.html",
                           job=job,
                           processed_filename=processed_filename,
                           original_filename=original_filename)

@app.route("/processed/<path:filename>")
@login_required
def processed_file(filename):
    return send_from_directory(app.config["PROCESSED_FOLDER"], filename)

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# ======================================================
# Admin Panel
# ======================================================
@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    total_jobs = ImageJob.query.count()
    users = User.query.all()
    jobs = ImageJob.query.order_by(ImageJob.created_at.desc()).all()
    return render_template("admin_dashboard.html",
                           total_users=total_users,
                           total_jobs=total_jobs,
                           users=users,
                           jobs=jobs)

@app.route("/admin/delete_user/<int:user_id>")
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash("You cannot delete another admin!", "warning")
        return redirect(url_for("admin_dashboard"))
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete_job/<int:job_id>")
@login_required
@admin_required
def delete_job(job_id):
    job = ImageJob.query.get_or_404(job_id)
    db.session.delete(job)
    db.session.commit()
    flash("Job deleted successfully.", "success")
    return redirect(url_for("admin_dashboard"))

# ======================================================
# CLI Command
# ======================================================
@app.cli.command("init-db")
def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized successfully.")

# ======================================================
# RUN APP (Web + Desktop Compatible)
# ======================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    logging.getLogger("flaskwebgui").setLevel(logging.ERROR)

    # Initialize FlaskWebGUI
    ui = FlaskUI(
        app=app,
        server="flask",
        width=1200,
        height=800,
        fullscreen=False
    )

    ui.run()
