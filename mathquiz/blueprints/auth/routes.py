# blueprints/auth/routes.py

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models.db import db_query_one, db_query_all, db_execute
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/")
def index():
    return render_template("index.html")

@auth_bp.route('/login_teacher', methods=['GET', 'POST'])
def login_teacher():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        row = db_query_one('SELECT password FROM teachers WHERE username=:u', {'u': username})
        if row and check_password_hash(row[0], password):
            session.clear()
            session['username'] = username
            session['role'] = 'teacher'
            flash("Login geslaagd!", "success")
            return redirect(url_for('teacher.dashboard'))
        flash("Login mislukt! Verkeerde gebruikersnaam of wachtwoord.", "danger")
        return redirect(url_for('auth.login_teacher'))
    return render_template('login_teacher.html')


@auth_bp.route('/register_teacher', methods=['GET', 'POST'])
def register_teacher():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            db_execute('''
                INSERT INTO teachers (username, created_at, password)
                VALUES (:u, NOW(), :p)
            ''', {
                'u': username,
                'p': generate_password_hash(password)
            })
        except Exception:
            flash("Registratie mislukt! Gebruikersnaam al in gebruik.", "danger")
            return redirect(url_for('auth.register_teacher'))

        flash("Registratie geslaagd!", "success")
        return redirect(url_for('auth.login_teacher'))

    return render_template('register_teacher.html')


@auth_bp.route('/login_group', methods=['GET', 'POST'])
def login_group():
    if request.method == 'POST':
        code = request.form['activation_code'].strip().upper()
        return redirect(url_for('auth.login_group_students', code=code))

    return render_template('login_group.html')


@auth_bp.route('/login_group/<code>', methods=['GET', 'POST'])
def login_group_students(code):
    grp = db_query_one('SELECT id, teacher_id FROM `groups` WHERE activation_code=:c', {'c': code})
    if not grp:
        flash("Ongeldige activatiecode!", "danger")
        return redirect(url_for('auth.login_group'))

    group_id, teacher_id = grp

    if request.method == 'POST':
        username = request.form['username']
        pin = request.form.get('pin', '').strip()
        row = db_query_one('''
            SELECT id FROM students
            WHERE username=:u AND group_id=:g AND pin=:p
            ''', {'u': username, 'g': group_id, 'p': pin})
        if not row:
            flash("Inloggen mislukt! Gebruiker niet in deze groep of verkeerde pincode ingevoerd!", "danger")
            return redirect(url_for('auth.login_group_students', code=code))

        session.clear()
        session['username'] = username
        session['role'] = 'student'
        session['student_id'] = row[0]
        flash("Inloggen geslaagd!", "success")
        demo = db_query_one('SELECT demo_seen FROM students WHERE id=:u', {'u': row[0]})
        demo_seen = int(demo[0]) if demo and demo[0] is not None else 0
        if demo_seen == 0:
            return redirect(url_for('student.demo_start'))

        return redirect(url_for('student.select_exercise'))

    students = [s[0] for s in db_query_all(
        'SELECT username FROM students WHERE group_id=:g ORDER BY username',
        {'g': group_id}
    )]

    return render_template('login_group_students.html', students=students, code=code)
