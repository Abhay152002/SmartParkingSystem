# smart_parking_system/app.py

from flask import Flask, render_template, Response, redirect, url_for, request, session, jsonify
import cv2, pickle, numpy as np, csv, datetime
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps

app = Flask(__name__)
app.secret_key = "supersecretkey"

width, height = 103, 43
with open('CarParkPos', 'rb') as f:
    posList = pickle.load(f)

# Default source (0 = webcam)
video_source = {'current': 'carPark.mp4'}

# =================== User Management ======================

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    conn.commit()
    conn.close()

def validate_user(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (username,))
    user = c.fetchone()
    conn.close()
    if user and check_password_hash(user[0], password):
        return True
    return False

def add_user(username, password):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    hashed_pw = generate_password_hash(password)
    try:
        c.execute("INSERT INTO users VALUES (?, ?)", (username, hashed_pw))
        conn.commit()
    except:
        pass
    conn.close()

# =================== Decorator ======================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# =================== Video + Parking ======================

show_video = True

def check_spaces(img):
    imgGray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    imgBlur = cv2.GaussianBlur(imgGray, (3, 3), 1)
    imgThres = cv2.adaptiveThreshold(imgBlur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, 25, 16)
    imgThres = cv2.medianBlur(imgThres, 5)
    imgThres = cv2.dilate(imgThres, np.ones((3, 3), np.uint8), iterations=1)

    statuses, free = [], 0
    for pos in posList:
        x, y = pos
        imgCrop = imgThres[y:y + height, x:x + width]
        count = cv2.countNonZero(imgCrop)
        status = 1 if count < 900 else 0
        statuses.append(status)
        color = (0, 255, 0) if status else (0, 0, 255)
        cv2.rectangle(img, (x, y), (x + width, y + height), color, 3)

    free = statuses.count(1)
    cv2.rectangle(img, (30, 30), (300, 80), (255, 255, 255), -1)
    cv2.putText(img, f'Free: {free}/{len(statuses)}', (40, 65), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 128, 0), 3)
    return img, statuses

def generate_frames():
    cap = cv2.VideoCapture(video_source['current'])
    while True:
        success, img = cap.read()
        if not success:
            cap = cv2.VideoCapture(video_source['current'])
            continue
        if show_video:
            img, _ = check_spaces(img)
        _, buffer = cv2.imencode('.jpg', img)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# =================== Routes ======================

@app.route('/')
@login_required
def home():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    init_db()
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        if validate_user(user, pw):
            session['user'] = user
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/register')
def register():
    init_db()
    add_user("admin", "admin123")
    return "User registered. Go to /login"

@app.route('/video')
@login_required
def video():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/toggle/<state>')
@login_required
def toggle(state):
    global show_video
    show_video = (state == 'show')
    return ('', 204)

@app.route('/set-source', methods=['POST'])
@login_required
def set_source():
    source = request.form['source']
    try:
        if source.startswith('http'):
            video_source['current'] = source
        elif source.startswith('0'):
            video_source['current'] = int(source)
        elif source.startswith('uploaded'):
            video_source['current'] = 'carPark.mp4'
        return jsonify({"message": "Source changed successfully"})
    except:
        return jsonify({"error": "Invalid source"}), 400

@app.route('/save-history')
@login_required
def save_history():
    cap = cv2.VideoCapture(video_source['current'])
    success, img = cap.read()
    if not success: return jsonify({"error": "No frame"}), 400
    _, statuses = check_spaces(img)
    with open('history.csv', 'a', newline='') as f:
        csv.writer(f).writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")] + statuses)
    return jsonify({"message": "History saved"})

@app.route('/get-history')
@login_required
def get_history():
    try:
        with open('history.csv', 'r') as f:
            return jsonify(list(csv.reader(f)))
    except FileNotFoundError:
        return jsonify([])

if __name__ == '__main__':
    app.run(debug=True)
