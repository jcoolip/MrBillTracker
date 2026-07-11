import os
import sqlite3
from datetime import datetime

from flask import Flask, redirect, render_template, request, url_for, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["DATABASE"] = "bill_tracker.db"
app.config["APP_NAME"] = "Mr. Bill Tracker"


def get_db_conn():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_conn()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            pmt_url TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER NOT NULL,
            amount_due REAL NOT NULL,
            due_date TEXT NOT NULL,
            bill_date TEXT,
            notes TEXT,
            image_path TEXT,
            created_at TEXT NOT NULL,
            date_paid TEXT,
            amount_paid REAL,
            confirmation_number TEXT,
            confirmation_image_path TEXT,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
        )
        """)

    conn.commit()
    conn.close()

def init_vendors():
    conn = get_db_conn()

    vendors = [
        ("Beckley Water Company", "https://www.eonlinebill.com/bapp/beckley/indexl"),
        ("Appalachian Power", "https://www.appalachianpower.com/account/bills/")
    ]

    conn.executemany("""
        INSERT OR IGNORE INTO vendors (name, pmt_url)
        VALUES (?, ?)
    """, vendors)

    conn.commit()
    conn.close()


init_db()
init_vendors()

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


@app.route("/")
def index():
    conn = get_db_conn()

    vendors = conn.execute("""
        SELECT
            vendors.id,
            vendors.name,
            vendors.pmt_url,
            SUM(
                CASE
                    WHEN bills.date_paid IS NULL
                    THEN bills.amount_due
                    ELSE 0
                END
            ) AS total_owed
        FROM vendors
        LEFT JOIN bills
            ON vendors.id = bills.vendor_id
        GROUP BY vendors.id
        """
    ).fetchall()

    conn.close()

    # formatted_bills = []

    # for bill in bills:
    #     bill = dict(bill)
    #     bill["due_date"] = datetime.strptime(
    #         bill["due_date"], "%Y-%m-%d"
    #     ).strftime("%m/%d")
    #     formatted_bills.append(bill)

    return render_template("index.html", vendors=vendors)

@app.route("/vendors/<int:vendor_id>")
def view_vendor(vendor_id):
    conn = get_db_conn()

    vendor = conn.execute("""
        SELECT
            bills.*,
            vendors.name AS vendor_name,
            vendors.pmt_url
        FROM bills
        JOIN vendors
            ON bills.vendor_id = vendors.id
        WHERE vendors.id = ?
        ORDER BY due_date
        """,
        (vendor_id,)).fetchall()

    conn.close()

    return render_template("vendor.html", vendor=vendor)

@app.route("/add")
def add_bill():
    conn = get_db_conn()

    vendors = conn.execute("""
        SELECT * FROM vendors ORDER BY name
        """).fetchall()

    conn.close()

    return render_template("add_bill.html", vendors=vendors)

@app.route("/add", methods=["POST"])
def preview_bill():
    image_path = None

    uploaded_file = request.files.get("bill_image")

    if uploaded_file and uploaded_file.filename != "":
        filename = secure_filename(uploaded_file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        uploaded_file.save(save_path)
        image_path = filename

    bill = {
        "vendor_id": request.form["vendor_id"],
        "amount_due": request.form["amount_due"],
        "due_date": request.form["due_date"],
        "bill_date": request.form.get("bill_date"),
        "notes": request.form.get("notes"),
        "image_path": image_path,
    }

    return render_template("preview_bill.html", bill=bill)

@app.route("/confirm", methods=["POST"])
def confirm_bill():
    conn = get_db_conn()

    conn.execute("""
        INSERT INTO bills (
            vendor_id,
            amount_due,
            due_date,
            bill_date,
            notes,
            image_path,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form["vendor_id"],
        request.form["amount_due"],
        request.form["due_date"],
        request.form.get("bill_date"),
        request.form.get("notes"),
        request.form.get("image_path"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("index"))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/payment/<int:bill_id>")
def payment(bill_id):
    conn = get_db_conn()

    bill = conn.execute("""
        SELECT *
        FROM bills
        WHERE id = ?
    """, (bill_id,)).fetchone()

    conn.close()

    return render_template("pay.html", bill=bill)

@app.route("/payment/<int:bill_id>", methods=["POST"])
def save_payment(bill_id):
    confirmation_image_path = None

    uploaded_file = request.files.get("confirm_image")

    if uploaded_file and uploaded_file.filename != "":
        filename = secure_filename(uploaded_file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        uploaded_file.save(save_path)
        confirmation_image_path = filename

    conn = get_db_conn()

    conn.execute("""
        UPDATE bills
        SET
            date_paid = ?,
            amount_paid = ?,
            confirmation_number = ?,
            confirmation_image_path = ?
        WHERE id = ?
    """, (
        request.form["pmt_date"],
        request.form["pmt_amt"],
        request.form.get("confirm_num"),
        confirmation_image_path,
        bill_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("index"))



if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
