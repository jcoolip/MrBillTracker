import os
import sqlite3
from datetime import datetime
from ssl import get_default_verify_paths

from flask import Flask, redirect, render_template, request, url_for, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["DATABASE"] = "bill_tracker.db"
app.config["APP_NAME"] = "HOME ACCOUNT TERMINAL"


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
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount_paid REAL NOT NULL,
            confirmation_number TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
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
            FOREIGN KEY (vendor_id) REFERENCES vendors(id)
        )
        """)

    conn.commit()
    conn.close()

def init_vendors():
    conn = get_db_conn()

    vendors = [
        ("Beckley Water Company", "https://www.eonlinebill.com/bapp/beckley/indexl"),
        ("Appalachian Power", "https://www.appalachianpower.com/account/bills/"),
        ("Frontier Communications", "https://ssoparent.frontier.com/pages/login"),
        ("Mountaineer Gas", "https://www.doxo.com/bill-pay/mountaineergas"),
        ("Disney+", "https://www.disneyplus.com/commerce/billing"),
        ("Beckley Sanitary", "https://beckleywv.municipalonlinepayments.com/beckleywv")
    ]

    conn.executemany("""
        INSERT OR IGNORE INTO vendors (name, pmt_url)
        VALUES (?, ?)
    """, vendors)

    conn.commit()
    conn.close()

def init_uploads():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

init_db()
init_vendors()
init_uploads()

@app.route("/")
def index():
    conn = get_db_conn()

    vendors = conn.execute("""
        WITH vendor_balances AS (
            SELECT
                vendors.id,
                vendors.name,
                vendors.pmt_url,

                COALESCE(bill_totals.total_billed, 0)
                    - COALESCE(payment_totals.total_paid, 0)
                    AS total_owed,

                (
                    SELECT bills.due_date
                    FROM bills
                    WHERE bills.vendor_id = vendors.id
                    ORDER BY
                        bills.bill_date DESC,
                        bills.id DESC
                    LIMIT 1
                ) AS next_due_date

            FROM vendors

            LEFT JOIN (
                SELECT
                    vendor_id,
                    SUM(amount_due) AS total_billed
                FROM bills
                GROUP BY vendor_id
            ) AS bill_totals
                ON vendors.id = bill_totals.vendor_id

            LEFT JOIN (
                SELECT
                    vendor_id,
                    SUM(amount_paid) AS total_paid
                FROM payments
                GROUP BY vendor_id
            ) AS payment_totals
                ON vendors.id = payment_totals.vendor_id
        )

        SELECT *
        FROM vendor_balances

        ORDER BY
            CASE
                WHEN total_owed <= 0 THEN 1
                ELSE 0
            END,
            next_due_date,
            name
    """).fetchall()

    conn.close()

    formatted_vendors = []

    for vendor in vendors:
        vendor = dict(vendor)

        if vendor["total_owed"] <= 0:
            vendor["next_due_date"] = "---"

        elif vendor["next_due_date"]:
            vendor["next_due_date"] = datetime.strptime(
                vendor["next_due_date"],
                "%Y-%m-%d"
            ).strftime("%m/%d")

        else:
            vendor["next_due_date"] = "---"

        formatted_vendors.append(vendor)

    return render_template(
        "index.html",
        vendors=formatted_vendors,
    )

@app.route("/vendors/<int:vendor_id>")
def view_vendor(vendor_id):
    conn = get_db_conn()

    payments = conn.execute("""
        SELECT *
        FROM payments
        WHERE vendor_id = ?
        ORDER BY payment_date
        """, (vendor_id,)).fetchall()

    vendor = conn.execute("""
        SELECT id, name, pmt_url
        FROM vendors
        WHERE id = ?
    """, (vendor_id,)).fetchone()

    if vendor is None:
        conn.close()
        return "Vendor not found", 404

    balance = conn.execute("""
        SELECT
            COALESCE(bill_totals.total_billed, 0)
            - COALESCE(payment_totals.total_paid, 0)
            AS total_owed
        FROM vendors

        LEFT JOIN (
            SELECT
                vendor_id,
                SUM(amount_due) AS total_billed
            FROM bills
            WHERE vendor_id = ?
            GROUP BY vendor_id
        ) AS bill_totals
            ON vendors.id = bill_totals.vendor_id

        LEFT JOIN (
            SELECT
                vendor_id,
                SUM(amount_paid) AS total_paid
            FROM payments
            WHERE vendor_id = ?
            GROUP BY vendor_id
        ) AS payment_totals
            ON vendors.id = payment_totals.vendor_id

        WHERE vendors.id = ?
    """, (vendor_id, vendor_id, vendor_id)).fetchone()

    current_bill = conn.execute("""
        SELECT due_date
        FROM bills
        WHERE vendor_id = ?
        ORDER BY bill_date DESC, id DESC
        LIMIT 1
    """, (vendor_id,)).fetchone()

    last_payment = conn.execute("""
        SELECT payment_date, amount_paid
        FROM payments
        WHERE vendor_id = ?
        ORDER BY payment_date DESC, id DESC
        LIMIT 1
    """, (vendor_id,)).fetchone()

    bill_history = conn.execute("""
        SELECT *
        FROM bills
        WHERE vendor_id = ?
        ORDER BY bill_date DESC, id DESC
    """, (vendor_id,)).fetchall()

    payment_history = conn.execute("""
        SELECT *
        FROM payments
        WHERE vendor_id = ?
        ORDER BY payment_date DESC, id DESC
    """, (vendor_id,)).fetchall()

    conn.close()

    total_owed = balance["total_owed"]

    next_due_date = None

    if total_owed > 0 and current_bill:
        next_due_date = current_bill["due_date"]

    if next_due_date is not None:
        next_due_date = datetime.strptime(
            next_due_date,
            "%Y-%m-%d"
        ).strftime("%m/%d")

    return render_template(
        "vendor.html",
        payments=payments,
        vendor=vendor,
        total_owed=total_owed,
        next_due_date=next_due_date,
        last_payment=last_payment,
        bill_history=bill_history,
        payment_history=payment_history,
    )

@app.route("/vendors/<int:vendor_id>/payment")
def payment(vendor_id):
    conn = get_db_conn()

    vendor = conn.execute("""
        SELECT id, name, pmt_url
        FROM vendors
        WHERE id = ?
    """, (vendor_id,)).fetchone()

    conn.close()

    if vendor is None:
        return "Vendor not found", 404

    return render_template("pay.html", vendor=vendor)

@app.route("/vendors/<int:vendor_id>/payment", methods=["POST"])
def save_payment(vendor_id):
    conn = get_db_conn()

    conn.execute("""
        INSERT INTO payments (
            vendor_id,
            payment_date,
            amount_paid,
            notes,
            confirmation_number,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        vendor_id,
        request.form["payment_date"],
        request.form["amount_paid"],
        request.form.get("notes"),
        request.form.get("confirmation_number"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("view_vendor", vendor_id=vendor_id))

@app.route("/vendors/add")
def add_vendor():
    return render_template("add_vendor.html")

@app.route("/vendors/add", methods=["POST"])
def save_vendor():
    conn = get_db_conn()

    conn.execute("""
        INSERT INTO vendors (name, pmt_url)
        VALUES (?, ?)
    """, (
        request.form["name"],
        request.form.get("pmt_url"),
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("index"))

@app.route("/vendors/<int:vendor_id>/edit")
def edit_vendor(vendor_id):
    conn = get_db_conn()

    vendor = conn.execute("""
        SELECT *
        FROM vendors
        WHERE id = ?
        """,(vendor_id,)).fetchone()

    conn.close()

    if vendor is None:
        return "Vendor not found", 404

    return render_template("edit_vendor.html", vendor=vendor)

@app.route("/vendors/<int:vendor_id>/edit", methods=["POST"])
def confirm_edit_vendor(vendor_id):
    conn = get_db_conn()

    conn.execute("""
        UPDATE vendors
        SET
            name = ?,
            pmt_url = ?
        WHERE id = ?
        """, (
            request.form["name"],
            request.form["pmt_url"],
            vendor_id
        ))

    conn.commit()
    conn.close()

    return redirect(url_for("view_vendor", vendor_id=vendor_id))

@app.route("/add")
def add_bill():
    conn = get_db_conn()

    vendors = conn.execute("""
        SELECT * FROM vendors ORDER BY name
        """).fetchall()

    conn.close()

    selected_vendor = request.args.get("vendor_id", type=int)

    return render_template("add_bill.html", vendors=vendors, selected_vendor=selected_vendor)

@app.route("/add", methods=["POST"])
def preview_bill():
    image_path = None

    uploaded_file = request.files.get("bill_image")

    if uploaded_file and uploaded_file.filename != "":
        filename = secure_filename(uploaded_file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        uploaded_file.save(save_path)
        image_path = filename

    conn = get_db_conn()

    vendor_id = request.form["vendor_id"]
    vendor = conn.execute("""
        SELECT name
        FROM vendors
        WHERE id = ?
        """, (vendor_id,)).fetchone()

    conn.close()

    bill = {
        "vendor_id": vendor_id,
        "vendor_name": vendor["name"],
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


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
