import os
import json
import sqlite3
import requests
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret")

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

CONCERTS_FILE = "data/concerts.json"

# ===== DB初期化 =====
def init_db():
    conn = sqlite3.connect('lesson_applications.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            age TEXT,
            contact TEXT,
            category TEXT,
            course TEXT,
            date TEXT,
            time TEXT,
            note TEXT,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            message TEXT,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ===== ログイン認証 =====
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        entered_id = request.form.get("user_id")
        entered_password = request.form.get("password")
        if (entered_id == os.getenv("ADMIN_ID") and
            entered_password == os.getenv("ADMIN_PASSWORD")):
            session["logged_in"] = True
            return redirect(url_for("admin"))
        else:
            flash("IDまたはパスワードが正しくありません")
    return render_template("login.html")  # ← 修正後

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

# ===== ダッシュボード =====
@app.route("/admin")
def admin():
    return render_template("admin.html")

# ===== レッスン申し込み管理 =====
@app.route("/admin/lesson-applications")
def admin_lesson_applications():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    name = request.args.get("name", "")
    category = request.args.get("category", "")
    course = request.args.get("course", "")

    query = "SELECT * FROM applications WHERE 1=1"
    params = []

    if name:
        query += " AND name LIKE ?"
        params.append(f"%{name}%")
    if category:
        query += " AND category LIKE ?"
        params.append(f"%{category}%")
    if course:
        query += " AND course LIKE ?"
        params.append(f"%{course}%")

    query += " ORDER BY submitted_at DESC"

    conn = sqlite3.connect("lesson_applications.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    applications = cur.fetchall()
    conn.close()

    return render_template("lesson_applications.html", applications=applications)

# ===== お問い合わせ一覧 =====
@app.route("/admin/contact-applications")
def admin_contact_applications():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = sqlite3.connect("lesson_applications.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM contacts ORDER BY submitted_at DESC")
    contacts = cur.fetchall()
    conn.close()

    return render_template("contact_applications.html", contacts=contacts)

# ===== 出演情報管理 =====
@app.route("/admin/concerts")
def admin_concerts():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("admin_concert.html")

@app.route("/add_concert", methods=["POST"])
def add_concert():
    title = request.form.get("title")
    date = request.form.get("date")
    time_ = request.form.get("time")
    location = request.form.get("location")
    description = request.form.get("description")
    image = request.files.get("image")

    if not all([title, date, time_, location, description]):
        return jsonify({"status": "error", "message": "Missing fields"})

    image_url = ""
    if image:
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        image_url = f"/static/uploads/{filename}"

    new_concert = {
        "title": title,
        "date": date,
        "time": time_,
        "location": location,
        "description": description,
        "image": image_url
    }

    try:
        with open(CONCERTS_FILE, "r", encoding="utf-8") as f:
            concerts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        concerts = []

    concerts.insert(0, new_concert)

    with open(CONCERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(concerts, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success"})

@app.route("/delete_concert/<int:index>", methods=["POST"])
def delete_concert(index):
    try:
        with open(CONCERTS_FILE, "r", encoding="utf-8") as f:
            concerts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"status": "error", "message": "データが見つかりません"})

    if 0 <= index < len(concerts):
        deleted = concerts.pop(index)
        with open(CONCERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(concerts, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "success", "message": "削除しました", "deleted": deleted})
    else:
        return jsonify({"status": "error", "message": "無効なインデックスです"})

@app.route("/concerts")
def concerts():
    try:
        with open(CONCERTS_FILE, "r", encoding="utf-8") as f:
            concerts = json.load(f)
    except Exception:
        concerts = []
    return render_template("concerts.html", concerts=concerts)

# ===== お問い合わせ受付 =====
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        if not name or not email or not message:
            flash("すべての項目を入力してください。")
            return redirect(url_for("contact"))

        conn = sqlite3.connect("lesson_applications.db")
        c = conn.cursor()
        c.execute("INSERT INTO contacts (name, email, message) VALUES (?, ?, ?)", (name, email, message))
        conn.commit()
        conn.close()

        context = {"name": name, "email": email, "message": message}

        send_mail(to=email, subject="【受付完了】お問い合わせありがとうございます", template_name="contact_email_user.html", context=context)
        send_mail(to="info@cantavivo.com", subject="【通知】お問い合わせがありました", template_name="contact_email_admin.html", context=context)

        return render_template("contact_thanks.html")

    return render_template("contact.html")

# ===== メール送信関数 =====
def send_mail(to, subject, template_name, context):
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        print("SendGrid APIキーが設定されていません。")
        return

    html_body = render_template(template_name, **context)

    data = {
        "personalizations": [{
            "to": [{"email": to}],
            "subject": subject
        }],
        "from": {
            "email": "yuzublv24@gmail.com",
            "name": "Tsuyoshi Iida"
        },
        "content": [{
            "type": "text/html",
            "value": html_body
        }]
    }

    response = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json=data
    )

    if response.status_code != 202:
        print("SendGrid送信失敗:", response.status_code, response.text)
    else:
        print("✅ メール送信成功（SendGrid）")

# ===== レッスン申し込み状況の分析データ =====
@app.route("/admin/lesson-analytics-data")
def lesson_analytics_data():
    conn = sqlite3.connect("lesson_applications.db")
    df = pd.read_sql_query("SELECT * FROM applications", conn)
    conn.close()

    if df.empty:
        return jsonify({
            "months": {"labels": [], "counts": []},
            "ages": {"labels": [], "counts": []},
            "categories": {"labels": [], "counts": []},
            "courses": {"labels": [], "counts": []}
        })

    df["month"] = pd.to_datetime(df["submitted_at"]).dt.strftime("%Y-%m")
    monthly = df["month"].value_counts().sort_index()

    def to_group(age):
        try:
            a = int(age)
            if a < 10: return "0-9"
            elif a < 20: return "10代"
            elif a < 30: return "20代"
            elif a < 40: return "30代"
            elif a < 50: return "40代"
            else: return "50歳以上"
        except: return "不明"

    df["age_group"] = df["age"].apply(to_group)
    ages = df["age_group"].value_counts().sort_index()

    categories = df["category"].value_counts()
    courses = df["course"].value_counts()

    return jsonify({
        "months": {"labels": monthly.index.tolist(), "counts": monthly.values.tolist()},
        "ages": {"labels": ages.index.tolist(), "counts": ages.values.tolist()},
        "categories": {"labels": categories.index.tolist(), "counts": categories.values.tolist()},
        "courses": {"labels": courses.index.tolist(), "counts": courses.values.tolist()}
    })

# ===== 一般ページルート =====
@app.route("/")
def home():
    try:
        with open(CONCERTS_FILE, "r", encoding="utf-8") as f:
            concerts = json.load(f)
    except Exception:
        concerts = []
    return render_template("index.html", concerts=concerts)


@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/lessons")
def lessons():
    return render_template("lessons.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy_policy.html")

# 体験レッスン申込フォーム表示・確認画面へ
@app.route("/lesson-trial", methods=["GET", "POST"])
def lesson_trial():
    if request.method == "POST":
        name = request.form.get("name")
        age = request.form.get("age")
        contact = request.form.get("contact")
        category = request.form.get("category")
        course = request.form.get("course")
        date = request.form.get("date")
        time = request.form.get("time")
        note = request.form.get("note")

        # 必須チェック
        if not all([name, age, contact, category, course, date, time]):
            flash("すべての必須項目を入力してください。")
            return redirect(url_for("lesson_trial"))

        return render_template(
            "lesson_trial_confirm.html",
            name=name, age=age, contact=contact,
            category=category, course=course,
            date=date, time=time, note=note
        )

    return render_template("lesson_trial.html")


# 確認画面から送信されたらDB保存・メール送信・完了画面へ
@app.route("/lesson-trial/submit", methods=["POST"])
def lesson_trial_submit():
    name = request.form.get("name")
    age = request.form.get("age")
    contact = request.form.get("contact")
    category = request.form.get("category")
    course = request.form.get("course")
    date = request.form.get("date")
    time_ = request.form.get("time")
    note = request.form.get("note")

    # DBへ保存
    conn = sqlite3.connect("lesson_applications.db")
    c = conn.cursor()
    c.execute('''
        INSERT INTO applications (name, age, contact, category, course, date, time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, age, contact, category, course, date, time_, note))
    conn.commit()
    conn.close()

    # メール送信（送信関数が定義済みの場合）
    context = {
        "name": name,
        "age": age,
        "contact": contact,
        "category": category,
        "course": course,
        "date": date,
        "time": time_,
        "note": note
    }

    send_mail(
        to=contact,
        subject="【受付完了】体験レッスンのお申し込みありがとうございます",
        template_name="lesson_email_user.html",
        context=context
    )

    send_mail(
        to="info@cantavivo.com",
        subject="【通知】体験レッスン申し込みがありました",
        template_name="lesson_email_admin.html",
        context=context
    )

    return render_template("lesson_trial_thanks.html", name=name)


@app.route('/sitemap.xml')
def sitemap():
    return app.send_static_file('sitemap.xml')

@app.route("/robots.txt")
def robots_txt():
    return (
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /login\n"
        "Disallow: /logout\n"
        "Sitemap: https://cantavivo.com/sitemap.xml\n",
        200,
        {"Content-Type": "text/plain"}
    )


# ===== サーバー起動 =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
