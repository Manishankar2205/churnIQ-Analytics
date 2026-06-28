from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify
import pandas as pd
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import secrets
from datetime import datetime, timedelta
import json
from io import BytesIO

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = 'churniq_secret_key_2026'

UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'csv'}

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  email TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reset_tokens
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT NOT NULL,
                  token TEXT NOT NULL,
                  expiry DATETIME NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS uploads
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT NOT NULL,
                  filename TEXT NOT NULL,
                  upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                  total_rows INTEGER)''')
    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def predict_churn(df):
    if 'Churn' in df.columns:
        return df['Churn'].apply(lambda x: 1 if str(x).lower() in ['yes', '1', 'true'] else 0).values
    predictions = []
    for _, row in df.iterrows():
        score = 0
        contract = str(row.get('Contract', '')).lower()
        if 'month' in contract: score += 0.4
        try:
            tenure_col = 'tenure' if 'tenure' in row else 'Tenure' if 'Tenure' in row else None
            if tenure_col:
                tenure = float(row.get(tenure_col, 0))
                if tenure < 12: score += 0.3
        except: pass
        try:
            charge_col = 'MonthlyCharges' if 'MonthlyCharges' in row else 'Monthly Charges' if 'Monthly Charges' in row else None
            if charge_col:
                monthly = float(row.get(charge_col, 0))
                if monthly > 70: score += 0.3
        except: pass
        tech_col = 'TechSupport' if 'TechSupport' in row else 'Tech Support' if 'Tech Support' in row else None
        if tech_col:
            tech_support = str(row.get(tech_col, '')).lower()
            if tech_support == 'no': score += 0.2
        predictions.append(1 if score > 0.5 else 0)
    return predictions

@app.route('/')
def home():
    if 'logged_in' in session: return redirect(url_for('upload'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password!= confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('INSERT INTO users (username, email, password) VALUES (?,?,?)',
                     (username, email, hashed_password))
            conn.commit()
            conn.close()
            flash('Registration successful! Please login', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or Email already exists', 'error')
            return redirect(url_for('register'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email =?', (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[3], password):
            session['logged_in'] = True
            session['username'] = user[1]
            session['email'] = user[2]
            return redirect(url_for('upload'))
        else:
            flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email =?', (email,))
        user = c.fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expiry = datetime.now() + timedelta(hours=1)
            c.execute('INSERT INTO reset_tokens (email, token, expiry) VALUES (?,?,?)',
                     (email, token, expiry))
            conn.commit()
            flash(f'Reset link: http://localhost:5000/reset_password/{token}', 'success')
        else: flash('Email not found', 'error')
        conn.close()
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT email, expiry FROM reset_tokens WHERE token =?', (token,))
    result = c.fetchone()
    if not result or datetime.now() > datetime.fromisoformat(result[1]):
        flash('Invalid or expired token', 'error')
        conn.close()
        return redirect(url_for('login'))
    email = result[0]
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password!= confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('reset_password.html', token=token)
        hashed_password = generate_password_hash(password)
        c.execute('UPDATE users SET password =? WHERE email =?', (hashed_password, email))
        c.execute('DELETE FROM reset_tokens WHERE token =?', (token,))
        conn.commit()
        conn.close()
        flash('Password reset successful! Please login', 'success')
        return redirect(url_for('login'))
    conn.close()
    return render_template('reset_password.html', token=token)

@app.route('/profile')
def profile():
    if 'logged_in' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT username, email FROM users WHERE email =?', (session['email'],))
    user = c.fetchone()
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/history')
def history():
    if 'logged_in' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT filename, upload_date, total_rows FROM uploads WHERE email =? ORDER BY upload_date DESC', (session['email'],))
    uploads = c.fetchall()
    conn.close()
    return render_template('history.html', uploads=uploads)

@app.route('/customer/<customer_id>')
def customer_detail(customer_id):
    if 'logged_in' not in session or 'uploaded_file' not in session:
        return redirect(url_for('upload'))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['uploaded_file'])
    df = pd.read_csv(filepath)
    customer = df[df['customerID'] == customer_id]
    if customer.empty:
        flash('Customer not found', 'error')
        return redirect(url_for('dashboard'))
    customer = customer.iloc[0]
    prediction = predict_churn(pd.DataFrame([customer]))[0]
    probability = 85 if prediction == 1 else 15
    return render_template('customer_detail.html', customer=customer.to_dict(), probability=probability)

@app.route('/download_report')
def download_report():
    if 'logged_in' not in session or 'uploaded_file' not in session:
        flash('Please upload a file first', 'error')
        return redirect(url_for('upload'))
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['uploaded_file'])
    df = pd.read_csv(filepath)
    df['Churn_Prediction'] = predict_churn(df)
    df['Churn_Probability'] = df['Churn_Prediction'].apply(lambda x: 0.85 if x == 1 else 0.15)
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'churn_predictions.csv')
    df.to_csv(output_path, index=False)
    return send_file(output_path, as_attachment=True)

@app.route('/download_excel')
def download_excel():
    if 'logged_in' not in session or 'uploaded_file' not in session:
        flash('Please upload a file first', 'error')
        return redirect(url_for('upload'))
    try:
        import openpyxl
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['uploaded_file'])
        df = pd.read_csv(filepath)
        df['Churn_Prediction'] = predict_churn(df)
        df['Churn_Probability'] = df['Churn_Prediction'].apply(lambda x: 0.85 if x == 1 else 0.15)
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'churn_report.xlsx')
        df.to_excel(output_path, index=False, engine='openpyxl')
        return send_file(output_path, as_attachment=True)
    except ImportError:
        flash('Excel feature needs openpyxl. Run: pip install openpyxl', 'error')
        return redirect(url_for('dashboard'))

@app.route('/download_pdf')
def download_pdf():
    if 'logged_in' not in session or 'uploaded_file' not in session:
        flash('Please upload a file first', 'error')
        return redirect(url_for('upload'))
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['uploaded_file'])
        df = pd.read_csv(filepath)
        total = len(df)
        churn_predictions = predict_churn(df)
        churn_count = int(sum(churn_predictions))
        churn_rate = round((churn_count/total)*100, 1) if total > 0 else 0
        charge_col = 'MonthlyCharges' if 'MonthlyCharges' in df.columns else 'Monthly Charges' if 'Monthly Charges' in df.columns else None
        avg_monthly = 0
        if charge_col:
            df[charge_col] = pd.to_numeric(df[charge_col], errors='coerce').fillna(0)
            avg_monthly = round(df[charge_col].mean(), 2)
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        p.setFont("Helvetica-Bold", 24)
        p.drawString(50, height - 50, "ChurnIQ Analytics Report")
        p.setFont("Helvetica", 12)
        p.drawString(50, height - 80, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        p.drawString(50, height - 100, f"User: {session['username']}")
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 140, "Key Metrics:")
        p.setFont("Helvetica", 12)
        p.drawString(70, height - 170, f"Total Customers: {total}")
        p.drawString(70, height - 190, f"Predicted Churn Count: {churn_count}")
        p.drawString(70, height - 210, f"Churn Rate: {churn_rate}%")
        p.drawString(70, height - 230, f"Avg Monthly Charges: ${avg_monthly}")
        p.showPage()
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='churn_report.pdf', mimetype='application/pdf')
    except ImportError:
        flash('PDF feature needs reportlab. Run: pip install reportlab', 'error')
        return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'logged_in' not in session: return redirect(url_for('login'))

    contract_filter = request.args.get('contract', 'all')

    metrics = {'churn_count': 0, 'total_customers': 0, 'churn_rate': 0, 'avg_monthly': 0}
    contract_data = [0, 0, 0]
    internet_data = [0, 0, 0]
    monthly_labels = ['0-20', '20-40', '40-60', '60-80', '80-100', '100+']
    monthly_data = [0, 0, 0, 0, 0, 0]
    tech_support_data = [0, 0]
    payment_data = [0, 0, 0, 0]
    customers = []

    if 'uploaded_file' in session:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], session['uploaded_file'])
        try:
            df = pd.read_csv(filepath)

            if contract_filter!= 'all' and 'Contract' in df.columns:
                df = df[df['Contract'] == contract_filter]

            churn_predictions = predict_churn(df)
            df['Churn_Pred'] = churn_predictions
            total = len(df)
            churn_count = int(sum(churn_predictions))
            metrics = {
                'churn_count': churn_count,
                'total_customers': total,
                'churn_rate': round((churn_count/total)*100, 1) if total > 0 else 0,
                'avg_monthly': 0
            }
            charge_col = 'MonthlyCharges' if 'MonthlyCharges' in df.columns else 'Monthly Charges' if 'Monthly Charges' in df.columns else None
            if charge_col:
                try:
                    df[charge_col] = pd.to_numeric(df[charge_col], errors='coerce').fillna(0)
                    metrics['avg_monthly'] = round(df[charge_col].mean(), 2)
                except: metrics['avg_monthly'] = 0
            if 'Contract' in df.columns:
                contract_churn = df[df['Churn_Pred'] == 1]['Contract'].value_counts()
                contract_data = [
                    round(contract_churn.get('Month-to-month', 0) / total * 100, 1),
                    round(contract_churn.get('One year', 0) / total * 100, 1),
                    round(contract_churn.get('Two year', 0) / total * 100, 1)
                ]
            if 'InternetService' in df.columns:
                internet_churn = df[df['Churn_Pred'] == 1]['InternetService'].value_counts()
                internet_data = [
                    round(internet_churn.get('Fiber optic', 0) / total * 100, 1),
                    round(internet_churn.get('DSL', 0) / total * 100, 1),
                    round(internet_churn.get('No', 0) / total * 100, 1)
                ]
            if charge_col:
                bins = [0, 20, 40, 60, 80, 100, 10000]
                labels = ['0-20', '20-40', '40-60', '60-80', '80-100', '100+']
                df['charge_bin'] = pd.cut(df[charge_col], bins=bins, labels=labels)
                monthly_churn = df[df['Churn_Pred'] == 1]['charge_bin'].value_counts()
                monthly_data = [round(monthly_churn.get(label, 0) / total * 100, 1) for label in labels]
            tech_col = 'TechSupport' if 'TechSupport' in df.columns else 'Tech Support' if 'Tech Support' in df.columns else None
            if tech_col:
                tech_churn = df[df['Churn_Pred'] == 1][tech_col].value_counts()
                tech_support_data = [
                    round(tech_churn.get('Yes', 0) / total * 100, 1),
                    round(tech_churn.get('No', 0) / total * 100, 1)
                ]
            pay_col = 'PaymentMethod' if 'PaymentMethod' in df.columns else 'Payment Method' if 'Payment Method' in df.columns else None
            if pay_col:
                pay_churn = df[df['Churn_Pred'] == 1][pay_col].value_counts()
                payment_data = [
                    round(pay_churn.get('Electronic check', 0) / total * 100, 1),
                    round(pay_churn.get('Mailed check', 0) / total * 100, 1),
                    round(pay_churn.get('Bank transfer (automatic)', pay_churn.get('Bank transfer', 0)) / total * 100, 1),
                    round(pay_churn.get('Credit card (automatic)', pay_churn.get('Credit card', 0)) / total * 100, 1)
                ]
            df['prob'] = df['Churn_Pred'].apply(lambda x: 85 if x == 1 else 15)
            if 'customerID' in df.columns:
                top_customers = df.nlargest(5, 'prob')[['customerID', 'prob']]
            else:
                df['customerID'] = ['C' + str(i+1).zfill(4) for i in range(len(df))]
                top_customers = df.nlargest(5, 'prob')[['customerID', 'prob']]
            customers = [
                {'id': str(row['customerID']), 'probability': int(row['prob'])}
                for _, row in top_customers.iterrows()
            ]
        except Exception as e:
            flash(f'Error reading CSV: {str(e)}', 'error')

    return render_template('dashboard.html',
                         metrics=metrics,
                         contract_data=contract_data,
                         internet_data=internet_data,
                         monthly_labels=monthly_labels,
                         monthly_data=monthly_data,
                         tech_support_data=tech_support_data,
                         payment_data=payment_data,
                         customers=customers,
                         contract_filter=contract_filter)

@app.route('/predict_single', methods=['GET', 'POST'])
def predict_single():
    if 'logged_in' not in session: return redirect(url_for('login'))
    prediction = None
    probability = None
    if request.method == 'POST':
        tenure = float(request.form.get('tenure', 0))
        monthly = float(request.form.get('monthly', 0))
        contract = request.form.get('contract', 'Month-to-month')

        score = 0
        if 'month' in contract.lower(): score += 0.4
        if tenure < 12: score += 0.3
        if monthly > 70: score += 0.3

        prediction = 1 if score > 0.5 else 0
        probability = 85 if prediction == 1 else 15

    return render_template('predict_single.html', prediction=prediction, probability=probability)

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'logged_in' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        file = request.files.get('file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            df = pd.read_csv(filepath)

            # FIX: Bracket close chesa ikkada
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('INSERT INTO uploads (email, filename, total_rows) VALUES (?,?,?)',
                     (session['email'], filename, len(df))) # ✅ ) add chesanu
            conn.commit()
            conn.close()

            flash(f'File uploaded! Rows: {len(df)}', 'success')
            session['uploaded_file'] = filename
            return redirect(url_for('dashboard'))
        flash('Only CSV files allowed', 'error')
    return render_template('upload.html')

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)