from flask import Flask, render_template, request, redirect, session, url_for
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from flask import send_file
import io
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename




app = Flask(__name__)
app.secret_key = "smartcitysecret"
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ---------------- DATABASE ----------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    email TEXT UNIQUE,
                    password TEXT,
                    role TEXT)''')

    conn.execute('''CREATE TABLE IF NOT EXISTS complaints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    category TEXT,
                    area TEXT,
                    description TEXT,
                    status TEXT,
                    date TEXT)''')
    conn.commit()
    conn.close()

init_db()
# Create default admin automatically
conn = get_db()
conn.execute("INSERT OR IGNORE INTO users (name,email,password,role) VALUES (?,?,?,?)",
             ("Admin","admin@gmail.com","123","admin"))
conn.commit()
conn.close()




def add_image_column():
    conn = get_db()
    cols = [row["name"] for row in conn.execute("PRAGMA table_info(complaints)").fetchall()]
    if "image" not in cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN image TEXT")
        conn.commit()
    conn.close()

add_image_column()


# ---------------- HOME ----------------
@app.route("/")
def index():
    return render_template("index.html")

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        existing_user = conn.execute("SELECT * FROM users WHERE email=?",
                                     (email,)).fetchone()

        if existing_user:
            conn.close()
            return "Email already registered!"

        conn.execute("INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
                     (name,email,password,"citizen"))
        conn.commit()
        conn.close()
        return redirect("/login")

    return render_template("register.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=? AND password=?",
                            (email,password)).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id"]
            session["role"] = user["role"]

            if user["role"] == "admin":
                return redirect("/admin")
            else:
                return redirect("/dashboard")
    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- CITIZEN DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")
    return render_template("citizen_dashboard.html")

# ---------------- ADD COMPLAINT ----------------
@app.route("/add_complaint", methods=["GET","POST"])
def add_complaint():
    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":
        category = request.form["category"]
        area = request.form["area"]
        description = request.form["description"]
        date = datetime.now().strftime("%Y-%m-%d")

        # image upload
        file = request.files.get("image")
        filename = None

        if file and file.filename != "":
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        conn = get_db()
        conn.execute("""
            INSERT INTO complaints (user_id, category, area, description, status, date, image)
            VALUES (?,?,?,?,?,?,?)
        """, (
            session["user_id"],
            category,
            area,
            description,
            "Pending",
            date,
            filename
        ))
        conn.commit()
        conn.close()

        return redirect("/my_complaints")

    return render_template("complaint_add.html")


# ---------------- MY COMPLAINTS ----------------
@app.route("/my_complaints")
def my_complaints():
    conn = get_db()
    complaints = conn.execute("SELECT * FROM complaints WHERE user_id=?",
                              (session["user_id"],)).fetchall()
    conn.close()
    return render_template("my_complaints.html", complaints=complaints)

# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin")
def admin():
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")

    conn = get_db()

    complaints = conn.execute("""
        SELECT complaints.*, users.name 
        FROM complaints 
        JOIN users ON complaints.user_id = users.id
    """).fetchall()

    total = conn.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM complaints WHERE status='Pending'").fetchone()[0]
    progress = conn.execute("SELECT COUNT(*) FROM complaints WHERE status='In Progress'").fetchone()[0]
    completed = conn.execute("SELECT COUNT(*) FROM complaints WHERE status='Completed'").fetchone()[0]

    conn.close()

    return render_template("admin_dashboard.html",
                           complaints=complaints,
                           total=total,
                           pending=pending,
                           progress=progress,
                           completed=completed)


# ---------------- UPDATE STATUS ----------------
@app.route("/update_status/<int:id>", methods=["POST"])
def update_status(id):
    new_status = request.form.get("status")

    conn = get_db()
    conn.execute("UPDATE complaints SET status=? WHERE id=?",
                 (new_status, id))
    conn.commit()
    conn.close()

    return redirect("/admin")









#---------------------pdf----------------------------------------

@app.route("/export_pdf")
def export_pdf():
    # Admin only
    if "role" not in session or session["role"] != "admin":
        return redirect("/login")

    conn = get_db()
    complaints = conn.execute("""
        SELECT complaints.*, users.name
        FROM complaints
        JOIN users ON complaints.user_id = users.id
        ORDER BY complaints.id DESC
    """).fetchall()
    conn.close()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    elements = []
    elements.append(Paragraph("Smart City Complaint Report", styles["Heading1"]))
    elements.append(Spacer(1, 0.3 * inch))

    for c in complaints:
        # ✅ Correct keys from your DB
        line1 = f"User: {c['name']} | Date: {c['date']} | Status: {c['status']}"
        line2 = f"Category: {c['category']} | Area: {c['area']}"
        line3 = f"Description: {c['description']}"

        elements.append(Paragraph(line1, styles["Normal"]))
        elements.append(Paragraph(line2, styles["Normal"]))
        elements.append(Paragraph(line3, styles["Normal"]))
        elements.append(Spacer(1, 0.2 * inch))

    doc.build(elements)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="complaints_report.pdf")




if __name__ == "__main__":
    app.run(debug=True)
