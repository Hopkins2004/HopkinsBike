"""Authentication blueprint: register, login, logout, and the login/register pages."""
from sqlite3 import IntegrityError

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db

bp = Blueprint('auth', __name__)


@bp.route('/register', methods=['POST'])
def f_register():
    """Claude_f_register: create user with username and password, no email verification required"""
    mail = request.form['email']
    password = request.form['password']
    hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (email, password, status, credit, verified) VALUES (?, ?, ?, ?, ?)",
                (mail, hashed_password, 'user', 100, 1),
            )
        flash('Registration successful!', 'success')
        return redirect(url_for('auth.go_to_login'))
    except IntegrityError:
        flash('Username already in use!', 'error')
        return redirect(url_for('auth.go_to_login'))


@bp.route('/login', methods=['POST'])
def f_login():
    """Claude_f_login: verify credentials and start a session, else flash an error."""
    mail = request.form['email']
    password = request.form['password']

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email=?", (mail,))
        user = cursor.fetchone()

    if user and check_password_hash(user[2], password):
        session['username'] = user[1]
        flash('Bienvenue ' + user[1] + ' !', 'success')
        return redirect(url_for('activities.f_history'))
    else:
        flash('Invalid username or password', 'error')
        return redirect(url_for('auth.go_to_login'))


@bp.route('/logout')
def f_logout():
    """Claude_f_logout: clear the session and return to the home page."""
    del session['username']
    flash('Logged out', 'error')
    return (redirect(url_for('pages.f_home')))


@bp.route('/login')
def go_to_login():
    """Claude_go_to_login: render the login page."""
    return render_template('login_page.html')


@bp.route('/register')
def go_to_register():
    """Claude_go_to_register: render the registration page."""
    return render_template('register.html')
