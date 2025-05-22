import os
import json
import requests
import pandas as pd
import psycopg2
from datetime import datetime
from sqlalchemy import create_engine
from psycopg2.extras import RealDictCursor
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

# ===== DB接続関数 =====
def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"), cursor_factory=RealDictCursor)

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
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("login"))

# ===== 管理画面 =====
@app.route("/admin")
def admin():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 総アクセス数
        cur.execute("SELECT COUNT(*) FROM access_logs")
        views = cur.fetchone()["count"]

        # 一意のIPによる訪問数
        cur.execute("SELECT COUNT(DISTINCT ip_address) FROM access_logs")
        visits = cur.fetchone()["count"]

        # 新規ユーザー（過去30日以内に申込）
        cur.execute("""
            SELECT COUNT(*) FROM applications
            WHERE submitted_at >= CURRENT_DATE - INTERVAL '30 days'
        """)
        new_users = cur.fetchone()["count"]

        # 将来用 placeholder
        active_users = 0

    except Exception as e:
        print("📛 統計取得エラー:", e)
        views = visits = new_users = active_users = 0

    finally:
        cur.close()
        conn.close()

    stats = {
        "views": views,
        "visits": visits,
        "new_users": new_users,
        "active_users": active_users
    }

    return render_template("admin.html", stats=stats)




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
        query += " AND name ILIKE %s"
        params.append(f"%{name}%")
    if category:
        query += " AND category ILIKE %s"
        params.append(f"%{category}%")
    if course:
        query += " AND course ILIKE %s"
        params.append(f"%{course}%")

    query += " ORDER BY submitted_at DESC"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(query, params)
    applications = cur.fetchall()
    conn.close()

    return render_template("lesson_applications.html", applications=applications)

@app.route("/admin/contact-applications")
def admin_contact_applications():
    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM contacts ORDER BY submitted_at DESC")
    contacts = cur.fetchall()
    conn.close()

    return render_template("contact_applications.html", contacts=contacts)

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

    # ✅ 画像が選ばれていない場合はロゴを使用
    if image and image.filename:
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        image_url = f"/static/uploads/{filename}"
    else:
        image_url = "/static/sitelogo.PNG"

    new_concert = {
        "id": int(datetime.now().timestamp()),  # ← ユニークID
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

@app.template_filter('jst')
def format_jst(value):
    import pytz
    from datetime import timezone
    try:
        jst = pytz.timezone('Asia/Tokyo')
        utc_dt = value.replace(tzinfo=timezone.utc)
        jst_dt = utc_dt.astimezone(jst)
        return jst_dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return value


# ===== 出演情報削除・表示 =====
@app.route("/delete_concert/<int:concert_id>", methods=["POST"])
def delete_concert(concert_id):
    try:
        with open(CONCERTS_FILE, "r", encoding="utf-8") as f:
            concerts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"status": "error", "message": "データが見つかりません"})

    # id を元に削除対象を探す
    new_concerts = [c for c in concerts if c.get("id") != concert_id]

    if len(new_concerts) == len(concerts):
        return jsonify({"status": "error", "message": "該当するIDが見つかりません"})

    # JSONを上書き
    with open(CONCERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_concerts, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success", "message": "削除しました"})


@app.route("/concerts")
def concerts():
    try:
        with open(CONCERTS_FILE, "r", encoding="utf-8") as f:
            concerts = json.load(f)
    except Exception:
        concerts = []
    return render_template("concerts.html", concerts=concerts)

# ===== お問い合わせフォーム =====
@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        if not name or not email or not message:
            flash("すべての項目を入力してください。")
            return redirect(url_for("contact"))

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO contacts (name, email, message) VALUES (%s, %s, %s)", (name, email, message))
        conn.commit()
        conn.close()

        context = {"name": name, "email": email, "message": message}
        send_mail(to=email, subject="【受付完了】お問い合わせありがとうございます", template_name="contact_email_user.html", context=context)
        send_mail(to="info@cantavivo.com", subject="【通知】お問い合わせがありました", template_name="contact_email_admin.html", context=context)

        return render_template("contact_thanks.html")

    return render_template("contact.html")

# ===== 体験レッスン申込 =====
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

        if not all([name, age, contact, category, course, date, time]):
            flash("すべての必須項目を入力してください。")
            return redirect(url_for("lesson_trial"))

        return render_template("lesson_trial_confirm.html", name=name, age=age, contact=contact, category=category, course=course, date=date, time=time, note=note)

    return render_template("lesson_trial.html")

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

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO applications (name, age, contact, category, course, date, time, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (name, age, contact, category, course, date, time_, note))
    conn.commit()
    conn.close()

    context = {
        "name": name, "age": age, "contact": contact, "category": category,
        "course": course, "date": date, "time": time_, "note": note
    }
    send_mail(to=contact, subject="【受付完了】体験レッスンのお申し込みありがとうございます", template_name="lesson_email_user.html", context=context)
    send_mail(to="info@cantavivo.com", subject="【通知】体験レッスン申し込みがありました", template_name="lesson_email_admin.html", context=context)

    return render_template("lesson_trial_thanks.html", name=name)

# ===== 分析API =====
@app.route("/admin/lesson-analytics-data")
def lesson_analytics_data():
    db_url = os.getenv("DATABASE_URL")
    engine = create_engine(db_url)

    df = pd.read_sql("SELECT * FROM applications", engine)

    print("[DEBUG] Raw Data:")
    print(df.head())

    try:
        df["submitted_at"] = pd.to_datetime(df["submitted_at"], errors="coerce")
    except Exception as e:
        print("[ERROR] 日付変換に失敗:", e)
        df["submitted_at"] = pd.NaT

    df = df[df["submitted_at"].notna()]

    print("[DEBUG] Filtered Data:")
    print(df[["submitted_at", "age", "category", "course"]])

    if df.empty:
        return jsonify({
            "months": {"labels": [], "counts": []},
            "ages": {"labels": [], "counts": []},
            "categories": {"labels": [], "counts": []},
            "courses": {"labels": [], "counts": []}
        })

    df["month"] = df["submitted_at"].dt.strftime("%Y-%m")

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
        except:
            return "不明"

    df["age_group"] = df["age"].apply(to_group)
    ages = df["age_group"].value_counts().sort_index()
    categories = df["category"].fillna("未設定").value_counts()
    courses = df["course"].fillna("未設定").value_counts()

    result = {
        "months": {"labels": monthly.index.tolist(), "counts": monthly.values.tolist()},
        "ages": {"labels": ages.index.tolist(), "counts": ages.values.tolist()},
        "categories": {"labels": categories.index.tolist(), "counts": categories.values.tolist()},
        "courses": {"labels": courses.index.tolist(), "counts": courses.values.tolist()}
    }

    print("[DEBUG] Final JSON Response:")
    print(result)

    return jsonify(result)


@app.route("/admin/access-analytics-data")
def access_analytics_data():
    db_url = os.getenv("DATABASE_URL")
    engine = create_engine(db_url)

    query = """
        SELECT 
            EXTRACT(HOUR FROM accessed_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Tokyo') AS hour
        FROM access_logs
    """
    df = pd.read_sql(query, engine)

    if df.empty:
        return jsonify({
            "labels": [],
            "counts": []
        })

    df["hour"] = df["hour"].astype(int)
    hourly = df["hour"].value_counts().sort_index()

    result = {
        "labels": [f"{h}時" for h in hourly.index.tolist()],
        "counts": hourly.values.tolist()
    }

    print("[DEBUG] Access Hourly Data:")
    print(result)

    return jsonify(result)

# ===== 公開ページ =====
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

@app.route("/sitemap.xml")
def sitemap():
    return app.send_static_file("sitemap.xml")

@app.route("/robots.txt")
def robots_txt():
    return ("User-agent: *\nDisallow: /admin/\nDisallow: /login\nDisallow: /logout\nSitemap: https://cantavivo.com/sitemap.xml\n", 200, {"Content-Type": "text/plain"})

@app.before_request
def log_access():
    if request.endpoint and not request.endpoint.startswith("static"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO access_logs (ip_address, path, user_agent)
            VALUES (%s, %s, %s)
        """, (request.remote_addr, request.path, request.headers.get('User-Agent')))
        conn.commit()
        cur.close()
        conn.close()

@app.route("/api/concerts")
def api_concerts():
    with open(CONCERTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)

@app.route("/update_concert/<int:concert_id>", methods=["POST"])
def update_concert(concert_id):
    title = request.form.get("title")
    date = request.form.get("date")
    time_ = request.form.get("time")
    location = request.form.get("location")
    description = request.form.get("description")
    image = request.files.get("image")

    if not all([title, date, time_, location, description]):
        return jsonify({"status": "error", "message": "Missing fields"})

    try:
        with open(CONCERTS_FILE, "r", encoding="utf-8") as f:
            concerts = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return jsonify({"status": "error", "message": "データ読み込み失敗"})

    found = False
    for i, concert in enumerate(concerts):
        if concert.get("id") == concert_id:
            # 画像を更新する場合
            image_url = concert.get("image", "")
            if image:
                filename = secure_filename(image.filename)
                image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                image_url = f"/static/uploads/{filename}"

            concerts[i] = {
                "id": concert_id,
                "title": title,
                "date": date,
                "time": time_,
                "location": location,
                "description": description,
                "image": image_url
            }
            found = True
            break

    if not found:
        return jsonify({"status": "error", "message": "IDが見つかりません"})

    with open(CONCERTS_FILE, "w", encoding="utf-8") as f:
        json.dump(concerts, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success"})


# ===== 起動設定 =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)