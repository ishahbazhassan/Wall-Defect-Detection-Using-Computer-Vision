from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize database object
db = SQLAlchemy()

# -----------------------------
# USER MODEL
# -----------------------------
class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # ✅ Added field
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password):
        """Hash and store password"""
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        """Verify password"""
        return check_password_hash(self.password_hash, raw_password)

# -----------------------------
# IMAGE JOB MODEL
# -----------------------------
class ImageJob(db.Model):
    __tablename__ = "image_job"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    original_path = db.Column(db.String(512), nullable=False)
    processed_path = db.Column(db.String(512))
    defect_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
