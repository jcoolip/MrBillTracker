import os
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["DATABASE"] = "bill_tracker.db"
app.config["APP_NAME"] = "Mr. Bill Tracker"


def get_db_conn():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            amount_due REAL NOT NULL,
            due_date TEXT NOT NULL,
            bill_date TEXT,
            category TEXT,
            status TEXT DEFAULT 'unpaid',
            notes TEXT,
            image_path TEXT,
            created_at TEXT NOT NULL
        )
        """)

    conn.commit()
    conn.close()


init_db()

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/add")
def add_bill():
    return render_template("add_bill.html")


@app.route("/add", methods=["POST"])
def preview_bill():
    image_path = None

    uploaded_file = request.files.get("bill_image")

    if uploaded_file and uploaded_file.filename != "":
        filename = secure_filename(uploaded_file.filename)
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        uploaded_file.save(image_path)

    bill = {
        "vendor": request.form["vendor"],
        "amount_due": request.form["amount_due"],
        "due_date": request.form["due_date"],
        "bill_date": request.form.get("bill_date"),
        "category": request.form.get("category"),
        "status": request.form.get("status", "unpaid"),
        "notes": request.form.get("notes"),
        "image_path": image_path,
    }

    return render_template("preview_bill.html", bill=bill)


@app.route("/confirm", methods=["POST"])
def confirm_bill():
    conn = get_db_conn()

    conn.execute("""
        INSERT INTO bills (
            vendor,
            amount_due,
            due_date,
            bill_date,
            category,
            status,
            notes,
            image_path,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form["vendor"],
        request.form["amount_due"],
        request.form["due_date"],
        request.form.get("bill_date"),
        request.form.get("category"),
        request.form.get("status", "unpaid"),
        request.form.get("notes"),
        request.form.get("image_path"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
