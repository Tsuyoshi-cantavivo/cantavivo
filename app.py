import sqlite3
import requests
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
import os

# 環境変数読み込み
load_dotenv()

app = Flask(__name__)
app.secret_key = "your_secret_key"

# DB初期化
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
    conn.commit()
    conn.close()

init_db()

# HTMLメール送信関数（SendGrid）
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

# 各ルート定義
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/profile")
def profile():
    return render_template("profile.html")

@app.route("/lessons")
def lessons():
    return render_template("lessons.html")

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        message = request.form.get("message")

        if not name or not email or not message:
            flash("すべての項目を入力してください。")
            return redirect(url_for("contact"))

        # メール送信内容
        context = {
            "name": name,
            "email": email,
            "message": message
        }

        # 確認メール（お客様宛）
        send_mail(
            to=email,
            subject="【受付完了】お問い合わせありがとうございます",
            template_name="contact_email_user.html",
            context=context
        )

        # 管理者通知（管理者宛）
        send_mail(
            to="yuzublv24@gmail.com",
            subject="【通知】お問い合わせがありました",
            template_name="contact_email_admin.html",
            context=context
        )

        return render_template("contact_thanks.html")

    return render_template("contact.html")


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

        if not name or not age or not contact or not category or not course or not date or not time:
            flash("必須項目をすべて入力してください。")
            return redirect(url_for("lesson_trial"))

        return render_template(
            "lesson_trial_confirm.html",
            name=name,
            age=age,
            contact=contact,
            category=category,
            course=course,
            date=date,
            time=time,
            note=note
        )

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

    # DB保存
    conn = sqlite3.connect('lesson_applications.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO applications (name, age, contact, category, course, date, time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, age, contact, category, course, date, time_, note))
    conn.commit()
    conn.close()

    # メール送信（HTMLテンプレート使用）
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

    # お客様宛
    send_mail(
        to=contact,
        subject="【受付完了】体験レッスンのお申し込みありがとうございます",
        template_name="lesson_email_user.html",
        context=context
    )

    # 管理者宛
    send_mail(
        to="yuzublv24@gmail.com",
        subject="【通知】体験レッスン申し込みがありました",
        template_name="lesson_email_admin.html",
        context=context
    )

    return render_template("lesson_trial_thanks.html", name=name)

@app.route("/privacy")
def privacy():
    return render_template("privacy_policy.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
