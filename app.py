from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import random
import string
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'bgmi_ultimate_arena_2026_secret'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ADMIN_PASSWORD = 'JAYASPALDADA'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    db = sqlite3.connect('bgmi_tournament.db')
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS tournaments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            game_mode TEXT NOT NULL,
            entry_fee TEXT NOT NULL,
            prize_pool TEXT NOT NULL,
            max_teams INTEGER NOT NULL DEFAULT 16,
            description TEXT,
            upi_id TEXT,
            registration_deadline TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reg_id TEXT UNIQUE NOT NULL,
            tournament_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            player1 TEXT NOT NULL,
            player2 TEXT NOT NULL,
            player3 TEXT NOT NULL,
            player4 TEXT NOT NULL,
            contact TEXT NOT NULL,
            payment_screenshot TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        );

        CREATE TABLE IF NOT EXISTS live_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            stream_url TEXT NOT NULL,
            stream_type TEXT DEFAULT 'youtube',
            status TEXT DEFAULT 'live',
            scheduled_time TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        );
    ''')
    db.commit()
    db.close()

def generate_reg_id():
    return 'REG-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_youtube_embed_url(url):
    """Convert YouTube URL to embed URL"""
    if 'youtube.com/watch?v=' in url:
        video_id = url.split('v=')[1].split('&')[0]
        return f'https://www.youtube.com/embed/{video_id}?autoplay=1'
    elif 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[1].split('?')[0]
        return f'https://www.youtube.com/embed/{video_id}?autoplay=1'
    elif 'youtube.com/live/' in url:
        video_id = url.split('live/')[1].split('?')[0]
        return f'https://www.youtube.com/embed/{video_id}?autoplay=1'
    elif 'youtube.com/embed/' in url:
        return url
    return url

# Routes
@app.route('/')
def index():
    db = get_db()
    active_tournaments = db.execute(
        'SELECT t.*, (SELECT COUNT(*) FROM registrations r WHERE r.tournament_id = t.id AND r.status = "approved") as filled_slots FROM tournaments t WHERE t.status = "active" ORDER BY t.created_at DESC'
    ).fetchall()
    past_tournaments = db.execute(
        'SELECT * FROM tournaments WHERE status = "completed" ORDER BY created_at DESC'
    ).fetchall()
    live_matches = db.execute(
        'SELECT lm.*, t.name as tournament_name FROM live_matches lm LEFT JOIN tournaments t ON lm.tournament_id = t.id WHERE lm.status = "live" ORDER BY lm.created_at DESC'
    ).fetchall()
    db.close()
    return render_template('index.html', active_tournaments=active_tournaments, past_tournaments=past_tournaments, live_matches=live_matches)

@app.route('/live')
def live_page():
    db = get_db()
    live_matches = db.execute(
        'SELECT lm.*, t.name as tournament_name FROM live_matches lm LEFT JOIN tournaments t ON lm.tournament_id = t.id WHERE lm.status = "live" ORDER BY lm.created_at DESC'
    ).fetchall()
    upcoming_matches = db.execute(
        'SELECT lm.*, t.name as tournament_name FROM live_matches lm LEFT JOIN tournaments t ON lm.tournament_id = t.id WHERE lm.status = "upcoming" ORDER BY lm.scheduled_time ASC'
    ).fetchall()
    past_matches = db.execute(
        'SELECT lm.*, t.name as tournament_name FROM live_matches lm LEFT JOIN tournaments t ON lm.tournament_id = t.id WHERE lm.status = "ended" ORDER BY lm.created_at DESC LIMIT 10'
    ).fetchall()
    db.close()
    return render_template('live.html', live_matches=live_matches, upcoming_matches=upcoming_matches, past_matches=past_matches)

@app.route('/live/<int:match_id>')
def watch_live(match_id):
    db = get_db()
    match = db.execute(
        'SELECT lm.*, t.name as tournament_name FROM live_matches lm LEFT JOIN tournaments t ON lm.tournament_id = t.id WHERE lm.id = ?',
        (match_id,)
    ).fetchone()
    db.close()
    if not match:
        flash('Match not found', 'error')
        return redirect(url_for('live_page'))
    embed_url = get_youtube_embed_url(match['stream_url'])
    return render_template('watch.html', match=match, embed_url=embed_url)

@app.route('/register/<int:tournament_id>', methods=['GET', 'POST'])
def register(tournament_id):
    db = get_db()
    tournament = db.execute('SELECT * FROM tournaments WHERE id = ?', (tournament_id,)).fetchone()
    if not tournament:
        flash('Tournament not found', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        team_name = request.form.get('team_name')
        player1 = request.form.get('player1')
        player2 = request.form.get('player2')
        player3 = request.form.get('player3')
        player4 = request.form.get('player4')
        contact = request.form.get('contact')

        # Handle file upload
        screenshot_filename = None
        if 'payment_screenshot' in request.files:
            file = request.files['payment_screenshot']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                screenshot_filename = filename

        reg_id = generate_reg_id()
        db.execute(
            'INSERT INTO registrations (reg_id, tournament_id, team_name, player1, player2, player3, player4, contact, payment_screenshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (reg_id, tournament_id, team_name, player1, player2, player3, player4, contact, screenshot_filename)
        )
        db.commit()
        db.close()
        return render_template('registration_success.html', reg_id=reg_id, tournament=tournament)

    db.close()
    return render_template('register.html', tournament=tournament)

@app.route('/check-status', methods=['GET', 'POST'])
def check_status():
    registration = None
    if request.method == 'POST':
        reg_id = request.form.get('reg_id', '').strip().upper()
        db = get_db()
        registration = db.execute(
            'SELECT r.*, t.name as tournament_name FROM registrations r JOIN tournaments t ON r.tournament_id = t.id WHERE r.reg_id = ?',
            (reg_id,)
        ).fetchone()
        db.close()
    return render_template('check_status.html', registration=registration)

# Admin Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Incorrect password', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    tournaments = db.execute('SELECT * FROM tournaments ORDER BY created_at DESC').fetchall()
    stats = db.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM registrations
    ''').fetchone()
    live_matches = db.execute(
        'SELECT lm.*, t.name as tournament_name FROM live_matches lm LEFT JOIN tournaments t ON lm.tournament_id = t.id ORDER BY lm.created_at DESC'
    ).fetchall()
    db.close()
    return render_template('admin_dashboard.html', tournaments=tournaments, stats=stats, live_matches=live_matches)

@app.route('/admin/tournament/create', methods=['POST'])
def create_tournament():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    name = request.form.get('name')
    game_mode = request.form.get('game_mode')
    entry_fee = request.form.get('entry_fee')
    prize_pool = request.form.get('prize_pool')
    max_teams = request.form.get('max_teams', 16)
    description = request.form.get('description')
    upi_id = request.form.get('upi_id')
    registration_deadline = request.form.get('registration_deadline')

    db = get_db()
    db.execute(
        'INSERT INTO tournaments (name, game_mode, entry_fee, prize_pool, max_teams, description, upi_id, registration_deadline) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (name, game_mode, entry_fee, prize_pool, max_teams, description, upi_id, registration_deadline)
    )
    db.commit()
    db.close()
    flash('Tournament created successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tournament/<int:tournament_id>/delete', methods=['POST'])
def delete_tournament(tournament_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('DELETE FROM registrations WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM live_matches WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM tournaments WHERE id = ?', (tournament_id,))
    db.commit()
    db.close()
    flash('Tournament deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tournament/<int:tournament_id>/complete', methods=['POST'])
def complete_tournament(tournament_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE tournaments SET status = "completed" WHERE id = ?', (tournament_id,))
    db.commit()
    db.close()
    flash('Tournament marked as completed!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tournament/<int:tournament_id>')
def admin_tournament_detail(tournament_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    tournament = db.execute('SELECT * FROM tournaments WHERE id = ?', (tournament_id,)).fetchone()
    registrations = db.execute(
        'SELECT * FROM registrations WHERE tournament_id = ? ORDER BY created_at DESC',
        (tournament_id,)
    ).fetchall()
    stats = db.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM registrations WHERE tournament_id = ?
    ''', (tournament_id,)).fetchone()
    db.close()
    return render_template('admin_tournament.html', tournament=tournament, registrations=registrations, stats=stats)

@app.route('/admin/registration/<int:reg_id>/approve', methods=['POST'])
def approve_registration(reg_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    reg = db.execute('SELECT tournament_id FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    db.execute('UPDATE registrations SET status = "approved" WHERE id = ?', (reg_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_tournament_detail', tournament_id=reg['tournament_id']))

@app.route('/admin/registration/<int:reg_id>/reject', methods=['POST'])
def reject_registration(reg_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    reg = db.execute('SELECT tournament_id FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    db.execute('UPDATE registrations SET status = "rejected" WHERE id = ?', (reg_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_tournament_detail', tournament_id=reg['tournament_id']))

@app.route('/admin/registration/<int:reg_id>/reset', methods=['POST'])
def reset_registration(reg_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    reg = db.execute('SELECT tournament_id FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    db.execute('UPDATE registrations SET status = "pending" WHERE id = ?', (reg_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_tournament_detail', tournament_id=reg['tournament_id']))

# Live Match Admin Routes
@app.route('/admin/live/create', methods=['POST'])
def create_live_match():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    title = request.form.get('title')
    description = request.form.get('description')
    stream_url = request.form.get('stream_url')
    stream_type = request.form.get('stream_type', 'youtube')
    tournament_id = request.form.get('tournament_id')
    status = request.form.get('status', 'live')
    scheduled_time = request.form.get('scheduled_time')

    if tournament_id == '' or tournament_id == 'none':
        tournament_id = None

    db = get_db()
    db.execute(
        'INSERT INTO live_matches (tournament_id, title, description, stream_url, stream_type, status, scheduled_time) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (tournament_id, title, description, stream_url, stream_type, status, scheduled_time)
    )
    db.commit()
    db.close()
    flash('Live match created successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/live/<int:match_id>/delete', methods=['POST'])
def delete_live_match(match_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('DELETE FROM live_matches WHERE id = ?', (match_id,))
    db.commit()
    db.close()
    flash('Live match removed!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/live/<int:match_id>/end', methods=['POST'])
def end_live_match(match_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE live_matches SET status = "ended" WHERE id = ?', (match_id,))
    db.commit()
    db.close()
    flash('Match ended!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/live/<int:match_id>/golive', methods=['POST'])
def golive_match(match_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE live_matches SET status = "live" WHERE id = ?', (match_id,))
    db.commit()
    db.close()
    flash('Match is now LIVE!', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
