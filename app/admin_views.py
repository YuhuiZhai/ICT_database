from flask import redirect, url_for, session, request, flash
from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.contrib.sqla.filters import FilterEqual
from .models import VehicleRequestForm, User  


from . import db
from .models import VehicleRequestForm


class SecureModelView(ModelView):
    can_export = True
    export_types = ["csv"]
    list_template = "admin_filter_csv.html"  
    
    column_display_pk = True
    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = True
    details_template = "form_readonly.html"

    column_filters = [
        "name",
        "dep_date",
        "ret_date",
        "project",
        "purpose",
        FilterEqual(
            VehicleRequestForm.vehicle,
            "Vehicle",
            options=[
                ("2022 RAM", "2022 RAM"),
                ("2012 F250", "2012 F250"),
                ("2016 AWD Equinox", "2016 AWD Equinox"),
            ],
        ),
        FilterEqual(
            VehicleRequestForm.status,
            "Status",
            options=[("submitted", "submitted"), ("draft", "draft")],
        ),
    ]

    column_labels = {
        "dep_date": "Departure Date",
        "ret_date": "Return Date",
        "start_mileage": "Start Mileage",
        "end_mileage": "End Mileage",
        "submitted_time": "Submitted Time",
        "admin_time": "Administrator Comment",
    }

    column_default_sort = ("submitted_time", True)  # True = descending
    page_size = 10

    def _truncate(view, context, model, name):
        value = getattr(model, name)
        if value and len(value) > 40:
            return value[:40] + "..."
        return value

    def _format_date(view, context, model, name):
        value = getattr(model, name)
        if not value:
            return ""
        return value.strftime("%m-%d-%Y")

    def _format_commas(view, context, model, name):
        value = getattr(model, name)
        if value is None or value == "":
            return ""
        try:
            num = int(value)
            return f"{num:,}"
        except (ValueError, TypeError):
            try:
                num = float(value)
                return f"{num:,.0f}"
            except (ValueError, TypeError):
                return value

    column_formatters = {
        "purpose": _truncate,
        "comments": _truncate,
        "project": _truncate,
        "dep_date": _format_date,
        "ret_date": _format_date,
        "start_mileage": _format_commas,
        "end_mileage": _format_commas,
    }

    def is_accessible(self):
        return session.get("logged_in")

    def inaccessible_callback(self, name, **kwargs):
        # IMPORTANT: admin blueprint endpoint
        return redirect(url_for("auth.admin_login"))


class SecureBaseView(BaseView):
    def is_accessible(self):
        return session.get("logged_in")

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("auth.admin_login"))


class SecureAdminIndexView(AdminIndexView):
    @expose("/")
    def index(self):
        if not session.get("logged_in"):
            return redirect(url_for("auth.admin_login"))
        return redirect(url_for("vehiclerequestform.index_view"))


class DownloadView(BaseView):
    @expose("/")
    def index(self):
        # IMPORTANT: download route is in the user blueprint
        return redirect(url_for("user.download_excel"))


class AdminLogoutView(SecureBaseView):
    @expose("/")
    def index(self):
        session.clear()
        return redirect(url_for("auth.admin_login"))


def init_admin(app):
    admin = Admin(
        app,
        name="Vehicle Usage Administration",
        index_view=SecureAdminIndexView(),
        template_mode="bootstrap3",
    )

    # Remove default Home entry (same as your original intent)
    admin._menu = admin._menu[1:]

    admin.add_view(SecureModelView(VehicleRequestForm, db.session, name="📄 View Form"))
    admin.add_view(DownloadView(name="📊 Download Excel", endpoint="download"))
    admin.add_view(AdminLogoutView(name="🚪 Logout", endpoint="admin_logout"))
    admin.add_view(ClearDatabaseView(name="Clear Database", endpoint="clear_db"))
    
class ClearDatabaseView(SecureBaseView):
    @expose("/", methods=["GET", "POST"])
    def index(self):
        if request.method == "POST":
            c1 = (request.form.get("confirm1") or "").strip().lower()
            c2 = (request.form.get("confirm2") or "").strip().lower()

            if c1 != "clear" or c2 != "clear":
                flash('Not cleared. Please type "clear" in BOTH boxes.', "error")
                return self.render("admin_clear_db.html")

            # ✅ Decide what "clear all data" means:
            # Usually you want to clear application data but keep admin accounts.
            try:
                db.session.query(VehicleRequestForm).delete()
                db.session.query(User).delete()
                # DO NOT delete AdminAccount unless you explicitly want to lock yourself out
                db.session.commit()
                flash("Database cleared successfully.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Clear failed: {e}", "error")

            return redirect(url_for("vehiclerequestform.index_view"))

        return self.render("admin_clear_db.html")
    