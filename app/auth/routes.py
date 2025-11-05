# app/auth/routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from app.models import User, Badge, UserBadge 
from app import db

# Creiamo il Blueprint
auth = Blueprint('auth', __name__)

# Funzione helper per i badge (potrebbe stare in app/utils.py in futuro)
def award_badge_if_earned(user, badge_name):
    badge = Badge.query.filter_by(name=badge_name).first()
    if not badge:
        if badge_name == "Nuovo Atleta":
            badge = Badge(name="Nuovo Atleta", description="Registrazione avvenuta con successo!", image_url="badge_new_athlete.png")
            db.session.add(badge)
            db.session.commit()
        else:
            return # Non crea altri badge al volo
    
    if badge and not UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
        user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
        db.session.add(user_badge)
        db.session.commit()
        flash(f'Congratulazioni! Hai ottenuto il badge: "{badge.name}"!', 'info')

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        # AGGIUNTO: Recupera la città dal form
        city = request.form.get('city') 
        accept_privacy = request.form.get('accept_privacy')

        if not accept_privacy:
            flash('Devi accettare la Privacy Policy e la Cookie Policy per registrarti.', 'danger')
            return redirect(url_for('auth.register'))

        # ... (validazioni per username, email, password) ...

        # Quando crei il nuovo utente, includi la città
        new_user = User(username=username, email=email, city=city) # La città viene passata qui
        new_user.set_password(password)
        db.session.add(new_user)
        
        try:
            db.session.commit()
            award_badge_if_earned(new_user, "Nuovo Atleta")
            flash('Registrazione avvenuta con successo! Effettua il login.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Si è verificato un errore durante la registrazione: {e}', 'danger')
            return redirect(url_for('auth.register'))
        
    # MODIFICA AL TEMPLATE: Passa la variabile 'city' se vuoi precompilarla o gestirla
    return render_template('register.html', is_homepage=False, city_value=request.form.get('city') if request.method == 'POST' else None)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            flash('Login avvenuto con successo!', 'success')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('Login fallito. Controlla username e password.', 'danger')
    return render_template('login.html', is_homepage=False)

@auth.route('/logout')
def logout():
    logout_user()
    flash('Sei stato disconnesso.', 'info')
    return redirect(url_for('main.index'))