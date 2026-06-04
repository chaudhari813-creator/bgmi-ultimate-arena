from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
import random
import string
import json
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'bgmi_ultimate_arena_2026_secret'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4'}
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

        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            round_name TEXT NOT NULL,
            team1_id INTEGER,
            team2_id INTEGER,
            team1_name TEXT,
            team2_name TEXT,
            winner_id INTEGER,
            team1_kills INTEGER DEFAULT 0,
            team2_kills INTEGER DEFAULT 0,
            match_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        );

        CREATE TABLE IF NOT EXISTS leaderboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            total_kills INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        );

        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'sub_admin',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS prizes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            team_name TEXT NOT NULL,
            prize_amount TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            upi_id TEXT,
            paid_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        );

        CREATE TABLE IF NOT EXISTS gallery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tournament_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            media_type TEXT DEFAULT 'image',
            filename TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tournament_id) REFERENCES tournaments(id)
        );
    ''')
    # Insert default super admin if not exists
    existing = db.execute("SELECT * FROM admins WHERE username = 'superadmin'").fetchone()
    if not existing:
        db.execute("INSERT INTO admins (username, password, role) VALUES ('superadmin', ?, 'super_admin')", (ADMIN_PASSWORD,))
    db.commit()
    db.close()

def generate_reg_id():
    return 'REG-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_youtube_embed_url(url):
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

def is_admin():
    return session.get('admin') or session.get('sub_admin')

def is_super_admin():
    return session.get('admin')

# ============ PUBLIC ROUTES ============

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

@app.route('/leaderboard')
def leaderboard():
    db = get_db()
    tournaments = db.execute('SELECT * FROM tournaments ORDER BY created_at DESC').fetchall()
    tournament_id = request.args.get('tournament_id', type=int)
    entries = []
    selected_tournament = None
    if tournament_id:
        entries = db.execute(
            'SELECT * FROM leaderboard WHERE tournament_id = ? ORDER BY points DESC, total_kills DESC',
            (tournament_id,)
        ).fetchall()
        selected_tournament = db.execute('SELECT * FROM tournaments WHERE id = ?', (tournament_id,)).fetchone()
    db.close()
    return render_template('leaderboard.html', tournaments=tournaments, entries=entries, selected_tournament=selected_tournament, tournament_id=tournament_id)

@app.route('/brackets/<int:tournament_id>')
def brackets(tournament_id):
    db = get_db()
    tournament = db.execute('SELECT * FROM tournaments WHERE id = ?', (tournament_id,)).fetchone()
    if not tournament:
        flash('Tournament not found', 'error')
        return redirect(url_for('index'))
    matches = db.execute(
        'SELECT * FROM match_results WHERE tournament_id = ? ORDER BY round_name, match_order',
        (tournament_id,)
    ).fetchall()
    # Group matches by round
    rounds = {}
    for m in matches:
        if m['round_name'] not in rounds:
            rounds[m['round_name']] = []
        rounds[m['round_name']].append(m)
    db.close()
    return render_template('brackets.html', tournament=tournament, rounds=rounds)

@app.route('/team/<int:team_id>')
def team_profile(team_id):
    db = get_db()
    team = db.execute('SELECT * FROM registrations WHERE id = ?', (team_id,)).fetchone()
    if not team:
        flash('Team not found', 'error')
        return redirect(url_for('index'))
    tournament = db.execute('SELECT * FROM tournaments WHERE id = ?', (team['tournament_id'],)).fetchone()
    # Get match history
    matches = db.execute(
        'SELECT * FROM match_results WHERE team1_id = ? OR team2_id = ? ORDER BY created_at DESC',
        (team_id, team_id)
    ).fetchall()
    # Get leaderboard entry
    lb_entry = db.execute(
        'SELECT * FROM leaderboard WHERE team_id = ? AND tournament_id = ?',
        (team_id, team['tournament_id'])
    ).fetchone()
    db.close()
    return render_template('team_profile.html', team=team, tournament=tournament, matches=matches, lb_entry=lb_entry)

@app.route('/gallery')
def gallery_page():
    db = get_db()
    items = db.execute(
        'SELECT g.*, t.name as tournament_name FROM gallery g LEFT JOIN tournaments t ON g.tournament_id = t.id ORDER BY g.created_at DESC'
    ).fetchall()
    db.close()
    return render_template('gallery.html', items=items)

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

# ============ ADMIN ROUTES ============

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        
        # Check super admin
        if password == ADMIN_PASSWORD and (username == '' or username == 'superadmin'):
            session['admin'] = True
            session['admin_username'] = 'superadmin'
            return redirect(url_for('admin_dashboard'))
        
        # Check sub-admins
        db = get_db()
        admin = db.execute('SELECT * FROM admins WHERE username = ? AND password = ?', (username, password)).fetchone()
        db.close()
        if admin:
            if admin['role'] == 'super_admin':
                session['admin'] = True
            else:
                session['sub_admin'] = True
            session['admin_username'] = admin['username']
            return redirect(url_for('admin_dashboard'))
        
        flash('Incorrect credentials', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    session.pop('sub_admin', None)
    session.pop('admin_username', None)
    return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not is_admin():
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
    admins = db.execute('SELECT * FROM admins ORDER BY created_at DESC').fetchall() if is_super_admin() else []
    db.close()
    return render_template('admin_dashboard.html', tournaments=tournaments, stats=stats, live_matches=live_matches, admins=admins)

@app.route('/admin/tournament/create', methods=['POST'])
def create_tournament():
    if not is_admin():
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
    if not is_super_admin():
        flash('Only super admin can delete tournaments', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    db.execute('DELETE FROM registrations WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM live_matches WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM match_results WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM leaderboard WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM prizes WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM gallery WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM tournaments WHERE id = ?', (tournament_id,))
    db.commit()
    db.close()
    flash('Tournament deleted successfully!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tournament/<int:tournament_id>/complete', methods=['POST'])
def complete_tournament(tournament_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE tournaments SET status = "completed" WHERE id = ?', (tournament_id,))
    db.commit()
    db.close()
    flash('Tournament marked as completed!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tournament/<int:tournament_id>')
def admin_tournament_detail(tournament_id):
    if not is_admin():
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
    matches = db.execute('SELECT * FROM match_results WHERE tournament_id = ? ORDER BY round_name, match_order', (tournament_id,)).fetchall()
    prizes_list = db.execute('SELECT * FROM prizes WHERE tournament_id = ? ORDER BY position', (tournament_id,)).fetchall()
    db.close()
    return render_template('admin_tournament.html', tournament=tournament, registrations=registrations, stats=stats, matches=matches, prizes=prizes_list)

@app.route('/admin/registration/<int:reg_id>/approve', methods=['POST'])
def approve_registration(reg_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    reg = db.execute('SELECT tournament_id FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    db.execute('UPDATE registrations SET status = "approved" WHERE id = ?', (reg_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_tournament_detail', tournament_id=reg['tournament_id']))

@app.route('/admin/registration/<int:reg_id>/reject', methods=['POST'])
def reject_registration(reg_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    reg = db.execute('SELECT tournament_id FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    db.execute('UPDATE registrations SET status = "rejected" WHERE id = ?', (reg_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_tournament_detail', tournament_id=reg['tournament_id']))

@app.route('/admin/registration/<int:reg_id>/reset', methods=['POST'])
def reset_registration(reg_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    reg = db.execute('SELECT tournament_id FROM registrations WHERE id = ?', (reg_id,)).fetchone()
    db.execute('UPDATE registrations SET status = "pending" WHERE id = ?', (reg_id,))
    db.commit()
    db.close()
    return redirect(url_for('admin_tournament_detail', tournament_id=reg['tournament_id']))

# ============ BRACKET & MATCH ROUTES ============

@app.route('/admin/tournament/<int:tournament_id>/generate-brackets', methods=['POST'])
def generate_brackets(tournament_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    # Get approved teams
    teams = db.execute(
        'SELECT * FROM registrations WHERE tournament_id = ? AND status = "approved"',
        (tournament_id,)
    ).fetchall()
    if len(teams) < 2:
        flash('Need at least 2 approved teams to generate brackets', 'error')
        return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))
    
    # Clear existing brackets
    db.execute('DELETE FROM match_results WHERE tournament_id = ?', (tournament_id,))
    db.execute('DELETE FROM leaderboard WHERE tournament_id = ?', (tournament_id,))
    
    # Shuffle and pair teams
    team_list = list(teams)
    random.shuffle(team_list)
    
    round_name = 'Round 1'
    for i in range(0, len(team_list) - 1, 2):
        t1 = team_list[i]
        t2 = team_list[i + 1]
        db.execute(
            'INSERT INTO match_results (tournament_id, round_name, team1_id, team2_id, team1_name, team2_name, match_order) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (tournament_id, round_name, t1['id'], t2['id'], t1['team_name'], t2['team_name'], i // 2 + 1)
        )
    
    # If odd number, last team gets a bye
    if len(team_list) % 2 != 0:
        last = team_list[-1]
        db.execute(
            'INSERT INTO match_results (tournament_id, round_name, team1_id, team2_id, team1_name, team2_name, winner_id, match_order) VALUES (?, ?, ?, NULL, ?, "BYE", ?, ?)',
            (tournament_id, round_name, last['id'], last['team_name'], last['id'], len(team_list) // 2 + 1)
        )
    
    # Initialize leaderboard
    for t in team_list:
        db.execute(
            'INSERT INTO leaderboard (tournament_id, team_id, team_name) VALUES (?, ?, ?)',
            (tournament_id, t['id'], t['team_name'])
        )
    
    db.commit()
    db.close()
    flash('Brackets generated successfully!', 'success')
    return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))

@app.route('/admin/match/<int:match_id>/result', methods=['POST'])
def set_match_result(match_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    
    winner_id = request.form.get('winner_id', type=int)
    team1_kills = request.form.get('team1_kills', 0, type=int)
    team2_kills = request.form.get('team2_kills', 0, type=int)
    
    db = get_db()
    match = db.execute('SELECT * FROM match_results WHERE id = ?', (match_id,)).fetchone()
    
    db.execute(
        'UPDATE match_results SET winner_id = ?, team1_kills = ?, team2_kills = ? WHERE id = ?',
        (winner_id, team1_kills, team2_kills, match_id)
    )
    
    # Update leaderboard
    if match['team1_id']:
        if winner_id == match['team1_id']:
            db.execute('UPDATE leaderboard SET wins = wins + 1, points = points + 3, total_kills = total_kills + ? WHERE team_id = ? AND tournament_id = ?',
                      (team1_kills, match['team1_id'], match['tournament_id']))
            if match['team2_id']:
                db.execute('UPDATE leaderboard SET losses = losses + 1, total_kills = total_kills + ? WHERE team_id = ? AND tournament_id = ?',
                          (team2_kills, match['team2_id'], match['tournament_id']))
        elif winner_id == match['team2_id']:
            db.execute('UPDATE leaderboard SET wins = wins + 1, points = points + 3, total_kills = total_kills + ? WHERE team_id = ? AND tournament_id = ?',
                      (team2_kills, match['team2_id'], match['tournament_id']))
            db.execute('UPDATE leaderboard SET losses = losses + 1, total_kills = total_kills + ? WHERE team_id = ? AND tournament_id = ?',
                      (team1_kills, match['team1_id'], match['tournament_id']))
    
    db.commit()
    db.close()
    flash('Match result updated!', 'success')
    return redirect(url_for('admin_tournament_detail', tournament_id=match['tournament_id']))

@app.route('/admin/tournament/<int:tournament_id>/next-round', methods=['POST'])
def generate_next_round(tournament_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    
    # Get current rounds
    rounds = db.execute(
        'SELECT DISTINCT round_name FROM match_results WHERE tournament_id = ? ORDER BY round_name',
        (tournament_id,)
    ).fetchall()
    
    if not rounds:
        flash('No rounds exist yet', 'error')
        return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))
    
    current_round = rounds[-1]['round_name']
    
    # Get winners from current round
    winners = db.execute(
        'SELECT winner_id FROM match_results WHERE tournament_id = ? AND round_name = ? AND winner_id IS NOT NULL',
        (tournament_id, current_round)
    ).fetchall()
    
    if not winners:
        flash('No winners set in current round yet', 'error')
        return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))
    
    # Determine next round name
    round_num = len(rounds) + 1
    if len(winners) == 2:
        next_round = 'Final'
    elif len(winners) <= 4:
        next_round = 'Semi Final'
    else:
        next_round = f'Round {round_num}'
    
    # Get team names for winners
    winner_teams = []
    for w in winners:
        team = db.execute('SELECT * FROM registrations WHERE id = ?', (w['winner_id'],)).fetchone()
        if team:
            winner_teams.append(team)
    
    # Pair winners
    for i in range(0, len(winner_teams) - 1, 2):
        t1 = winner_teams[i]
        t2 = winner_teams[i + 1]
        db.execute(
            'INSERT INTO match_results (tournament_id, round_name, team1_id, team2_id, team1_name, team2_name, match_order) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (tournament_id, next_round, t1['id'], t2['id'], t1['team_name'], t2['team_name'], i // 2 + 1)
        )
    
    if len(winner_teams) % 2 != 0:
        last = winner_teams[-1]
        db.execute(
            'INSERT INTO match_results (tournament_id, round_name, team1_id, team2_id, team1_name, team2_name, winner_id, match_order) VALUES (?, ?, ?, NULL, ?, "BYE", ?, ?)',
            (tournament_id, next_round, last['id'], last['team_name'], last['id'], len(winner_teams) // 2 + 1)
        )
    
    db.commit()
    db.close()
    flash(f'{next_round} generated!', 'success')
    return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))

# ============ LIVE MATCH ROUTES ============

@app.route('/admin/live/create', methods=['POST'])
def create_live_match():
    if not is_admin():
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
    flash('Live match created!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/live/<int:match_id>/delete', methods=['POST'])
def delete_live_match(match_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('DELETE FROM live_matches WHERE id = ?', (match_id,))
    db.commit()
    db.close()
    flash('Live match removed!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/live/<int:match_id>/end', methods=['POST'])
def end_live_match(match_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE live_matches SET status = "ended" WHERE id = ?', (match_id,))
    db.commit()
    db.close()
    flash('Match ended!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/live/<int:match_id>/golive', methods=['POST'])
def golive_match(match_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    db.execute('UPDATE live_matches SET status = "live" WHERE id = ?', (match_id,))
    db.commit()
    db.close()
    flash('Match is now LIVE!', 'success')
    return redirect(url_for('admin_dashboard'))

# ============ ADMIN MANAGEMENT ============

@app.route('/admin/admins/create', methods=['POST'])
def create_sub_admin():
    if not is_super_admin():
        flash('Only super admin can manage admins', 'error')
        return redirect(url_for('admin_dashboard'))
    username = request.form.get('username', '').strip()
    password = request.form.get('password')
    role = request.form.get('role', 'sub_admin')
    if not username or not password:
        flash('Username and password required', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    try:
        db.execute('INSERT INTO admins (username, password, role) VALUES (?, ?, ?)', (username, password, role))
        db.commit()
        flash(f'Admin "{username}" created!', 'success')
    except:
        flash('Username already exists', 'error')
    db.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/admins/<int:admin_id>/delete', methods=['POST'])
def delete_sub_admin(admin_id):
    if not is_super_admin():
        flash('Only super admin can manage admins', 'error')
        return redirect(url_for('admin_dashboard'))
    db = get_db()
    db.execute('DELETE FROM admins WHERE id = ? AND role != "super_admin"', (admin_id,))
    db.commit()
    db.close()
    flash('Admin removed!', 'success')
    return redirect(url_for('admin_dashboard'))

# ============ PRIZE ROUTES ============

@app.route('/admin/tournament/<int:tournament_id>/prize/add', methods=['POST'])
def add_prize(tournament_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    position = request.form.get('position', type=int)
    team_name = request.form.get('team_name')
    prize_amount = request.form.get('prize_amount')
    upi_id = request.form.get('upi_id')
    db = get_db()
    db.execute(
        'INSERT INTO prizes (tournament_id, position, team_name, prize_amount, upi_id) VALUES (?, ?, ?, ?, ?)',
        (tournament_id, position, team_name, prize_amount, upi_id)
    )
    db.commit()
    db.close()
    flash('Prize added!', 'success')
    return redirect(url_for('admin_tournament_detail', tournament_id=tournament_id))

@app.route('/admin/prize/<int:prize_id>/paid', methods=['POST'])
def mark_prize_paid(prize_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    prize = db.execute('SELECT * FROM prizes WHERE id = ?', (prize_id,)).fetchone()
    db.execute('UPDATE prizes SET status = "paid", paid_at = ? WHERE id = ?', (datetime.now().strftime('%Y-%m-%d %H:%M'), prize_id))
    db.commit()
    db.close()
    flash('Prize marked as paid!', 'success')
    return redirect(url_for('admin_tournament_detail', tournament_id=prize['tournament_id']))

@app.route('/admin/prize/<int:prize_id>/delete', methods=['POST'])
def delete_prize(prize_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    prize = db.execute('SELECT * FROM prizes WHERE id = ?', (prize_id,)).fetchone()
    db.execute('DELETE FROM prizes WHERE id = ?', (prize_id,))
    db.commit()
    db.close()
    flash('Prize removed!', 'success')
    return redirect(url_for('admin_tournament_detail', tournament_id=prize['tournament_id']))

# ============ GALLERY ROUTES ============

@app.route('/admin/gallery/upload', methods=['POST'])
def upload_gallery():
    if not is_admin():
        return redirect(url_for('admin_login'))
    title = request.form.get('title')
    description = request.form.get('description')
    tournament_id = request.form.get('tournament_id')
    if tournament_id == '' or tournament_id == 'none':
        tournament_id = None
    
    if 'media' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files['media']
    if file and allowed_file(file.filename):
        filename = secure_filename(f"gallery_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        media_type = 'video' if filename.rsplit('.', 1)[1].lower() == 'mp4' else 'image'
        
        db = get_db()
        db.execute(
            'INSERT INTO gallery (tournament_id, title, description, media_type, filename) VALUES (?, ?, ?, ?, ?)',
            (tournament_id, title, description, media_type, filename)
        )
        db.commit()
        db.close()
        flash('Media uploaded to gallery!', 'success')
    else:
        flash('Invalid file type', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/gallery/<int:item_id>/delete', methods=['POST'])
def delete_gallery_item(item_id):
    if not is_admin():
        return redirect(url_for('admin_login'))
    db = get_db()
    item = db.execute('SELECT * FROM gallery WHERE id = ?', (item_id,)).fetchone()
    if item:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], item['filename'])
        if os.path.exists(filepath):
            os.remove(filepath)
        db.execute('DELETE FROM gallery WHERE id = ?', (item_id,))
        db.commit()
    db.close()
    flash('Gallery item removed!', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
