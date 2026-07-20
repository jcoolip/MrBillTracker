import os
import sqlite3
from datetime import datetime, date, timedelta
from urllib.parse import urlencode

from flask import Flask, flash, redirect, render_template, request, url_for, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["DATABASE"] = "bill_tracker.db"
app.config["SECRET_KEY"] = "8u4j3oer0u843ipgrnk304igkperm"

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
            category_id INTEGER,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            pmt_url TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT,
            is_recurring INTEGER NOT NULL DEFAULT 0,
            recurring_amount REAL,
            recurring_due_day INTEGER,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_order INTEGER DEFAULT 100
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
        (2, "Beckley Water Company", "https://www.eonlinebill.com/bapp/beckley/indexl"),
        (2, "Appalachian Power", "https://www.appalachianpower.com/account/bills/"),
        (3, "Frontier Communications", "https://ssoparent.frontier.com/pages/login"),
        (2, "Mountaineer Gas", "https://www.doxo.com/bill-pay/mountaineergas"),
        (8, "Disney+", "https://www.disneyplus.com/commerce/billing"),
        (2, "Beckley Sanitary", "https://beckleywv.municipalonlinepayments.com/beckleywv"),
        (1, "Household", "https://www.google.com/finance"),
        (4, "AT&T", "https://www.att.com/my/#/login"),
        (5, "Geico", "https://www.geico.com/myaccount/"),
        (8, "Youtubetv", "https://www.youtube.com/paid_memberships")
    ]

    cats = [
        ("Housing", 10),
        ("Utilities", 20),
        ("Internet", 30),
        ("Mobile", 40),
        ("Insurance", 50),
        ("Credit Cards", 60),
        ("Loans", 70),
        ("Streaming", 80),
        ("Subscriptions", 90),
        ("Transportation", 100),
        ("Healthcare", 110),
        ("Shopping", 120),
        ("Entertainment", 130),
        ("Other", 999)
    ]

    conn.executemany("""
        INSERT OR IGNORE INTO categories (name, sort_order)
        VALUES (?, ?)
    """, cats)

    conn.executemany("""
        INSERT OR IGNORE INTO vendors (category_id, name, pmt_url)
        VALUES (?, ?, ?)
    """, vendors)

    conn.commit()
    conn.close()

def init_uploads():
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

def edit_db():
    conn = get_db_conn()

    conn.execute("""
        ALTER TABLE bills
        ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0;
    """)

    conn.close()

init_db()
init_vendors()
init_uploads()
# edit_db()

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route("/admin/manage-vendors")
def manage_vendors():
    conn = get_db_conn()

    vendors = conn.execute("""
        SELECT * FROM vendors
        ORDER BY name
    """).fetchall()

    conn.close()

    return render_template("manage_vendors.html", vendors=vendors)

@app.route("/admin/manage-categories")
def manage_categories():
    conn = get_db_conn()

    categories = conn.execute("""
        SELECT * FROM categories
        ORDER BY sort_order
    """).fetchall()

    conn.close()

    return render_template("manage_categories.html", categories=categories)

@app.route("/")
def index():
    conn = get_db_conn()

    vendors = conn.execute("""
        SELECT
            vendors.id,
            vendors.name,
            vendors.pmt_url,
            vendors.is_active,
            categories.id AS category_id,
            COALESCE(categories.name, 'Uncategorized') AS category_name,
            COALESCE(categories.sort_order, 999) AS category_sort,

            COALESCE(bill_totals.total_billed, 0)
                - COALESCE(payment_totals.total_paid, 0)
                AS total_owed,

            (
                SELECT bills.due_date
                FROM bills
                WHERE bills.vendor_id = vendors.id
                ORDER BY bills.bill_date DESC, bills.id DESC
                LIMIT 1
            ) AS next_due_date

        FROM vendors

        LEFT JOIN categories
            ON vendors.category_id = categories.id

        LEFT JOIN (
            SELECT vendor_id, SUM(amount_due) AS total_billed
            FROM bills
            GROUP BY vendor_id
        ) AS bill_totals
            ON vendors.id = bill_totals.vendor_id

        LEFT JOIN (
            SELECT vendor_id, SUM(amount_paid) AS total_paid
            FROM payments
            GROUP BY vendor_id
        ) AS payment_totals
            ON vendors.id = payment_totals.vendor_id

        WHERE vendors.is_active = 1

        ORDER BY
            category_sort,
            category_name,
            CASE WHEN total_owed <= 0 THEN 1 ELSE 0 END,
            next_due_date,
            vendors.name
    """).fetchall()

    conn.close()

    grouped_categories = {}

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

        category_name = vendor["category_name"]

        if category_name not in grouped_categories:
            grouped_categories[category_name] = {
                "name": category_name,
                "total_owed": 0,
                "vendors": [],
            }

        grouped_categories[category_name]["total_owed"] += vendor["total_owed"]
        grouped_categories[category_name]["vendors"].append(vendor)

    return render_template(
        "index.html",
        categories=grouped_categories.values()
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

    # bill_history = conn.execute("""
    #     SELECT *
    #     FROM bills
    #     WHERE vendor_id = ?
    #     ORDER BY bill_date DESC, id DESC
    # """, (vendor_id,)).fetchall()

    bill_rows = conn.execute("""
        SELECT *
        FROM bills
        WHERE vendor_id = ?
        ORDER BY created_at DESC, id DESC
    """, (vendor_id,)).fetchall()

    calendar_bill = conn.execute("""
        SELECT *
        FROM bills
        WHERE vendor_id = ?
        AND COALESCE(is_archived, 0) = 0
        ORDER BY
            CASE
                WHEN date(due_date) >= date('now') THEN 0
                ELSE 1
            END,
            CASE
                WHEN date(due_date) >= date('now')
                    THEN date(due_date)
            END ASC,
            CASE
                WHEN date(due_date) < date('now')
                    THEN date(due_date)
            END DESC
        LIMIT 1
    """, (vendor_id,)).fetchone()

    bill_history = []

    current_assigned = False

    for bill in bill_rows:
        bill_data = dict(bill)

        if bill_data["is_archived"]:
            bill_data["state"] = "archived"

        elif not current_assigned:
            bill_data["state"] = "current"
            current_assigned = True

        else:
            bill_data["state"] = "past"

        bill_data["vendor_name"] = vendor["name"]
        bill_data["pmt_url"] = vendor["pmt_url"]
        bill_data["calendar_url"] = google_calendar_url(bill_data)

        bill_history.append(bill_data)
        
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

    calendar_url = None

    if calendar_bill:
        calendar_bill_data = dict(calendar_bill)

        calendar_bill_data["vendor_name"] = vendor["name"]
        calendar_bill_data["pmt_url"] = vendor["pmt_url"]

        calendar_url = google_calendar_url(calendar_bill_data)

    return render_template(
        "vendor.html",
        payments=payments,
        vendor=vendor,
        total_owed=total_owed,
        next_due_date=next_due_date,
        last_payment=last_payment,
        bill_history=bill_history,
        payment_history=payment_history,
        calendar_url=calendar_url
    )

@app.route("/vendors/<int:vendor_id>/payment")
def payment(vendor_id):
    conn = get_db_conn()

    vendor = conn.execute("""
        SELECT id, name, pmt_url
        FROM vendors
        WHERE id = ?
    """, (vendor_id,)).fetchone()

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
    """, (
        vendor_id,
        vendor_id,
        vendor_id
    )).fetchone()

    conn.close()

    today = datetime.now().strftime("%Y-%m-%d")

    if vendor is None:
        return "Vendor not found", 404

    total_owed = balance["total_owed"] if balance else 0

    return render_template(
        "pay.html",
        vendor=vendor,
        total_owed=total_owed,
        today=today
    )

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

    flash("PAYMENT RECV'D", "success")
    return redirect(url_for("view_vendor", vendor_id=vendor_id))

@app.route("/vendors/add")
def add_vendor():

    conn = get_db_conn()

    categories = conn.execute("""
        SELECT *
        FROM categories
    """).fetchall()

    return render_template("add_vendor.html", categories=categories)

@app.route("/vendors/add", methods=["POST"])
def save_vendor():
    conn = get_db_conn()

    category_id = request.form.get("category_id")
    name = request.form["name"].strip()
    pmt_url = request.form.get("pmt_url")
    is_recurring = request.form.get("is_recurring", "0")
    recurring_amount = request.form.get("recurring_amount") or None
    recurring_due_day = request.form.get("recurring_due_day") or None

    try:
        conn.execute("""
            INSERT INTO vendors (
                category_id,
                name,
                pmt_url,
                updated_at,
                is_recurring,
                recurring_amount,
                recurring_due_day
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            category_id,
            name,
            pmt_url,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            is_recurring,
            recurring_amount,
            recurring_due_day
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        flash(f"VENDOR DUPLICATE :: {name}", "error")
        return redirect(url_for("add_vendor"))

    finally:
        conn.close()

    flash("VENDOR ADDITION SUCCESS", "success")
    return redirect(url_for("index"))

@app.route("/vendors/<int:vendor_id>/edit")
def edit_vendor(vendor_id):
    conn = get_db_conn()

    vendor = conn.execute("""
        SELECT *
        FROM vendors
        WHERE id = ?
        """,(vendor_id,)).fetchone()

    categories = conn.execute("""
        SELECT *
        FROM categories
        ORDER BY sort_order
        """).fetchall()

    conn.close()

    if vendor is None:
        return "Vendor not found", 404

    return render_template("edit_vendor.html", vendor=vendor, categories=categories)

@app.route("/vendors/<int:vendor_id>/edit", methods=["POST"])
def confirm_edit_vendor(vendor_id):
    conn = get_db_conn()

    category_id = request.form["category_id"]
    name = request.form["name"].strip()
    pmt_url = request.form["pmt_url"]
    is_recurring = request.form["is_recurring"]
    recurring_amount = request.form["recurring_amount"]
    recurring_due_day = request.form["recurring_due_day"]

    try:
        conn.execute("""
            UPDATE vendors
            SET
                category_id = ?,
                name = ?,
                pmt_url = ?,
                updated_at = ?,
                is_recurring = ?,
                recurring_amount = ?,
                recurring_due_day = ?
            WHERE id = ?
            """, (
                category_id,
                name,
                pmt_url,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                is_recurring,
                recurring_amount,
                recurring_due_day,
                vendor_id
            ))

        conn.commit()
    except sqlite3.IntegrityError:
        flash(f"VENDOR DUPLICATE :: {name}", "error")
        return redirect(url_for("edit_vendor", vendor_id=vendor_id))
    finally:
        conn.close()

    flash("VENDOR EDIT SUCCESS", "success")
    return redirect(url_for("edit_vendor", vendor_id=vendor_id))

@app.route("/category/add")
def add_category():

    conn = get_db_conn()

    categories = conn.execute("""
        SELECT *
        FROM categories
        """).fetchall()

    return render_template("add_category.html", categories=categories)

@app.route("/category/add", methods=["POST"])
def save_category():
    conn = get_db_conn()

    name = request.form["name"].strip()
    sort_order = request.form["sort_order"]

    try:
        conn.execute("""
            INSERT INTO categories (name, sort_order)
            VALUES (?, ?)
        """, (name,sort_order))

        conn.commit()
    except sqlite3.IntegrityError:
        flash(f"CATEGORY DUPLICATE :: {name}", "error")
        return redirect(url_for("add_category"))
    finally:
        conn.close()

    flash("CATEGORY ADDITION SUCCESS", "success")
    return redirect(url_for("index"))

@app.route("/category/<int:category_id>/edit")
def edit_category(category_id):
    conn = get_db_conn()

    category = conn.execute("""
        SELECT *
        FROM categories
        WHERE id = ?
        """, (category_id,)).fetchone()

    categories = conn.execute("""
        SELECT *
        FROM categories
        ORDER BY sort_order
        """).fetchall()

    conn.close()

    if category is None:
        return "Category not found", 404

    return render_template("edit_category.html", category=category, categories=categories)

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

    flash("BILL ACCEPTED", "success")
    return redirect(url_for("index"))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/bills/<int:bill_id>/archive", methods=["POST"])
def archive_bill(bill_id):
    conn = get_db_conn()

    bill = conn.execute("""
        SELECT vendor_id
        FROM bills
        WHERE id = ?
    """, (bill_id,)).fetchone()

    if bill is None:
        conn.close()
        return "Bill not found", 404

    conn.execute("""
        UPDATE bills
        SET is_archived = 1
        WHERE id = ?
    """, (bill_id,))

    conn.commit()
    conn.close()

    return redirect(
        url_for("view_vendor", vendor_id=bill["vendor_id"])
    )

def google_calendar_url(bill):
    due_date = date.fromisoformat(bill["due_date"])

    # Google all-day events use an exclusive end date.
    end_date = due_date + timedelta(days=1)

    params = {
        "action": "TEMPLATE",
        "text": f'Pay {bill["vendor_name"]}',
        "dates": (
            f'{due_date.strftime("%Y%m%d")}/'
            f'{end_date.strftime("%Y%m%d")}'
        ),
        "details": (
            f'Amount due: ${bill["amount_due"]:.2f}\n'
            f'Due date: {due_date.strftime("%m/%d/%Y")}\n'
            f'Payment URL: {bill["pmt_url"] or "Not provided"}'
        ),
    }

    return (
        "https://calendar.google.com/calendar/render?"
        + urlencode(params)
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
