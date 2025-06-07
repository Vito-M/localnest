import os
import uuid
import sqlite3
import secrets
from flask import Flask, request, redirect, render_template, send_file, session, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Non più hardcoded
UPLOAD_FOLDER = 'data'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['username'] = username
            session['user_id'] = user['id']
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Credenziali non valide')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        password_confirm = request.form['password_confirm']

        if password != password_confirm:
            return render_template('register.html', error='Le password non coincidono')

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            conn.execute(
                'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                (username, email, hashed_password)
            )
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return render_template('register.html', error='Username o email già esistente')

    return render_template('register.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'username' not in session or 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        file = request.files['file']
        if file:
            try:
                original_filename = file.filename
                unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)

                conn = get_db_connection()
                conn.execute('INSERT INTO files (user_id, filename, original_filename) VALUES (?, ?, ?)', 
                            (session['user_id'], unique_filename, original_filename))
                conn.commit()
                conn.close()
                return redirect(url_for('dashboard', upload='success'))
            except Exception as e:
                return redirect(url_for('dashboard', upload='error'))

    conn = get_db_connection()
    files = conn.execute('SELECT id, filename, original_filename FROM files WHERE user_id = ?', (session['user_id'],)).fetchall()
    user = conn.execute('SELECT email FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    return render_template('upload.html', files=files, username=session['username'], email=user['email'])

# Messo controllo contro IDOR
@app.route('/download/<int:file_identifier>')
def download_file(file_identifier):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    file = conn.execute(
        'SELECT filename, original_filename FROM files WHERE id = ? AND user_id = ?',
        (file_identifier, session['user_id'])
    ).fetchone()
    conn.close()

    if not file:
        return "ID non valido o accesso non autorizzato", 403

    file_path = os.path.join(UPLOAD_FOLDER, file['filename'])
    if os.path.isfile(file_path):
        return send_file(file_path, as_attachment=True, download_name=file['original_filename'])

    return "File non trovato", 404

# Messo controllo contro IDOR
@app.route('/delete/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        conn = get_db_connection()
        file = conn.execute(
            'SELECT filename FROM files WHERE id = ? AND user_id = ?',
            (file_id, session['user_id'])
        ).fetchone()

        if file:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
            conn.execute('DELETE FROM files WHERE id = ?', (file_id,))
            conn.commit()
            conn.close()
            return redirect(url_for('dashboard', delete='success'))

        conn.close()
        return redirect(url_for('dashboard', delete='nessunfile'))
    except Exception as e:
        return redirect(url_for('dashboard', delete='nessunaconnessione'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
