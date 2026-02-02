from flask_login import UserMixin
from . import db


class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, index=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_confirmed = db.Column(db.Boolean, default=False, nullable=False)


class VehicleRequestForm(db.Model):
    __tablename__ = "vehicle_request_form"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    name = db.Column(db.String)
    phone = db.Column(db.String)
    email = db.Column(db.String, index=True)

    vehicle = db.Column(db.String, index=True)
    dep_date = db.Column(db.Date)
    ret_date = db.Column(db.Date)

    start_mileage = db.Column(db.String)
    end_mileage = db.Column(db.String)

    destination = db.Column(db.String)
    purpose = db.Column(db.String)
    project = db.Column(db.String)

    comments = db.Column(db.String)
    submitted_time = db.Column(db.String)

    admin_comment = db.Column(db.String)
    status = db.Column(db.String, default="draft", index=True)


class AdminAccount(db.Model):
    __tablename__ = "admin_account"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
