# app/main/routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app,request, Blueprint
import requests
from flask_login import login_required, current_user
from app.models import User, Route, Activity, ActivityLike, Challenge, Comment, Like, RouteRecord, Badge, UserBadge, Notification, ChallengeInvitation, Bet, Post, PostComment, PostLike, Tag ,post_tags, Group,Event
from app import db
from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime
import json
import gpxpy
import uuid
import os
from decimal import Decimal, InvalidOperation
from shapely.geometry import LineString, Point
from math import radians, sin, cos, sqrt, atan2
from werkzeug.utils import secure_filename # Utile per gestire i nomi dei file
from flask_wtf.csrf import validate_csrf, CSRFError # Importa per la validazione manuale
import traceback  # ⚠️ AGGIUNGI QUESTO IMPORT
from app import csrf  # <-- IMPORT CORRETTO
import json
from .services import get_unified_feed_items
import re # <-- Aggiungi questo import all'inizio del file
from .onboarding import complete_onboarding_step, get_onboarding_status
from .gamification import add_prestige, TITLES, create_bet_notification # <-- Assicurati che sia così
import random
from app import csrf
from flask_wtf.csrf import validate_csrf # Aggiungi questo import
from wtforms import ValidationError
# All'inizio di routes.py
from .gamification import close_expired_challenges
from datetime import datetime, timedelta
main = Blueprint('main', __name__)

# --- Funzioni Helper ---

def calculate_distance_meters(lat1, lon1, lat2, lon2):
    R = 6371000
    lat1_rad, lon1_rad, lat2_rad, lon2_rad = map(radians, [lat1, lon1, lat2, lon2])
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def create_geojson_linestring_buffer(geojson_linestring_coords, buffer_distance_meters):
    if not geojson_linestring_coords or len(geojson_linestring_coords) < 2:
        return None
    coords_shapely = [(p[0], p[1]) for p in geojson_linestring_coords]
    line = LineString(coords_shapely)
    buffer_in_degrees = buffer_distance_meters / (111.32 * 1000)
    return line.buffer(buffer_in_degrees)
    
def award_badge_if_earned(user, badge_name):
    # Questa funzione potrebbe aver bisogno di 'app.app_context()' se usata fuori da una request,
    # ma qui dentro va bene così.
    badge = Badge.query.filter_by(name=badge_name).first()
    if not badge:
        if badge_name == "Nuovo Atleta":
            badge = Badge(name="Nuovo Atleta", description="Registrazione avvenuta con successo!", image_url="badge_new_athlete.png")
        elif badge_name == "Primo Percorso":
            badge = Badge(name="Primo Percorso", description="Hai creato il tuo primo percorso!", image_url="badge_first_route.png")
        elif badge_name == "Prima Attività":
            badge = Badge(name="Prima Attività", description="Hai registrato la tua prima attività!", image_url="badge_first_activity.png")
        elif badge_name == "Re/Regina del Percorso":
            badge = Badge(name="Re/Regina del Percorso", description="Hai stabilito un nuovo record di velocità su un percorso!", image_url="badge_king_queen.png")
        
        if badge:
            db.session.add(badge)
            db.session.commit()
        else:
            return False

    if badge and not UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
        user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
        db.session.add(user_badge)
        
        # --- NUOVO CODICE AGGIUNTO QUI ---
        # Creiamo un post automatico per celebrare il nuovo badge!
        badge_post_content = f"🏅 Badge Sbloccato! {user.username} ha ottenuto il badge: '{badge.name}'!"

        badge_post = Post(
            user_id=user.id, # Il post è attribuito all'utente che ha ottenuto il badge
            content=badge_post_content,
            post_category='system_badge', # La nostra nuova categoria speciale!
            post_type='text'
        )
        add_prestige(user, 'get_badge')
        
        db.session.commit() # Questo salverà sia UserBadge che il nuovo Post
        flash(f'Congratulazioni! Hai ottenuto il badge: "{badge.name}"!', 'info')
        return True
    return False

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@main.route('/')
def index():
    user_city = current_user.city if current_user.is_authenticated else None
    
    # Inizializziamo le variabili che dipendono dal login
    # Inizializziamo tutte le variabili che dipendono dal login
    community_items, has_next_feed_page = [], False
    upcoming_events, show_onboarding, onboarding_status = [], False, {}
    recent_challenges_in_city = []

    if current_user.is_authenticated:
        # --- SE L'UTENTE È LOGGATO, CARICHIAMO I DATI DELLA SUA DASHBOARD ---
        
        # 1. Feed personalizzato
        community_items, has_next_feed_page = get_unified_feed_items(user=current_user, page=1, per_page=5)
        
        # 2. Onboarding
        status, is_complete = get_onboarding_status(current_user)
        if not is_complete:
            show_onboarding = True
            onboarding_status = status
            
        # 3. Eventi dei gruppi
        now = datetime.utcnow()
        joined_group_ids = [g.id for g in current_user.joined_groups]
        if joined_group_ids:
            upcoming_events = Event.query.filter(
                Event.group_id.in_(joined_group_ids),
                Event.event_time >= now
            ).order_by(Event.event_time.asc()).limit(3).all()

        # 4. NUOVA POSIZIONE: Sfide recenti nella città dell'utente
        if user_city:
            print(f"\n--- DEBUG: Cerco sfide per la città: '{user_city}' ---")
            
            # Query più flessibile per il debug (ignora maiuscole/minuscole e scommesse)
            challenges_in_city_query = db.session.query(Challenge).join(Route).options(
                joinedload(Challenge.route_info) # <-- AGGIUNGI QUESTO
            ).filter(
                func.lower(Route.classic_city) == func.lower(user_city),
                Challenge.end_date >= datetime.utcnow(),
                Challenge.is_active == True
            ).order_by(Challenge.start_date.asc()).limit(3).all()
            
            print(f"Trovate {len(challenges_in_city_query)} sfide attive in questa città.")
            recent_challenges_in_city = challenges_in_city_query
        else:
            print("\n--- DEBUG: L'utente è loggato ma non ha una città nel profilo per filtrare le sfide. ---")
            
    else:
        # --- SE L'UTENTE NON È LOGGATO, CARICHIAMO IL FEED PUBBLICO ---
        community_items, has_next_feed_page = get_unified_feed_items(user=None, page=1, per_page=5)

    # --- DATI SEMPRE PUBBLICI ---
    top_users_data = (
        db.session.query(User, func.sum(Activity.distance).label('total_distance'))
        .join(Activity).group_by(User.id)
        .order_by(func.sum(Activity.distance).desc()).limit(5).all()
    )
    top_users = [{'user': user, 'total_distance': total_distance or 0} for user, total_distance in top_users_data]

    # ===============================================================
    # CALCOLA LE STATISTICHE DEL SITO
    # ===============================================================
    # Sostituisci i modelli con i nomi corretti se sono diversi
    # (es. Activity, Route, etc.)
    site_stats = {
        'total_users': db.session.query(User).count(),
        'total_posts': db.session.query(Post).count(),
        'total_activities': db.session.query(Activity).count() if 'Activity' in globals() else 0, # Esempio
        'total_routes': db.session.query(Route).count() if 'Route' in globals() else 0 # Esempio
    }
        
    # --- PASSAGGIO DATI AL TEMPLATE ---
    return render_template("index.html", 
                        user_city=user_city, 
                        is_homepage=True, 
                        recent_challenges_in_city=recent_challenges_in_city,
                        top_users=top_users,
                        community_items=community_items, 
                        has_next_feed_page=has_next_feed_page,
                        show_onboarding=show_onboarding,
                        onboarding_status=onboarding_status,
                        upcoming_events=upcoming_events,
                        TITLES=TITLES,
                        site_stats=site_stats, Comment=Comment,PostComment=PostComment,
                        now=datetime.utcnow()
                        )


@main.route('/privacy')
def privacy_policy():
    return render_template('privacy.html')

@main.route('/cookie_policy')
def cookie_policy():
    return render_template('cookie_policy.html')

@main.route("/api/search_city")
def search_city():
    q = request.args.get("q")
    if not q:
        return jsonify([])

    try:
        res = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 5},
            headers={"User-Agent": "StreetSportApp/1.0 (leopoldo@example.com)"}
        )
        res.raise_for_status()
        return jsonify(res.json())
    except requests.RequestException as e:
        print("❌ Errore chiamata Nominatim:", e)
        return jsonify({"error": "Nominatim non disponibile"}), 503
    

@main.route('/feed')
@login_required
def feed():
    page = request.args.get('page', 1, type=int)
    activities_query = current_user.followed_posts().union(current_user.activities).order_by(Activity.created_at.desc())
    pagination = activities_query.options(
        joinedload(Activity.user_activity),
        joinedload(Activity.route_activity),
        joinedload(Activity.challenge)
    ).paginate(page=page, per_page=10, error_out=False)
    activities_on_page = pagination.items
    # NUOVA RIGA in feed
    return render_template('feed.html', activities=activities_on_page, pagination=pagination, ActivityLike=ActivityLike, is_homepage=False)

@main.route('/user/<int:user_id>')
def user_profile(user_id):
    user = User.query.get_or_404(user_id)
    total_distance = db.session.query(func.sum(Activity.distance)).filter_by(user_id=user.id).scalar() or 0.0
    total_activities = user.activities.count()
    total_routes_created = user.routes.count()
    total_records_held = user.route_records.count()
    followers_count = user.followers.count()
    followed_count = user.followed.count()
    user_activities = user.activities.order_by(Activity.created_at.desc()).limit(10).all()
    
    # Nuove query per le scommesse
    bets_won = Bet.query.filter_by(winner_id=user_id).options(
        db.joinedload(Bet.loser)
    ).order_by(Bet.status.asc(), Bet.created_at.desc()).all()  # Prima pending, poi paid
    
    bets_lost = Bet.query.filter_by(loser_id=user_id).options(
        db.joinedload(Bet.winner)
    ).order_by(Bet.status.asc(), Bet.created_at.desc()).all()
    user_posts = Post.query.filter_by(user_id=user.id, group_id=None).order_by(Post.created_at.desc()).limit(10).all()
    user_groups = user.joined_groups.all()

    return render_template("profile.html",
                           user=user,
                           user_activities=user_activities,
                           total_distance=total_distance,
                           total_activities=total_activities,
                           total_routes_created=total_routes_created,
                           total_records_held=total_records_held,
                           followers_count=followers_count,
                           followed_count=followed_count,
                           bets_won=bets_won,
                           bets_lost=bets_lost,
                           is_homepage=False,
                           TITLES=TITLES,
                           user_posts=user_posts,
                           user_groups=user_groups,
                           Route=Route)


@main.route('/user/edit', methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        new_username = request.form.get("username")
        new_email = request.form.get("email")
        new_password = request.form.get("password")
        new_city = request.form.get("city")
        new_surname = request.form.get("surname") # AGGIUNTO: Recupera il cognome dal form
        
        if 'profile_image' in request.files and request.files['profile_image'].filename != '':
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                filename = str(uuid.uuid4()) + os.path.splitext(file.filename)[1]
                filepath = os.path.join(current_app.config['PROFILE_PICS_FOLDER'], filename)
                file.save(filepath)
                current_user.profile_image = filename
            else:
                flash('Formato immagine non valido.', 'danger')
                return redirect(url_for('main.edit_profile'))

        if new_username and new_username != current_user.username:
            if User.query.filter(User.username == new_username, User.id != current_user.id).first():
                flash('Username già in uso.', 'danger')
                return redirect(url_for('main.edit_profile'))
            current_user.username = new_username
        
        if new_email and new_email != current_user.email:
            if User.query.filter(User.email == new_email, User.id != current_user.id).first():
                flash('Email già registrata.', 'danger')
                return redirect(url_for('main.edit_profile'))
            current_user.email = new_email
        
        if new_password:
            # Aggiungi qui la validazione per la lunghezza minima della password, se non l'hai già fatto
            if len(new_password) < 6:
                flash('La nuova password deve avere almeno 6 caratteri.', 'danger')
                return redirect(url_for('main.edit_profile'))
            current_user.set_password(new_password)
        
        if new_city is not None:
            current_user.city = new_city

        # AGGIUNTO: Aggiorna il cognome
        if new_surname is not None: # Controlla se il campo è stato inviato (anche se vuoto)
            current_user.surname = new_surname

        # Se l'utente ha aggiunto una foto profilo e una città, consideriamo il profilo completo
        # Potresti voler aggiungere anche il cognome qui se lo ritieni parte del completamento del profilo
        if current_user.profile_image != 'default.png' and current_user.city:
            pass # <-- AGGIUNGI QUESTA RIGA indentata correttamente
            # complete_onboarding_step(current_user, 'profile_complete') # rimosso il commento se la funzione esiste

            # Esempio di come potresti definire complete_onboarding_step se non ce l'hai:
            # if current_user.onboarding_steps is None:
            #     current_user.onboarding_steps = {}
            # current_user.onboarding_steps['profile_complete'] = True


        try:
            db.session.commit()
            flash('Profilo aggiornato con successo!', 'success')
            return redirect(url_for('main.user_profile', user_id=current_user.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Si è verificato un errore durante l\'aggiornamento: {e}', 'danger')
            return redirect(url_for('main.edit_profile'))


    return render_template("edit_profile.html", user=current_user, is_homepage=False)

@main.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user == current_user:
        flash('Non puoi seguire te stesso!', 'warning')
        return redirect(url_for('main.user_profile', user_id=user.id))
    current_user.follow(user)

    # --- NUOVA LOGICA NOTIFICHE ---
    # Crea una notifica solo se non è già stata creata (evita duplicati)
    existing_notification = Notification.query.filter_by(
        recipient_id=user.id, 
        actor_id=current_user.id, 
        action='new_follower'
    ).first()
    
    if not existing_notification:
        notification = Notification(
            recipient_id=user.id,           # La notifica è per l'utente che viene seguito
            actor_id=current_user.id,       # L'attore è l'utente che ha appena cliccato "segui"
            action='new_follower'
        )
        db.session.add(notification)
    # --- FINE NUOVA LOGICA ---
    
    db.session.commit()
    # Controlliamo se ha raggiunto la soglia
    if current_user.followed.count() >= 3:
        complete_onboarding_step(current_user, 'followed_users')
        
    flash(f'Ora segui {username}!', 'success')

    return redirect(url_for('main.user_profile', user_id=user.id))
    
@main.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first_or_404()
    if user == current_user:
        flash('Non puoi smettere di seguire te stesso!', 'warning')
        return redirect(url_for('main.user_profile', user_id=user.id))
    current_user.unfollow(user)
    db.session.commit()
    flash(f'Non segui più {username}.', 'info')
    return redirect(url_for('main.user_profile', user_id=user.id))

@main.route('/explore/users')
@login_required
def explore_users():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '')
    query = User.query
    if search_query:
        query = query.filter(User.username.ilike(f'%{search_query}%'))
    query = query.filter(User.id != current_user.id)
    pagination = query.order_by(User.username.asc()).paginate(page=page, per_page=15, error_out=False)
    # NUOVA RIGA in explore_users
    return render_template('explore_users.html', users=pagination.items, pagination=pagination, search_query=search_query, is_homepage=False)

# --- Route per Percorsi (Routes) ---

@main.route("/routes/new", methods=["GET","POST"])
@login_required
def create_route():
    if request.method == "POST":
        name = request.form["name"]
        description = request.form.get("description")
        activity_type = request.form.get("activity_type")
        coords_geojson_str = None
        distance_km = None

        if 'gpx_file' in request.files and request.files['gpx_file'].filename != '':
            gpx_file = request.files['gpx_file']
            try:
                gpx_data = gpxpy.parse(gpx_file.stream)
                points = [ [p.longitude, p.latitude] for t in gpx_data.tracks for s in t.segments for p in s.points ]
                if points:
                    coords_geojson_str = json.dumps({"type": "Feature", "geometry": {"type": "LineString", "coordinates": points}, "properties": {}})
                    distance_km = gpx_data.length_3d() / 1000 if gpx_data.length_3d() else gpx_data.length_2d() / 1000
                else:
                    flash('Il file GPX non contiene dati di percorso validi.', 'danger')
                    return redirect(url_for("main.create_route"))
            except Exception as e:
                flash(f'Errore nella lettura del file GPX: {e}', 'danger')
                return redirect(url_for("main.create_route"))
        
        elif "coordinates" in request.form and request.form["coordinates"]:
            coords_geojson_str = request.form["coordinates"]
            try:
                geojson_obj = json.loads(coords_geojson_str)
                line_coords = geojson_obj['geometry']['coordinates']
                total_distance_meters = sum(calculate_distance_meters(line_coords[i][1], line_coords[i][0], line_coords[i+1][1], line_coords[i+1][0]) for i in range(len(line_coords) - 1))
                distance_km = total_distance_meters / 1000.0
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                distance_km = None

        if not coords_geojson_str:
            flash('Devi disegnare un percorso sulla mappa o caricare un file GPX.', 'danger')
            return redirect(url_for("main.create_route"))

        new_route = Route(name=name, description=description, activity_type=activity_type, coordinates=coords_geojson_str, created_by=current_user.id, distance_km=distance_km)
        db.session.add(new_route)
        add_prestige(current_user, 'new_route')
        db.session.commit()
        
        flash('Percorso creato con successo!', 'success')
        return redirect(url_for("main.index"))
    return render_template('new_route.html', is_homepage=False)

@main.route("/route/<int:route_id>", methods=["GET", "POST"])
def route_detail(route_id):
    route = Route.query.options(joinedload(Route.creator)).get_or_404(route_id)
    
    # DEBUG: Verifica i dati del percorso
    print(f"=== DEBUG PERCORSO {route_id} ===")
    print(f"Nome: {route.name}")
    print(f"Descrizione: {route.description}")
    print(f"Tipo attività: {route.activity_type}")
    print(f"Creato da: {route.creator.username if route.creator else 'N/A'}")
    print(f"Distanza: {route.distance_km}")
    print(f"Coordinate: {route.coordinates[:100] if route.coordinates else 'Nessuna'}...")  # Solo primi 100 caratteri
    print(f"Difficoltà: {route.difficulty}")
    print(f"Dislivello: {route.elevation_gain}")
    print("================================")
    
    # Gestione corretta delle coordinate GeoJSON
    route_geojson_data = None
    if route.coordinates:
        try:
            # Se le coordinate sono già in formato JSON, usale direttamente
            if isinstance(route.coordinates, str) and route.coordinates.strip().startswith('{'):
                geojson_obj = json.loads(route.coordinates)
                print("✅ Coordinate già in formato GeoJSON")
            else:
                # Altrimenti, converti le coordinate in GeoJSON
                print("🔄 Conversione coordinate in GeoJSON...")
                coords_list = [list(map(float, coord.split(','))) for coord in route.coordinates.split(';')]
                geojson_obj = {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords_list
                    },
                    "properties": {}
                }
            
            # Verifica che la struttura GeoJSON sia corretta
            if 'geometry' in geojson_obj and 'coordinates' in geojson_obj['geometry']:
                route_geojson_data = json.dumps(geojson_obj)
                print("✅ GeoJSON creato correttamente")
            else:
                print("❌ Struttura GeoJSON non valida")
                route_geojson_data = "{}"
                
        except Exception as e:
            print(f"❌ Errore conversione coordinate: {e}")
            route_geojson_data = "{}"
    else:
        route_geojson_data = "{}"
        print("ℹ️ Nessuna coordinata disponibile")

    challenges_for_route = Challenge.query.filter(
        Challenge.route_id == route.id,
        Challenge.end_date >= datetime.utcnow()
    ).order_by(Challenge.start_date).all()

    # Query per le attività top
    top_5_activities_for_route = db.session.query(
        Activity, User
    ).join(
        User, Activity.user_id == User.id
    ).filter(
        Activity.route_id == route_id
    ).order_by(
        Activity.duration.asc()
    ).limit(5).all()

    # Prepara i dati per i commenti con like info
    comments_with_like_info = []
    for comment in route.comments.order_by(Comment.created_at.desc()).all():
        like_count = comment.likes.count()
        has_liked = False
        if current_user.is_authenticated:
            has_liked = comment.likes.filter_by(user_id=current_user.id).first() is not None
        comments_with_like_info.append({
            'comment': comment,
            'like_count': like_count,
            'has_liked': has_liked
        })

    if request.method == "POST":
        if not current_user.is_authenticated:
            flash('Devi essere loggato per commentare.', 'danger')
            return redirect(url_for('auth.login', next=request.url))
        
        comment_content = request.form.get("comment_content")
        if not comment_content:
            flash('Il commento non può essere vuoto.', 'danger')
            return redirect(url_for('main.route_detail', route_id=route.id))
        
        new_comment = Comment(user_id=current_user.id, route_id=route.id, content=comment_content)
        db.session.add(new_comment)
        db.session.commit()
        flash('Commento aggiunto con successo!', 'success')
        return redirect(url_for('main.route_detail', route_id=route.id))

    return render_template(
        'route_detail.html',
        route=route,
        route_geojson_data=route_geojson_data,
        challenges_for_route=challenges_for_route,
        top_5_activities_for_route=top_5_activities_for_route,
        comments_with_like_info=comments_with_like_info
    )

@main.route("/comment/<int:comment_id>/like", methods=["POST"])
@login_required
def toggle_like(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    like = Like.query.filter_by(user_id=current_user.id, comment_id=comment_id).first()
    if like:
        db.session.delete(like)
        action = "unliked"
    else:
        new_like = Like(user_id=current_user.id, comment_id=comment_id)
        db.session.add(new_like)
        action = "liked"
    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'action': action,
        'new_like_count': comment.likes.count(),  # <--- usa .count()
        'comment_id': comment_id
    })


# --- Route per Sfide (Challenges) e Attività (Activities) ---

# In app/main/routes.py, nella funzione create_challenge() per il metodo POST

@main.route("/challenges/new", methods=["GET", "POST"])
@login_required
def create_challenge():
    if request.method == "POST":
        challenge_name = request.form["name"]
        route_id_str = request.form.get("route_id")
        start_date_str = request.form["start_date"]
        end_date_str = request.form["end_date"]
        
        challenge_type = request.form.get("challenge_type", "open")
        bet_type = request.form.get("bet_type", "none")
        custom_bet = request.form.get("custom_bet", "")
        invited_friends = request.form.getlist("invited_friends")
        
        # Validazioni (invariate)
        if not route_id_str:
            flash('Devi selezionare un percorso per creare la sfida.', 'warning')
            return redirect(url_for('main.create_challenge'))
        
        try:
            route_id = int(route_id_str)
            route = Route.query.get(route_id)
            if not route:
                flash(f'Il percorso selezionato non esiste.', 'danger')
                return redirect(url_for('main.create_challenge'))
        except (ValueError, TypeError):
            flash('ID del percorso non valido.', 'danger')
            return redirect(url_for('main.create_challenge'))

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            flash('Formato data non valido.', 'danger')
            return redirect(url_for('main.create_challenge'))
        
        if start_date >= end_date:
            flash('La data di inizio deve essere precedente alla data di fine.', 'danger')
            return redirect(url_for('main.create_challenge'))

        # La validazione per le sfide chiuse rimane
        if challenge_type == "closed" and not invited_friends:
            flash('Per le sfide chiuse devi invitare almeno un amico.', 'danger')
            return redirect(url_for('main.create_challenge'))

        bet_value = get_bet_value(bet_type, custom_bet)
        
        new_challenge = Challenge(
            name=challenge_name, 
            route_id=route_id,
            start_date=start_date, 
            end_date=end_date, 
            created_by=current_user.id,
            challenge_type=challenge_type,
            bet_type=bet_type,
            custom_bet=custom_bet,
            bet_value=bet_value,
            is_active=True # Assicuriamoci che sia sempre True alla creazione
        )
        
        try:
            db.session.add(new_challenge)
            db.session.flush()

            # --- INIZIO BLOCCO LOGICA MODIFICATO ---
            # Questa logica ora si attiva se ci sono amici invitati,
            # indipendentemente dal tipo di sfida.
            if invited_friends:
                for friend_id in invited_friends:
                    try:
                        friend_id_int = int(friend_id)
                        friend = User.query.get(friend_id_int)
                        if friend:
                            # 1. Se la sfida è CHIUSA, creiamo un record di invito formale
                            if challenge_type == "closed":
                                invitation = ChallengeInvitation(
                                    challenge_id=new_challenge.id,
                                    invited_user_id=friend_id_int
                                )
                                db.session.add(invitation)
                            
                            # 2. IN OGNI CASO (aperta o chiusa), inviamo una notifica
                            notification = Notification(
                                recipient_id=friend_id_int,
                                actor_id=current_user.id,
                                action='challenge_invitation',
                                object_id=new_challenge.id,
                                object_type='challenge'
                            )
                            db.session.add(notification)
                            
                    except (ValueError, TypeError):
                        continue
            # --- FINE BLOCCO LOGICA MODIFICATO ---
            
            db.session.commit()
            
            # Messaggio di successo personalizzato
            success_message = f'Sfida "{challenge_name}" creata con successo!'
            if invited_friends:
                if challenge_type == "closed":
                    success_message += f' {len(invited_friends)} amici invitati.'
                else: # Sfida aperta
                    success_message += f' {len(invited_friends)} amici avvisati.'
            
            flash(success_message, 'success')
            return redirect(url_for('main.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Errore durante la creazione della sfida: {str(e)}', 'danger')
            return redirect(url_for('main.create_challenge'))
        
    # Metodo GET (invariato)
    routes = Route.query.order_by(Route.name).all()
    return render_template("create_challenge.html", routes=routes, is_homepage=False)

# === FUNZIONE HELPER PER LE SCOMMESSE ===
def get_bet_value(bet_type, custom_bet):
    """Restituisce il valore formattato della scommessa"""
    bet_values = {
        'none': 'Nessuna scommessa',
        'beer': '🍺 1 Birra',
        'dinner': '🍝 1 Cena', 
        'coffee': '☕ 1 Caffè',
        'custom': custom_bet if custom_bet else 'Scommessa personalizzata'
    }
    return bet_values.get(bet_type, 'Nessuna scommessa')


# In app/main/routes.py

@main.route("/activities/record", methods=["GET", "POST"])
@login_required
def record_activity():
    if request.method == "POST":
        print("\n--- DEBUG: Inizio processamento attività POST ---")
        
        selected_challenge_id = request.form.get("challenge_id", type=int)
        selected_route_id = request.form.get("route_id", type=int)
        activity_type = request.form.get("activity_type")

        redirect_params = {
            'pre_selected_route_id': selected_route_id,
            'pre_selected_challenge_id': selected_challenge_id
        }

        if not selected_challenge_id and not selected_route_id:
            flash('Devi selezionare un percorso o una sfida per registrare l\'attività.', 'danger')
            return redirect(url_for('main.record_activity'))

        target_route = None
        target_challenge = None

        if selected_challenge_id:
            target_challenge = Challenge.query.get(selected_challenge_id)
            if not target_challenge:
                flash('Sfida selezionata non valida.', 'danger')
                return redirect(url_for('main.record_activity', **redirect_params))
            target_route = target_challenge.route_info
        elif selected_route_id:
            target_route = Route.query.get(selected_route_id)
            if not target_route:
                flash('Percorso selezionato non valido.', 'danger')
                return redirect(url_for('main.record_activity', **redirect_params))
        
        if not target_route:
            flash('Impossibile determinare il percorso target per l\'attività.', 'danger')
            return redirect(url_for('main.record_activity', **redirect_params))

        # ==========================================================
        # --- NUOVO BLOCCO DI SICUREZZA PER LE SFIDE PRIVATE ---
        # ==========================================================
        if target_challenge and target_challenge.challenge_type == 'closed':
            # Controlla se l'utente ha il permesso di partecipare
            
            is_creator = target_challenge.created_by == current_user.id
            
            # Controlla se l'utente è stato invitato E ha accettato l'invito
            invitation = ChallengeInvitation.query.filter_by(
                challenge_id=target_challenge.id,
                invited_user_id=current_user.id
            ).first()
            
            is_accepted_invitee = invitation and invitation.status == 'accepted'

            # Se l'utente non è né il creatore né un invitato che ha accettato...
            if not is_creator and not is_accepted_invitee:
                flash('Non sei autorizzato a partecipare a questa sfida privata.', 'danger')
                return redirect(url_for('main.challenges_list'))
        # ==========================================================
        # --- FINE BLOCCO DI SICUREZZA ---
        # ==========================================================

        gpx_file = request.files.get('gpx_file')
        if not gpx_file or gpx_file.filename == '':
            flash('Nessun file GPX selezionato.', 'danger')
            return redirect(url_for('main.record_activity', **redirect_params))
        
        try:
            gpx = gpxpy.parse(gpx_file.stream)
            
            activity_duration_seconds = gpx.get_duration() or 0
            activity_distance_meters = gpx.length_3d() if gpx.length_3d() else gpx.length_2d()
            activity_distance_km = activity_distance_meters / 1000.0
            activity_avg_speed = activity_distance_km / (activity_duration_seconds / 3600.0) if activity_duration_seconds > 0 else 0.0
            
            activity_geojson_coords_raw = [(p.longitude, p.latitude) for t in gpx.tracks for s in t.segments for p in s.points]
            
            if not activity_geojson_coords_raw:
                flash('Il file GPX non contiene dati di percorso validi.', 'danger')
                return redirect(url_for('main.record_activity', **redirect_params))

         
            # --- VALIDAZIONE DELLA DISTANZA ---
            expected_distance = Decimal(str(target_route.distance_km)) if target_route.distance_km is not None else Decimal(0)
            actual_distance = Decimal(str(activity_distance_km))
          

            distance_tolerance_percent = Decimal('0.05')
            is_valid_distance = False
            if expected_distance > 0:
                lower_bound = expected_distance * (1 - distance_tolerance_percent)
                upper_bound = expected_distance * (1 + distance_tolerance_percent)
               
                if lower_bound <= actual_distance <= upper_bound:
                    is_valid_distance = True
            elif actual_distance == 0 and expected_distance == 0:
                 is_valid_distance = True

            if not is_valid_distance:
               
                flash(f'La distanza dell\'attività non corrisponde al percorso selezionato (Prevista: ~{expected_distance:.2f} km, Registrata: {actual_distance:.2f} km).', 'danger')
                return redirect(url_for('main.record_activity', **redirect_params))
            
    
            
            # --- VALIDAZIONE GEOFENCING ---
            try:
                ref_route_geojson_obj = json.loads(target_route.coordinates)
                ref_route_coords_shapely = [(p[0], p[1]) for p in ref_route_geojson_obj['geometry']['coordinates']]
                geofence_buffer_meters = 50 
                geofence_polygon = create_geojson_linestring_buffer(ref_route_coords_shapely, geofence_buffer_meters)

                if geofence_polygon:
                    points_inside_geofence = sum(1 for lon, lat in activity_geojson_coords_raw if geofence_polygon.contains(Point(lon, lat)))
                    total_activity_points = len(activity_geojson_coords_raw)

                    if total_activity_points > 0:
                        geofence_match_threshold = 0.80
                        match_percentage = points_inside_geofence / total_activity_points
                        print(f"--- DEBUG: Punti nel geofence: {points_inside_geofence}/{total_activity_points} ({match_percentage:.2%}) ---")
                        
                        if match_percentage < geofence_match_threshold:
                            print("--- DEBUG: !!! VALIDAZIONE GEOFENCING FALLITA !!! ---")
                            flash(f'Il tracciato non segue abbastanza il percorso ({match_percentage:.0%} di corrispondenza).', 'danger')
                            return redirect(url_for('main.record_activity', **redirect_params))
                        
                        print("--- DEBUG: Validazione geofencing SUPERATA. ---")
                    else:
                        flash('Nessun punto GPS nel file di attività per la validazione.', 'danger')
                        return redirect(url_for('main.record_activity', **redirect_params))
                else:
                    flash('Errore nella creazione del geofence per il percorso.', 'danger')
                    return redirect(url_for('main.record_activity', **redirect_params))
            except Exception as e:
                print(f"--- DEBUG: !!! ERRORE CRITICO DURANTE GEOFENCING: {e} !!! ---")
                flash(f'Errore durante la validazione geofencing: {e}', 'danger')
                return redirect(url_for('main.record_activity', **redirect_params))

            print("--- DEBUG: Tutte le validazioni superate. Procedo al salvataggio. ---")
            
            activity_gps_track_geojson = json.dumps({"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[p[0], p[1]] for p in activity_geojson_coords_raw]}, "properties": {}})

            new_activity = Activity(
                user_id=current_user.id, route_id=target_route.id,
                challenge_id=target_challenge.id if target_challenge else None,
                activity_type=activity_type, gps_track=activity_gps_track_geojson,
                duration=int(activity_duration_seconds), avg_speed=float(activity_avg_speed),
                distance=float(activity_distance_km)
            )
            db.session.add(new_activity)
            add_prestige(current_user, 'new_activity')
            db.session.commit()

            current_record = RouteRecord.query.filter_by(route_id=target_route.id, activity_type=activity_type).order_by(RouteRecord.duration.asc()).first()
            # --- MODIFICA QUESTO BLOCCO ---
            if not current_record or new_activity.duration < current_record.duration:
                if current_record:
                    # Se c'era un record precedente, lo rimuoviamo
                    db.session.delete(current_record)
                
                # Creiamo il nuovo record
                new_record = RouteRecord(
                    route_id=target_route.id, 
                    user_id=current_user.id, 
                    activity_id=new_activity.id, 
                    activity_type=activity_type, 
                    duration=new_activity.duration
                )
                db.session.add(new_record)
                
                # --- NUOVO CODICE AGGIUNTO QUI ---
                # Creiamo un post automatico per celebrare il nuovo record!
                record_post_content = (
                    f"🏆 Nuovo Record! {current_user.username} ha conquistato il percorso '{target_route.name}' "
                    f"con un tempo eccezionale di {datetime.utcfromtimestamp(new_activity.duration).strftime('%H:%M:%S')}!"
                )

                record_post = Post(
                    user_id=current_user.id, # Il post è attribuito all'utente che ha fatto il record
                    content=record_post_content,
                    post_category='system_record', # La nostra nuova categoria speciale!
                    post_type='text' # È un post di solo testo
                )
                db.session.add(record_post)
                add_prestige(current_user, 'new_record')
                db.session.commit()
                award_badge_if_earned(current_user, "Re/Regina del Percorso")
            
            if Activity.query.filter_by(user_id=current_user.id).count() == 1:
                award_badge_if_earned(current_user, "Prima Attività")

            flash('Attività registrata con successo!', 'success')
            return redirect(url_for('main.index'))

        except Exception as e:
            print(f"--- DEBUG: !!! ERRORE CRITICO NEL TRY PRINCIPALE: {e} !!! ---")
            flash(f'Errore imprevisto durante l\'elaborazione del file GPX: {e}', 'danger')
            return redirect(url_for('main.record_activity', **redirect_params))

    # --- Logica GET ---
    pre_selected_route_id = request.args.get('route_id', type=int)
    pre_selected_challenge_id = request.args.get('challenge_id', type=int)
    challenges = Challenge.query.order_by(Challenge.name).all()
    # Esempio di come potresti passare routes serializzate, se necessario. Per ora passiamo gli oggetti
    routes = Route.query.order_by(Route.name).all()
    return render_template("record_activity.html",
                           challenges=challenges,
                           routes=routes,
                           pre_selected_route_id=pre_selected_route_id,
                           pre_selected_challenge_id=pre_selected_challenge_id,
                           is_homepage=False)



def parse_gps_to_geojson(gps_data_string):
    """
    Analizza una stringa di dati GPS da vari formati e la converte
    in un dizionario GeoJSON "LineString" valido.
    
    Gestisce:
    - GeoJSON Feature
    - GeoJSON LineString
    - Lista di Dizionari [{'lat': ..., 'lon': ...}]
    - Lista di Dizionari [{'lat': ..., 'lng': ...}]
    - Lista di Liste [[lon, lat]]
    - Lista Vuota []
    """
    if not gps_data_string:
        return None

    try:
        data = json.loads(gps_data_string)

        # CASO 1: Oggetto GeoJSON "Feature"
        if isinstance(data, dict) and data.get('type') == 'Feature':
            print("DEBUG PARSER :: Detected GPS format: GeoJSON Feature.")
            geometry = data.get('geometry')
            if isinstance(geometry, dict) and geometry.get('type') == 'LineString':
                return geometry
        
        # CASO 2: Oggetto GeoJSON "LineString"
        if isinstance(data, dict) and data.get('type') == 'LineString':
            print("DEBUG PARSER :: Detected GPS format: Pre-formatted GeoJSON LineString.")
            return data

        # CASO 3: I dati sono una lista
        if isinstance(data, list):
            if not data:
                print("DEBUG PARSER :: GPS track is an empty list.")
                return None

            first_point = data[0]

            # Sottocaso 3a: Lista di Dizionari
            if isinstance(first_point, dict) and 'lat' in first_point:
                # --- SOLUZIONE: Controlla se esiste 'lon' o 'lng' ---
                lon_key = None
                if 'lon' in first_point:
                    lon_key = 'lon'
                elif 'lng' in first_point:
                    lon_key = 'lng'
                # ----------------------------------------------------
                
                if lon_key:
                    print(f"DEBUG PARSER :: Detected format: List of Dictionaries (using key: '{lon_key}').")
                    coordinates = [[point[lon_key], point['lat']] for point in data]
                    return {"type": "LineString", "coordinates": coordinates}
            
            # Sottocaso 3b: Lista di Liste
            if isinstance(first_point, list) and len(first_point) >= 2:
                print("DEBUG PARSER :: Detected GPS format: List of Lists.")
                return {"type": "LineString", "coordinates": data}

        # Se nessun formato valido è stato riconosciuto
        print(f"Warning: Unknown or invalid GPS data format for data: {str(data)[:200]}...") # Tronca per non intasare i log
        return None

    except Exception as e:
        print(f"Error parsing GPS data string: {e}")
        return None
    
@main.route("/activity/<int:activity_id>")
def activity_detail(activity_id):
    activity = Activity.query.get_or_404(activity_id)
    
    print(f"\n=== DEBUG activity_detail (Activity ID: {activity.id}) ===")
    
    # --- GESTIONE GEOJSON DEL PERCORSO ---
    route_geojson_data = None
    if activity.route_activity and activity.route_activity.coordinates:
        try:
            route_geojson_data = json.loads(activity.route_activity.coordinates)
        except Exception as e:
            print(f"Error parsing route coordinates: {e}")
    
    # --- GESTIONE GEOJSON DELL'ATTIVITÀ ---
    print("Parsing activity GPS track...")
    activity_geojson_data = parse_gps_to_geojson(activity.gps_track)
    
    if activity_geojson_data:
        print(f"Successfully parsed GPS track. Coordinates count: {len(activity_geojson_data['coordinates'])}")
    else:
        print("Failed to parse GPS track.")
        
    print("=======================\n")
    
    # --- CORRETTA GESTIONE DELLA SFIDA ---
    challenge = Challenge.query.get(activity.challenge_id) if activity.challenge_id else None
    
    return render_template(
        "activity_detail.html",
        activity=activity, 
        user=activity.user_activity, 
        route=activity.route_activity,
        challenge=challenge,  # ✅ usa la variabile giusta
        activity_geojson_data=activity_geojson_data, 
        route_geojson_data=route_geojson_data, 
        is_homepage=False
    )

@main.route("/activities")
def all_activities():
    page = request.args.get('page', 1, type=int)
    pagination = Activity.query.options(joinedload(Activity.user_activity), joinedload(Activity.route_activity), joinedload(Activity.challenge)).order_by(Activity.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    # NUOVA RIGA in all_activities
    return render_template("all_activities.html", activities=pagination.items, pagination=pagination, is_homepage=False)

# --- Route per Classifiche (Leaderboards) ---

@main.route("/challenges/<int:challenge_id>/leaderboard")
def leaderboard(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    leaderboard_entries = db.session.query(Activity, User).join(User).filter(Activity.challenge_id == challenge_id).order_by(Activity.duration.asc()).all()
    # NUOVA RIGA in leaderboard
    return render_template("leaderboard.html", challenge=challenge, leaderboard_entries=leaderboard_entries, is_homepage=False)

@main.route("/challenges")
@login_required
def challenges_list():
    now = datetime.utcnow()
    
    # 1. Recupera le sfide aperte e attive
    active_challenges = Challenge.query.options(joinedload(Challenge.route_info)).filter(
        Challenge.challenge_type == 'open',
        Challenge.end_date >= now,
        Challenge.is_active == True
    ).order_by(Challenge.start_date.asc()).all()

    # 2. Recupera gli inviti in sospeso
    invited_challenges = Challenge.query.options(joinedload(Challenge.route_info)).join(ChallengeInvitation).filter(
        Challenge.challenge_type == 'closed',
        ChallengeInvitation.invited_user_id == current_user.id,
        ChallengeInvitation.status == 'pending'
    ).order_by(Challenge.created_at.desc()).all()

    # 3. Recupera le sfide create dall'utente
    my_challenges = Challenge.query.options(joinedload(Challenge.route_info)).filter_by(
        created_by=current_user.id
    ).order_by(Challenge.created_at.desc()).all()

    # 4. Recupera lo storico
    finished_challenges_pag = Challenge.query.options(joinedload(Challenge.route_info)).filter(
        Challenge.end_date < now
    ).order_by(Challenge.end_date.desc()).paginate(page=request.args.get('page', 1, type=int), per_page=10, error_out=False)

    return render_template("challenges_list.html", 
                           active_challenges=active_challenges, 
                           invited_challenges=invited_challenges,
                           my_challenges=my_challenges,
                           finished_challenges_pag=finished_challenges_pag, # Passiamo l'oggetto paginazione
                           now=now,
                           is_homepage=False)

@main.route("/leaderboards/total_distance")
def leaderboard_total_distance():
    results = (
        db.session.query(
            User.id,
            User.username,
            User.profile_image,
            func.sum(Activity.distance).label('total_distance')
        )
        .join(Activity)
        .group_by(User.id, User.username, User.profile_image)
        .order_by(func.sum(Activity.distance).desc())
        .limit(20)
        .all()
    )

    leaderboard_data = [
        {
            'id': id,
            'username': username,
            'profile_image': profile_image,
            'total_distance': total_distance or 0
        }
        for id, username, profile_image, total_distance in results
    ]

    return render_template(
        "leaderboard_total_distance.html",
        leaderboard_data=leaderboard_data,
        is_homepage=False
    )

@main.route("/leaderboards/most_routes")
def leaderboard_most_routes():
    results = (
        db.session.query(
            User.id,
            User.username,
            User.profile_image,
            func.count(Route.id).label('total_routes_created')
        )
        .join(Route, User.id == Route.created_by)
        .group_by(User.id, User.username, User.profile_image)
        .order_by(func.count(Route.id).desc())
        .limit(20)
        .all()
    )

    leaderboard_data = [
        {
            'id': id,
            'username': username,
            'profile_image': profile_image,
            'total_routes_created': total_routes_created or 0
        }
        for id, username, profile_image, total_routes_created in results
    ]

    return render_template(
        "leaderboard_most_routes.html",
        leaderboard_data=leaderboard_data,
        is_homepage=False
    )



# In app/main/routes.py

@main.route('/notifications')
@login_required
def notifications():
    """Notifiche con conteggio non lette"""
    user_notifications = current_user.notifications.order_by(Notification.timestamp.desc()).all()
    unread_count = Notification.query.filter_by(recipient_id=current_user.id, read=False).count()
    
    notification_messages = []
    
    for n in user_notifications:
        message = ""
        link = "#"  # Link di default sicuro
        icon = "🔔"
        bg_color = "bg-secondary"
        
        if n.action == 'new_follower':
            message = f"<strong>{n.actor.username}</strong> ha iniziato a seguirti."
            link = url_for('main.user_profile', user_id=n.actor_id)
            icon = "👥"
            bg_color = "bg-info"
        
        elif n.action == 'like_activity':
            activity = Activity.query.get(n.object_id)
            if activity and activity.route_activity:
                message = f"A <strong>{n.actor.username}</strong> piace la tua attività su <em>{activity.route_activity.name}</em>."
                link = url_for('main.activity_detail', activity_id=activity.id)
            else:
                message = f"A <strong>{n.actor.username}</strong> piace una tua attività che è stata rimossa."
            icon = "❤️"
            bg_color = "bg-danger"
        
        elif n.action == 'challenge_invitation':
            challenge = Challenge.query.get(n.object_id)
            if challenge:
                message = f"<strong>{n.actor.username}</strong> ti ha invitato alla sfida: <em>{challenge.name}</em>."
                link = url_for('main.challenge_detail', challenge_id=challenge.id)
            else:
                message = f"<strong>{n.actor.username}</strong> ti ha invitato a una sfida che è stata rimossa."
            icon = "🎯"
            bg_color = "bg-warning"

        elif n.action == 'challenge_accepted':
            challenge = Challenge.query.get(n.object_id)
            if challenge:
                message = f"<strong>{n.actor.username}</strong> ha accettato la tua sfida: <em>{challenge.name}</em>."
                link = url_for('main.challenge_detail', challenge_id=challenge.id)
            else:
                message = f"<strong>{n.actor.username}</strong> ha accettato una tua sfida che è stata rimossa."
            icon = "✅"
            bg_color = "bg-success"

        elif n.action == 'bet_won':
            # La tua logica per bet_won è corretta
            challenge = Challenge.query.get(n.object_id) # object_id è l'ID della sfida
            if challenge:
                message = f"🎉 Hai vinto una scommessa! <strong>{n.actor.username}</strong> ti deve: <em>{challenge.bet_value}</em>"
                bet = Bet.query.filter_by(challenge_id=challenge.id, winner_id=current_user.id).first()
                if bet:
                    link = url_for('main.bet_details', bet_id=bet.id)
            else:
                message = f"🎉 Hai vinto una scommessa contro <strong>{n.actor.username}</strong>!"
            icon = "🎉"
            bg_color = "bg-success"
        
        elif n.action == 'bet_lost':
            # La tua logica per bet_lost è corretta
            challenge = Challenge.query.get(n.object_id)
            if challenge:
                message = f"💸 Hai perso una scommessa! Devi a <strong>{n.actor.username}</strong>: <em>{challenge.bet_value}</em>"
                bet = Bet.query.filter_by(challenge_id=challenge.id, loser_id=current_user.id).first()
                if bet:
                    link = url_for('main.bet_details', bet_id=bet.id)
            else:
                message = f"💸 Hai perso una scommessa contro <strong>{n.actor.username}</strong>."
            icon = "💸"
            bg_color = "bg-danger"

        elif n.action == 'mention_in_post':
            post = Post.query.get(n.object_id)
            if post:
                message = f"<strong>{n.actor.username}</strong> ti ha menzionato in un post."
                link = url_for('main.post_detail', post_id=post.id)
            else:
                message = f"<strong>{n.actor.username}</strong> ti ha menzionato in un post rimosso."
            icon = "📣"
            bg_color = "bg-info"
        
        elif n.action == 'mention_in_comment':
            post = Post.query.get(n.object_id)
            if post:
                message = f"<strong>{n.actor.username}</strong> ti ha menzionato in un commento."
                link = url_for('main.post_detail', post_id=post.id) + '#comments-section'
            else:
                message = f"<strong>{n.actor.username}</strong> ti ha menzionato in un commento su un post rimosso."
            icon = "💬"
            bg_color = "bg-info"
        
        elif n.action == 'title_up':
            user = User.query.get(n.object_id)
            if user:
                message = f"👑 **Promozione!** Hai raggiunto il rango di <strong>{user.title}</strong>!"
                link = url_for('main.user_profile', user_id=user.id)
            icon = "👑"
            bg_color = "bg-warning"
                
        elif n.action == 'route_approved':
            route = Route.query.get(n.object_id)
            if route:
                message = f"🗺️ La tua proposta per il percorso <strong>'{route.name}'</strong> è stata approvata!"
                link = url_for('main.route_detail', route_id=route.id)
            icon = "🗺️"
            bg_color = "bg-success"
        
        elif n.action == 'bet_paid':
            bet = Bet.query.get(n.object_id)
            if bet:
                message = f"✅ <strong>{n.actor.username}</strong> ha saldato il suo debito per la scommessa: <em>{bet.bet_value}</em>."
                link = url_for('main.bet_details', bet_id=bet.id)
            else:
                message = f"✅ <strong>{n.actor.username}</strong> ha saldato una scommessa."
            icon = "✅"
            bg_color = "bg-success"

        notification_messages.append({
            'message': message,
            'link': link,
            'timestamp': n.timestamp,
            'read': n.read,
            'icon': icon,
            'bg_color': bg_color,
            'id': n.id
        })

    # Segna le notifiche come lette
    unread_notifications = current_user.notifications.filter_by(read=False).all()
    for n in unread_notifications:
        n.read = True
    db.session.commit()

    return render_template('notifications.html', 
                         notifications=notification_messages, 
                         unread_count=unread_count,
                         is_homepage=False)

@main.route('/challenge/<int:challenge_id>')
@login_required
def challenge_detail(challenge_id):
    """Dettaglio di una sfida specifica"""
    print(f"🎯 DEBUG challenge_detail: Inizio per sfida {challenge_id}, utente {current_user.id}")
    
    challenge = Challenge.query.get_or_404(challenge_id)
    print(f"🎯 DEBUG: Sfida trovata - ID: {challenge.id}, Nome: {challenge.name}, Tipo: {challenge.challenge_type}, Creatore: {challenge.created_by}")

    # Verifica se la sfida è scaduta
    #if challenge.end_date < datetime.utcnow() and challenge.is_active:
    #    challenge.is_active = False
    #    db.session.commit()
    #    flash('Questa sfida è appena scaduta!', 'info')
        
    # DEBUG ESTESO: Query degli inviti
    print(f"🔍 DEBUG: Eseguo query inviti per challenge_id = {challenge_id}")
    invitations = ChallengeInvitation.query.filter_by(challenge_id=challenge_id).all()
    print(f"🔍 DEBUG: Trovati {len(invitations)} inviti per questa sfida")
    
    for inv in invitations:
        invited_user = User.query.get(inv.invited_user_id)
        print(f"🔍 DEBUG Invito: ID {inv.id} -> User {inv.invited_user_id} ({invited_user.username if invited_user else 'N/A'}) -> Status {inv.status}")

    # DEBUG: Cerca l'invito specifico per l'utente corrente
    user_invitation = ChallengeInvitation.query.filter_by(
        challenge_id=challenge_id, 
        invited_user_id=current_user.id
    ).first()
    
    if user_invitation:
        print(f"✅ DEBUG: UTENTE CORRENTE HA INVITO - Status: {user_invitation.status}")
    else:
        print(f"❌ DEBUG: UTENTE CORRENTE NON HA INVITO per questa sfida")

    # Recupera le attività
    activities = Activity.query.filter_by(challenge_id=challenge_id)\
                              .order_by(Activity.created_at.desc())\
                              .all()

    print(f"🎯 DEBUG: Render template con {len(invitations)} inviti")
    
    return render_template('challenge_detail.html', 
                         challenge=challenge, 
                         activities=activities, 
                         invitations=invitations,
                         is_homepage=False)

@main.route("/challenge/<int:challenge_id>/accept", methods=["POST"])
@login_required
def accept_challenge(challenge_id):
    print(f"🎯 DEBUG: Inizio accept_challenge per sfida {challenge_id}")
    print(f"🎯 DEBUG: Utente corrente: {current_user.username} (ID: {current_user.id})")
    
    challenge = Challenge.query.get_or_404(challenge_id)
    print(f"🎯 DEBUG: Sfida trovata: {challenge.name} (Creatore ID: {challenge.created_by})")
    
    # Trova il creatore della sfida
    creator = User.query.get(challenge.created_by)
    print(f"🎯 DEBUG: Creatore sfida: {creator.username if creator else 'NON TROVATO'} (ID: {challenge.created_by})")

    invitation = ChallengeInvitation.query.filter_by(
        challenge_id=challenge_id, 
        invited_user_id=current_user.id
    ).first()

    print(f"🎯 DEBUG: Invito trovato: {invitation}")
    if invitation:
        print(f"🎯 DEBUG: Stato invito prima: {invitation.status}")

    if invitation and invitation.status == 'pending':
        print("🎯 DEBUG: Invito valido e pending - procedo con l'accettazione")
        
        invitation.status = 'accepted'
        invitation.responded_at = datetime.utcnow()
        
        # --- CORREZIONE CRITICA: NOTIFICA PER IL CREATORE ---
        if challenge.created_by != current_user.id:
            print(f"🎯 DEBUG: Creazione notifica per il creatore (ID: {challenge.created_by})")
            
            # Crea la notifica di accettazione
            notification = Notification(
                recipient_id=challenge.created_by,  # Il creatore della sfida
                actor_id=current_user.id,           # Chi ha accettato
                action='challenge_accepted',
                object_id=challenge.id,
                object_type='challenge'
            )
            db.session.add(notification)
            
            # DEBUG: Verifica che la notifica sia stata creata
            db.session.flush()  # Forza il salvataggio per ottenere l'ID
            print(f"✅ DEBUG: Notifica creata - ID: {notification.id}, Per: {challenge.created_by}, Azione: challenge_accepted")
        else:
            print("🎯 DEBUG: L'utente sta accettando la propria sfida - nessuna notifica necessaria")
        
        try:
            db.session.commit()
            print("✅ DEBUG: Database commit effettuato con successo")
            
            # DEBUG: Verifica che la notifica sia nel database
            if challenge.created_by != current_user.id:
                saved_notification = Notification.query.filter_by(
                    recipient_id=challenge.created_by,
                    actor_id=current_user.id,
                    action='challenge_accepted',
                    object_id=challenge.id
                ).first()
                print(f"🔍 DEBUG: Notifica salvata nel DB: {saved_notification is not None}")
                if saved_notification:
                    print(f"🔍 DEBUG: Dettagli notifica salvata - ID: {saved_notification.id}, Timestamp: {saved_notification.timestamp}")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ DEBUG: Errore durante il commit: {e}")
            flash('Errore durante l\'accettazione della sfida.', 'danger')
            return redirect(url_for('main.challenges_list'))
        
        flash('Hai accettato la sfida!', 'success')
    else:
        print(f"❌ DEBUG: Invito non valido - status: {invitation.status if invitation else 'Nessun invito'}")
        flash('Invito non trovato o già gestito.', 'warning')

    return redirect(url_for('main.challenges_list'))

@main.route("/challenge/<int:challenge_id>/decline", methods=["POST"])
@login_required
def decline_challenge(challenge_id):
    challenge = Challenge.query.get_or_404(challenge_id)
    invitation = ChallengeInvitation.query.filter_by(
        challenge_id=challenge_id, 
        invited_user_id=current_user.id
    ).first()
    
    if invitation and invitation.status == 'pending':
        invitation.status = 'declined'
        invitation.responded_at = datetime.utcnow()
        db.session.commit()
        flash('Hai rifiutato la sfida.', 'info')
    else:
        flash('Invito non trovato o già gestito.', 'warning')
    
    return redirect(url_for('main.challenges_list'))

@main.route('/track-activity')
def track_activity():
    """Pagina di tracking attività live"""
    routes = Route.query.filter_by(is_active=True).all()
    return render_template('track_activity.html', routes=routes)

@main.route('/api/save-live-activity', methods=['POST'])
@login_required
def save_live_activity():
    """Salva un'attività tracciata live"""
    print("User:", current_user)
    data = request.get_json()
    print("Received data:", data)
    try:
        data = request.get_json()
        
        # Prepara i dati
        positions = data.get('positions', [])
        gps_track = json.dumps(positions) if positions else '[]'
        distance = data.get('distance', 0) or 0.1  # Evita 0.0
        duration = data.get('duration', 0) or 1    # Evita 0 (in secondi)
        
        # CALCOLA avg_speed (km/h)
        # velocità = distanza / tempo (in ore)
        hours = duration / 3600  # secondi → ore
        avg_speed = distance / hours if hours > 0 else 0
        
        # Crea nuova attività con TUTTI i campi obbligatori
        new_activity = Activity(
            user_id=current_user.id,
            route_id=data.get('route_id'),
            duration=duration,
            distance=distance,
            activity_type='Corsa',
            gps_track=gps_track,
            avg_speed=round(avg_speed, 2)  # ← OBBLIGATORIO!
            # challenge_id può essere None
            # created_at si aggiunge automaticamente
        )
        
        db.session.add(new_activity)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'activity_id': new_activity.id,
            'message': f'Attività salvata! {distance:.2f}km in {duration//60}min'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    


@main.route("/test_accept_challenge/<int:challenge_id>")
@login_required
def test_accept_challenge(challenge_id):
    """Route di test per accettare una sfida - TEMPORANEA"""
    print(f"🎯 TEST MANUALE: Accettazione sfida {challenge_id} by user {current_user.id}")
    
    challenge = Challenge.query.get_or_404(challenge_id)
    print(f"🎯 TEST: Challenge: {challenge.name}, Creator: {challenge.created_by}")
    
    # Trova l'invito
    invitation = ChallengeInvitation.query.filter_by(
        challenge_id=challenge_id, 
        invited_user_id=current_user.id
    ).first()
    
    if invitation and invitation.status == 'pending':
        print("🎯 TEST: Invito trovato e pending - procedo con accettazione")
        invitation.status = 'accepted'
        invitation.responded_at = datetime.utcnow()
        
        # Crea notifica per il creatore
        if challenge.created_by != current_user.id:
            notification = Notification(
                recipient_id=challenge.created_by,
                actor_id=current_user.id,
                action='challenge_accepted',
                object_id=challenge.id,
                object_type='challenge'
            )
            db.session.add(notification)
            print(f"✅ TEST: Notifica creata per creator ID {challenge.created_by}")
        
        db.session.commit()
        print("✅ TEST: Database commit effettuato")
        flash('TEST: Sfida accettata con successo!', 'success')
    else:
        status = invitation.status if invitation else 'NON TROVATO'
        print(f"❌ TEST: Invito non valido - Status: {status}")
        flash(f'TEST: Impossibile accettare - Invito: {status}', 'warning')
    
    return redirect(url_for('main.challenges_list'))


@main.route("/debug/my_invitations")
@login_required
def debug_my_invitations():
    """Mostra tutti gli inviti dell'utente corrente"""
    invitations = ChallengeInvitation.query.filter_by(invited_user_id=current_user.id).all()
    
    result = f"""
    <h1>🎯 I Miei Inviti - {current_user.username} (ID: {current_user.id})</h1>
    
    <h2>Inviti Pendenti ({len([i for i in invitations if i.status == 'pending'])})</h2>
    <ul>
        {"".join([f'''
        <li style="margin-bottom: 10px;">
            <strong>Sfida ID: {inv.challenge_id}</strong> - Status: <span style="color: {'orange' if inv.status == 'pending' else 'green' if inv.status == 'accepted' else 'red'}">{inv.status}</span>
            <br>
            <a href="/challenge/{inv.challenge_id}" class="btn btn-sm btn-primary">Vai alla Sfida</a>
            <a href="/test/accept_challenge/{inv.challenge_id}" class="btn btn-sm btn-success">Test Accetta</a>
        </li>
        ''' for inv in invitations if inv.status == 'pending'])}
    </ul>
    
    <h2>Tutti gli Inviti ({len(invitations)})</h2>
    <ul>
        {"".join([f'<li>Sfida ID: {inv.challenge_id} - Status: {inv.status}</li>' for inv in invitations])}
    </ul>
    
    <h2>Link Utili</h2>
    <ul>
        <li><a href="/challenges">Lista Sfide Completa</a></li>
        <li><a href="/notifications">Le Mie Notifiche</a></li>
    </ul>
    """
    
    return result



@main.route("/challenges/finished")
@login_required
def finished_challenges():
    """Pagina dedicata alle sfide terminate"""
    page = request.args.get('page', 1, type=int)
    now = datetime.utcnow()
    
    # Sfide terminate (scadute e non attive)
    finished_challenges_query = Challenge.query.filter(
        Challenge.end_date < now,
        Challenge.is_active == False
    )
    
    pagination = finished_challenges_query.order_by(Challenge.end_date.desc()).paginate(page=page, per_page=10, error_out=False)
    
    return render_template("finished_challenges.html", 
                         challenges=pagination.items,
                         pagination=pagination,
                         now=now,
                         is_homepage=False)


@main.route("/bet/<int:bet_id>/mark_paid", methods=["POST"])
@login_required
def mark_bet_paid(bet_id):
    """Segna una scommessa come pagata - L'ora della verità ha suonato."""
    
    # Il guardiano silenzioso: la validazione CSRF
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Il codice di sicurezza è invalido o è scaduto. La transazione non può essere completata.', 'danger')
        return redirect(url_for('main.bet_details', bet_id=bet_id))

    # La ricerca della scommessa leggendaria
    bet = Bet.query.get_or_404(bet_id)
    
    # Il verdetto del destino: solo lo sconfitto può riscattarsi
    if bet.loser_id != current_user.id:
        flash('Solo colui che ha subìto la sconfitta può riscattare il proprio onore.', 'danger')
        return redirect(url_for('main.user_profile', user_id=current_user.id))

    # ⚔️ INIZIO DELLA CERIMONIA DEL PAGAMENTO ⚔️

    # 1. Il Sigillo dell'Onore - La scommessa viene marchiata come saldata
    bet.status = 'paid'
    bet.paid_at = datetime.utcnow()
    db.session.add(bet)

    # 2. L'Annuncio al Regno - Il post viene aggiornato per la posterità
    if bet.related_post_id:
        related_post = Post.query.get(bet.related_post_id)
        if related_post:
            paid_announcements = [
                f"🏆 L'onore è stato ripagato! {bet.loser.username} ha saldato il debito con {bet.winner.username}. La bilancia della giustizia è in equilibrio.",
                f"💰 Il conto è stato regolato! {bet.loser.username} ha finalmente onorato la scommessa versando {bet.bet_value} a {bet.winner.username}. L'arena delle scommesse applaude.",
                f"⚖️ Giustizia è fatta! Dopo la sconfitta, {bet.loser.username} paga il tributo a {bet.winner.username}. Il cerchio si chiude."
            ]
            related_post.content = random.choice(paid_announcements)
            related_post.post_category = 'system_bet_paid'
            db.session.add(related_post)

    # 3. Il Messaggio del Corvo - La notifica vola verso il vincitore
    winner_notification = Notification(
        recipient_id=bet.winner_id,
        actor_id=current_user.id,
        action='bet_paid',
        object_id=bet.id,
        object_type='bet'
        # Rimossa la proprietà 'message' che non esiste nel modello
    )
    db.session.add(winner_notification)

    # 🏁 FINE DELLA CERIMONIA 🏁

    try:
        # Il Giuramento Eterno - Tutte le modifiche vengono sigillate
        db.session.commit()
        flash(f'🎊 La scommessa è stata ufficialmente sigillata come pagata! L\'onore è stato preservato.', 'success')
        
        # Registro degli eventi epici
        print(f"📜 [BET PAID] User {current_user.id} ha saldato la scommessa {bet_id}")
        
    except Exception as e:
        # L'Oscuro Presagio - Qualcosa è andato storto
        db.session.rollback()
        flash(f'Un oscuro presagio ha interrotto la cerimonia: {e}', 'danger')
        print(f"💥 ERRORE CATASTROFICO in mark_bet_paid: {e}")

    return redirect(url_for('main.bet_details', bet_id=bet.id))

@main.route("/notifications/clear_all", methods=["POST"])
@login_required
def clear_all_notifications():
    """Segna tutte le notifiche come lette"""
    try:
        # Marca tutte come lette
        Notification.query.filter_by(recipient_id=current_user.id, read=False).update({'read': True})
        db.session.commit()
        flash('✅ Tutte le notifiche sono state marcate come lette!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('❌ Errore durante l\'aggiornamento delle notifiche.', 'danger')
        print(f"Errore clear_all_notifications: {e}")
    
    return redirect(url_for('main.notifications'))

@main.route("/test/create_test_route")
def create_test_route():
    """Crea una route di test"""
    from app.models import Route, User
    from datetime import datetime
    import json
    
    # Prendi il primo utente come creatore
    creator = User.query.first()
    
    test_route = Route(
        name="Route di Test",
        description="Route creata per testare le scommesse",
        coordinates=json.dumps({
            "type": "Feature",
            "geometry": {
                "type": "LineString", 
                "coordinates": [[12.0, 41.0], [12.1, 41.1]]
            },
            "properties": {}
        }),
        activity_type="Corsa",
        created_by=creator.id,
        distance_km=5.0,
        is_active=True
    )
    
    try:
        db.session.add(test_route)
        db.session.commit()
        return "✅ Route di test creata!"
    except Exception as e:
        db.session.rollback()
        return f"❌ Errore: {e}"
    
    

@main.route("/test/create_test_bet")
@login_required
def create_test_bet():
    """Crea una scommessa di test - VERSIONE CORRETTA"""
    try:
        from app.models import Bet, Challenge, User, Notification, Route
        from datetime import datetime, timedelta
        
        # USER1: Tu (vincitore)
        user1 = current_user
        
        # USER2: Un altro utente
        user2 = User.query.filter(User.id != current_user.id).first()
        
        if not user2:
            return "❌ Serve almeno un altro utente per il test"
        
        # Prendi una route esistente o creane una fittizia
        existing_route = Route.query.first()
        if not existing_route:
            return "❌ Nessuna route nel database. Crea prima una route."
        
        # Crea una sfida fittizia COMPLETA
        test_challenge = Challenge(
            name="TEST Scommessa Birra",
            route_id=existing_route.id,  # ⬅️ OBBLIGATORIO
            start_date=datetime.utcnow() - timedelta(days=1),  # ⬅️ OBBLIGATORIO
            end_date=datetime.utcnow() - timedelta(hours=1),   # ⬅️ OBBLIGATORIO (scaduta)
            created_by=user2.id,
            challenge_type='open',
            bet_type="beer",
            bet_value="🍺 1 Birra",
            is_active=False  # Già terminata
        )
        db.session.add(test_challenge)
        db.session.flush()  # Ottieni ID senza commit
        
        # Crea la scommessa
        test_bet = Bet(
            challenge_id=test_challenge.id,
            winner_id=user1.id,
            loser_id=user2.id,
            bet_type="beer",
            bet_value="🍺 1 Birra",
            status='pending'
        )
        db.session.add(test_bet)
        
        # Crea notifiche di test
        winner_notification = Notification(
            recipient_id=user1.id,
            actor_id=user2.id,
            action='bet_won',
            object_id=test_challenge.id,
            object_type='bet'
        )
        db.session.add(winner_notification)
        
        loser_notification = Notification(
            recipient_id=user2.id,
            actor_id=user1.id,
            action='bet_lost', 
            object_id=test_challenge.id,
            object_type='bet'
        )
        db.session.add(loser_notification)
        
        db.session.commit()
        
        return f"""
        <h1>✅ Test Scommessa Creato!</h1>
        <p><strong>Vincitore:</strong> {user1.username} (tu)</p>
        <p><strong>Perdente:</strong> {user2.username}</p>
        <p><strong>Scommessa:</strong> 🍺 1 Birra</p>
        <p><strong>Route usata:</strong> {existing_route.name}</p>
        <br>
        <a href="/user/{user1.id}" class="btn btn-success">Vedi il TUO profilo (vincitore)</a>
        <a href="/user/{user2.id}" class="btn btn-danger">Vedi profilo {user2.username} (perdente)</a>
        <a href="/notifications" class="btn btn-primary">Vedi Notifiche</a>
        """
        
    except Exception as e:
        db.session.rollback()
        return f"❌ Errore: {e}"

@main.route("/bet/<string:bet_id>")
@login_required
def bet_details(bet_id):
    """Dettagli di una scommessa specifica"""
    from app.models import Bet
    
    try:
        bet_id_int = int(bet_id)
    except ValueError:
        flash('ID scommessa non valido.', 'danger')
        return redirect(url_for('main.index'))
    
    bet = Bet.query.get_or_404(bet_id_int)
    
    # Verifica che l'utente sia coinvolto nella scommessa
    if bet.winner_id != current_user.id and bet.loser_id != current_user.id:
        flash('Non hai accesso a questa scommessa.', 'danger')
        return redirect(url_for('main.index'))
    
    return render_template("bet_details.html", 
                         bet=bet,
                         is_homepage=False)

@main.route("/bets")
@login_required
def my_bets():
    """Pagina con tutte le scommesse dell'utente"""
    from app.models import Bet
    from datetime import datetime, timedelta
    
    # Scommesse vinte
    bets_won = Bet.query.filter_by(winner_id=current_user.id)\
                       .options(db.joinedload(Bet.loser),
                                db.joinedload(Bet.challenge))\
                       .order_by(Bet.created_at.desc())\
                       .all()
    
    # Scommesse perse
    bets_lost = Bet.query.filter_by(loser_id=current_user.id)\
                        .options(db.joinedload(Bet.winner),
                                 db.joinedload(Bet.challenge))\
                        .order_by(Bet.created_at.desc())\
                        .all()
    
    # Data per evidenziare scommesse nuove (ultime 24h)
    today_minus_1day = datetime.utcnow() - timedelta(days=1)
    
    return render_template("my_bets.html",
                         bets_won=bets_won,
                         bets_lost=bets_lost,
                         today_minus_1day=today_minus_1day,
                         is_homepage=False)

@main.route("/bet-stats")
@login_required
def bet_stats():
    """Mostra le statistiche delle scommesse"""
    from app.models import Bet

    bets = Bet.query.filter(
        (Bet.winner_id == current_user.id) | (Bet.loser_id == current_user.id)
    ).all()

    total_bets = len(bets)
    wins = sum(1 for b in bets if b.winner_id == current_user.id)
    losses = total_bets - wins

    return render_template(
        "bet_stats.html",
        bets=bets,
        total_bets=total_bets,
        wins=wins,
        losses=losses,
        is_homepage=False
    )



# In app/main/routes.py
# --- Funzione helper per controllare il tipo di file ---
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@main.route('/posts/new', methods=['GET', 'POST'])
@login_required
def create_post():
    # --- LOGICA ESEGUITA QUANDO IL FORM VIENE INVIATO (METODO POST) ---
    if request.method == 'POST':
        content = request.form.get('content', '')
        post_type = request.form.get('post_type', 'text')
        image_file = request.files.get('image')
        group_id = request.form.get('group_id') # Prende l'ID del gruppo dal form
        
        # Converte l'ID del gruppo in intero se presente, altrimenti rimane None
        if group_id:
            try:
                group_id = int(group_id)
            except ValueError:
                group_id = None
        else:
            group_id = None

        # Validazione base del contenuto
        if not content.strip() and not image_file:
            flash('Il post non può essere vuoto. Aggiungi testo o un\'immagine.', 'warning')
            return redirect(url_for('main.create_post'))

        image_filename = None
        # Gestione dell'immagine (se caricata)
        if image_file and image_file.filename != '':
            if allowed_file(image_file.filename):
                upload_dir = os.path.join(current_app.root_path, 'static', 'posts_images')
                os.makedirs(upload_dir, exist_ok=True)
                
                filename = secure_filename(image_file.filename)
                unique_filename = f"{uuid.uuid4()}{os.path.splitext(filename)[1]}"
                save_path = os.path.join(upload_dir, unique_filename)
                
                try:
                    image_file.save(save_path)
                    image_filename = unique_filename
                    post_type = 'image'
                except Exception as e:
                    flash(f"Errore nel salvataggio dell'immagine: {e}", 'danger')
                    return redirect(url_for('main.create_post'))
            else:
                flash('Formato immagine non valido. Usa PNG, JPG, JPEG o GIF.', 'danger')
                return redirect(url_for('main.create_post'))

        # Analisi del contenuto per menzioni e hashtag
        processed_content_mentions, mentioned_users = parse_mentions(content)

        # Creazione dell'oggetto Post in memoria
        new_post = Post(
            user_id=current_user.id,
            content=processed_content_mentions, # Contenuto temporaneo con link delle menzioni
            image_url=image_filename,
            post_type=post_type,
            group_id=group_id,
            post_category=request.form.get('post_category', 'user_post')
        )

        print("\n--- DEBUG CREATE_POST ---")
        print(f"Contenuto: {new_post.content}")
        print(f"Group ID salvato: {new_post.group_id} (Tipo: {type(new_post.group_id)})")
        print("------------------------\n")

        # Analisi per hashtag, che modifica sia il contenuto che l'oggetto new_post
        final_content = parse_and_link_hashtags(processed_content_mentions, new_post)
        new_post.content = final_content # Aggiornamento con il contenuto finale

        try:
            db.session.add(new_post)
            db.session.flush()  # Assegna un ID a new_post

            # Creazione delle notifiche per le menzioni
            for user in mentioned_users:
                if user.id != current_user.id:
                    notification = Notification(
                        recipient_id=user.id,
                        actor_id=current_user.id,
                        action='mention_in_post',
                        object_id=new_post.id,
                        object_type='post'
                    )
                    db.session.add(notification)
            
            add_prestige(current_user, 'new_post')
            if len(current_user.posts) == 1:
                complete_onboarding_step(current_user, 'first_post')
            db.session.commit()
            
            flash('Post creato con successo!', 'success')

            # Redirect intelligente: alla bacheca del gruppo o alla home page
            if group_id:
                return redirect(url_for('main.group_detail', group_id=group_id))
            else:
                return redirect(url_for('main.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la creazione del post: {e}", 'danger')
            return redirect(url_for('main.create_post'))

    # --- LOGICA ESEGUITA QUANDO LA PAGINA VIENE CARICATA (METODO GET) ---
    
    # Recupera i gruppi a cui l'utente è iscritto per popolare il menu a tendina
    user_groups = current_user.joined_groups.order_by(Group.name.asc()).all()
    
    # Codice di debug per verificare i gruppi trovati
    print("\n--- [DEBUG] Caricamento pagina CREATE_POST (GET) ---")
    print(f"Utente: {current_user.username}")
    print(f"Numero di gruppi trovati: {len(user_groups)}")
    for group in user_groups:
        print(f"  - Gruppo: {group.name} (ID: {group.id})")
    print("-------------------------------------------\n")
    
    # Mostra il form vuoto, passando la lista dei gruppi
    return render_template('create_post.html', is_homepage=False, user_groups=user_groups)


# --- Assicurati che la funzione allowed_file sia definita (probabilmente in routes.py o una utility) ---
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Aggiungi la route per visualizzare un singolo post (necessaria per i link) ---
@main.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Recupera i commenti per questo post
    post_comments = PostComment.query.filter_by(
        post_id=post_id, 
        parent_id=None # <-- FILTRO CRUCIALE
    ).join(User).order_by(PostComment.created_at.asc()).all()
    
    # Recupera i like per questo post
    post_likes = PostLike.query.filter_by(post_id=post_id).join(User).all()
    
    # Verifica se l'utente corrente ha messo like a questo post
    user_liked_post = False
    if current_user.is_authenticated:
        user_like = PostLike.query.filter_by(post_id=post_id, user_id=current_user.id).first()
        if user_like:
            user_liked_post = True

    return render_template('post_detail.html', 
                           post=post, 
                           post_comments=post_comments, 
                           post_likes=post_likes,
                           user_liked_post=user_liked_post,
                           PostComment=PostComment, # <-- AGGIUNGI QUESTA RIGA
                           is_homepage=False)

# --- Esempi di route per commenti e like (da aggiungere) ---

@main.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment_to_post(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')

    # --- NUOVA RIGA: RECUPERA IL PARENT_ID DAL FORM ---
    parent_id = request.form.get('parent_id', type=int)
    # --- FINE NUOVA RIGA ---
    
    if not content:
        flash('Il commento non può essere vuoto.', 'warning')
        return redirect(url_for('main.post_detail', post_id=post_id))
        
    new_comment = PostComment(
        user_id=current_user.id,
        post_id=post_id,
        content=content,
        parent_id=parent_id
    )
    db.session.add(new_comment)
    db.session.commit()
    flash('Commento aggiunto!', 'success')
    return redirect(url_for('main.post_detail', post_id=post_id))

@main.route('/post/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_post_like(post_id):
    post = Post.query.get_or_404(post_id)
    like = PostLike.query.filter_by(post_id=post_id, user_id=current_user.id).first()
    
    if like:
        db.session.delete(like)
        action = 'unliked'
    else:
        new_like = PostLike(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
        action = 'liked'
        if post.user_id != current_user.id:
            add_prestige(post.user, 'receive_like')
        
    db.session.commit()
    
    # Restituisce il conteggio usando il metodo .count() di SQLAlchemy
    return jsonify({'status': 'success', 'action': action, 'new_like_count': post.likes.count()})


@main.route('/api/post/<int:post_id>/comment/<int:parent_comment_id>/reply', methods=['POST'])
@login_required
def reply_to_comment_ajax(post_id, parent_comment_id):
    """
    API endpoint per aggiungere una risposta a un commento in modo asincrono.
    """
    post = Post.query.get_or_404(post_id)
    parent_comment = PostComment.query.get_or_404(parent_comment_id)
    content = request.form.get('content')

    if not content or not content.strip():
        return jsonify({'status': 'error', 'message': 'La risposta non può essere vuota.'}), 400

    # Riconosci menzioni
    processed_content, mentioned_users = parse_mentions(content)

    reply = PostComment(
        user_id=current_user.id,
        post_id=post_id,
        parent_id=parent_comment_id,  # 👈 collega la risposta al commento originale
        content=processed_content
    )
    db.session.add(reply)
    add_prestige(current_user, 'new_comment')

    # Notifica all'autore del commento
    if parent_comment.user_id != current_user.id:
        notification = Notification(
            recipient_id=parent_comment.user_id,
            actor_id=current_user.id,
            action='reply_to_comment',
            object_id=post.id,
            object_type='post'
        )
        db.session.add(notification)

    # Notifica eventuali utenti menzionati
    for user in mentioned_users:
        if user.id != current_user.id:
            notif = Notification(
                recipient_id=user.id,
                actor_id=current_user.id,
                action='mention_in_comment',
                object_id=post.id,
                object_type='post'
            )
            db.session.add(notif)

    db.session.commit()

    reply_html = render_template(
        'partials/feed_items/_comment.html',
        comment=reply,
        PostComment=PostComment
    )

    return jsonify({
        'status': 'success',
        'message': 'Risposta aggiunta!',
        'comment_html': reply_html,
        'new_comment_count': post.comments.count()
    })



@main.route('/api/feed')
def api_feed():
    page = request.args.get('page', 1, type=int)
    # Passiamo 'current_user' anche qui
    items, has_next = get_unified_feed_items(user=current_user, page=page, per_page=5)
    items, has_next = get_unified_feed_items(page=page, per_page=5)
    
    items_html = render_template('partials/_feed_posts_chunk.html', items=items)
    
    return jsonify({
        'html': items_html,
        'has_next_page': has_next
    })

# TEST #####################################################################################################################################

@main.route("/test/create_test_bet_leo_marco")
@login_required  
def create_test_bet_leo_marco():
    """Crea una scommessa di test specifica per Leopoldo e Marco"""
    try:
        from app.models import Bet, Challenge, User, Notification, Route
        from datetime import datetime, timedelta
        
        # USER1: Leopoldo (vincitore) - deve essere loggato
        if current_user.username != "Leopoldo":
            return """
            <div class="alert alert-danger">
                <h4>❌ Accesso Negato</h4>
                <p>Devi essere loggato come <strong>Leopoldo</strong> per questo test.</p>
                <p>Utente attuale: <strong>{}</strong></p>
                <a href="/auth/logout" class="btn btn-warning">Logout</a>
            </div>
            """.format(current_user.username)
        
        user1 = current_user  # Leopoldo
        
        # USER2: Marco (perdente)
        user2 = User.query.filter_by(username="Marco").first()
        
        if not user2:
            return """
            <div class="alert alert-danger">
                <h4>❌ Utente Non Trovato</h4>
                <p>L'utente <strong>Marco</strong> non è stato trovato nel database.</p>
                <a href="/test/create_test_user" class="btn btn-primary">Crea Utente Test</a>
            </div>
            """
        
        # Prendi una route esistente
        existing_route = Route.query.first()
        if not existing_route:
            return """
            <div class="alert alert-danger">
                <h4>❌ Route Non Trovata</h4>
                <p>Nessuna route trovata nel database.</p>
                <a href="/test/create_test_route" class="btn btn-primary">Crea Route Test</a>
            </div>
            """
        
        # Crea una sfida fittizia COMPLETA
        test_challenge = Challenge(
            name="Sfida Test Leo vs Marco",
            route_id=existing_route.id,
            start_date=datetime.utcnow() - timedelta(days=1),
            end_date=datetime.utcnow() - timedelta(hours=1),  # Scaduta
            created_by=user2.id,  # Marco crea la sfida
            challenge_type='closed',
            bet_type="beer", 
            bet_value="🍺 1 Birra",
            is_active=False  # Già terminata
        )
        db.session.add(test_challenge)
        db.session.flush()  # Ottieni ID senza commit
        
        # Crea la scommessa - Leopoldo vince, Marco perde
        test_bet = Bet(
            challenge_id=test_challenge.id,
            winner_id=user1.id,  # Leopoldo vince
            loser_id=user2.id,   # Marco perde
            bet_type="beer",
            bet_value="🍺 1 Birra", 
            status='pending'
        )
        db.session.add(test_bet)
        
        # Crea notifiche
        winner_notification = Notification(
            recipient_id=user1.id,  # Leopoldo
            actor_id=user2.id,      # Marco
            action='bet_won',
            object_id=test_challenge.id,
            object_type='bet'
        )
        db.session.add(winner_notification)
        
        loser_notification = Notification(
            recipient_id=user2.id,  # Marco  
            actor_id=user1.id,      # Leopoldo
            action='bet_lost',
            object_id=test_challenge.id, 
            object_type='bet'
        )
        db.session.add(loser_notification)
        
        db.session.commit()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Test Scommessa Creato</title>
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
            <div class="container mt-4">
                <div class="alert alert-success">
                    <h1>✅ Test Scommessa Leo vs Marco Creato!</h1>
                </div>
                
                <div class="card mb-4">
                    <div class="card-header bg-info text-white">
                        <h4>🎯 Scenario Test Creato</h4>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6">
                                <h5>Vincitore 🎉</h5>
                                <p><strong>Leopoldo (TU)</strong></p>
                                <p>Riceve: 🍺 1 Birra</p>
                                <p>Notifica: "Hai vinto una scommessa!"</p>
                            </div>
                            <div class="col-md-6">
                                <h5>Perdente 💸</h5>
                                <p><strong>Marco</strong></p>
                                <p>Deve: 🍺 1 Birra</p>
                                <p>Notifica: "Hai perso una scommessa!"</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="row">
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-success text-white">
                                <h5>COME LEOPOLDO (VINCITORE)</h5>
                            </div>
                            <div class="card-body">
                                <p>✅ <a href="/user/{user1.id}" class="btn btn-success btn-sm">Vedi il TUO Profilo</a></p>
                                <p><small>Dovresti vedere: "🍺 Ti Devono 1"</small></p>
                                
                                <p>✅ <a href="/notifications" class="btn btn-primary btn-sm">Vedi Notifiche</a></p>
                                <p><small>Dovresti vedere notifica vittoria con icona 🎉</small></p>
                                
                                <p>✅ <a href="/bets" class="btn btn-info btn-sm">Vedi Scommesse</a></p>
                                <p><small>Dovresti vedere scheda scommessa vinta</small></p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="col-md-6">
                        <div class="card h-100">
                            <div class="card-header bg-danger text-white">
                                <h5>COME MARCO (PERDENTE)</h5>
                            </div>
                            <div class="card-body">
                                <p>1. <a href="/auth/logout" class="btn btn-warning btn-sm">Fai Logout</a></p>
                                
                                <p>2. <a href="/test/reset_password_marco" class="btn btn-secondary btn-sm">Reset Password Marco</a></p>
                                <p><small>(Se non conosci la password)</small></p>
                                
                                <p>3. Login come: <strong>Marco</strong></p>
                                
                                <p>4. <a href="/user/{user2.id}" class="btn btn-danger btn-sm">Vedi Profilo Marco</a></p>
                                <p><small>Dovresti vedere: "💸 Devi Pagare 1"</small></p>
                                
                                <p>5. <a href="/notifications" class="btn btn-primary btn-sm">Vedi Notifiche Marco</a></p>
                                <p><small>Dovresti vedere notifica sconfitta con icona 💸</small></p>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="text-center mt-4">
                    <div class="btn-group">
                        <a href="/notifications" class="btn btn-primary">🔔 Testa Notifiche</a>
                        <a href="/bets" class="btn btn-success">💰 Testa Scommesse</a>
                        <a href="/debug/bets_detailed" class="btn btn-secondary">🐛 Debug Scommesse</a>
                    </div>
                </div>
                
                <div class="mt-4">
                    <div class="alert alert-info">
                        <h6>📊 Dati Creati:</h6>
                        <ul>
                            <li><strong>Sfida:</strong> {test_challenge.name} (ID: {test_challenge.id})</li>
                            <li><strong>Scommessa:</strong> ID {test_bet.id} - {test_bet.bet_value}</li>
                            <li><strong>Notifiche:</strong> 2 create (1 per vincitore, 1 per perdente)</li>
                            <li><strong>Route usata:</strong> {existing_route.name}</li>
                        </ul>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        db.session.rollback()
        return f"""
        <div class="alert alert-danger">
            <h4>❌ Errore durante la creazione del test</h4>
            <pre>{str(e)}</pre>
            <a href="/" class="btn btn-primary">Torna alla Home</a>
        </div>
        """
    

@main.route("/test/reset_password_marco")
def reset_password_marco():
    """Resetta password di Marco per testing"""
    from app.models import User
    from werkzeug.security import generate_password_hash
    
    marco = User.query.filter_by(username="Marco").first()
    if marco:
        marco.password_hash = generate_password_hash("test123")
        db.session.commit()
        return """
        <h1>✅ Password Marco Resettata!</h1>
        <div class="alert alert-info">
            <p><strong>Username:</strong> Marco</p>
            <p><strong>Password:</strong> test123</p>
        </div>
        <a href="/auth/login" class="btn btn-primary">Vai al Login</a>
        """
    else:
        return "❌ Utente Marco non trovato"
    

@main.route("/debug/bets_detailed")
def debug_bets_detailed():
    """Debug dettagliato di tutte le scommesse"""
    from app.models import Bet
    
    bets = Bet.query.all()
    
    result = "<h1>💰 Debug Dettagliato Scommesse</h1>"
    
    if not bets:
        result += "<p>❌ Nessuna scommessa nel database</p>"
    else:
        for bet in bets:
            result += f"""
            <div style="border: 1px solid #ccc; padding: 10px; margin: 10px;">
                <h3>Scommessa ID: {bet.id}</h3>
                <p><strong>Challenge ID:</strong> {bet.challenge_id}</p>
                <p><strong>Vincitore:</strong> {bet.winner.username} (ID: {bet.winner_id})</p>
                <p><strong>Perdente:</strong> {bet.loser.username} (ID: {bet.loser_id})</p>
                <p><strong>Scommessa:</strong> {bet.bet_value}</p>
                <p><strong>Status:</strong> {bet.status}</p>
                <p><strong>Creata:</strong> {bet.created_at}</p>
                <p>
                    <a href="/bet/{bet.id}" class="btn btn-primary">Bet Details</a>
                    <a href="/bet/{bet.id}/mark_paid" class="btn btn-success">Mark Paid (GET)</a>
                </p>
            </div>
            """
    
    return result


def parse_mentions(content):
    """
    Analizza un testo, trova le @menzioni (ignorando maiuscole/minuscole), 
    le trasforma in link e restituisce il testo processato e una lista di utenti menzionati.
    """
    print(f"\n--- DEBUG PARSE MENTIONS (Case-Insensitive) ---")
    print(f"Contenuto originale: '{content}'")
    
    mention_pattern = r'@([a-zA-Z0-9_]+)'
    usernames_from_regex = re.findall(mention_pattern, content)
    
    print(f"Usernames trovati dal regex: {usernames_from_regex}")

    if not usernames_from_regex:
        print("Nessun username trovato. Fine.")
        return content, []

    # --- CORREZIONE CHIAVE QUI ---
    # Convertiamo tutti gli username in minuscolo per la ricerca
    usernames_lower = [name.lower() for name in usernames_from_regex]
    
    # Eseguiamo una query case-insensitive confrontando i nomi in minuscolo
    users = User.query.filter(func.lower(User.username).in_(usernames_lower)).all()
    print(f"Utenti trovati nel database (case-insensitive): {users}")
    # --- FINE CORREZIONE ---

    # Creiamo una mappa con gli username in minuscolo per un match facile
    user_map = {user.username.lower(): user for user in users}
    mentioned_users = []

    def replace_mention(match):
        username_original = match.group(1)
        username_lower = username_original.lower()
        
        if username_lower in user_map:
            user = user_map[username_lower]
            if user not in mentioned_users:
                mentioned_users.append(user)
            
            # Usiamo l'username originale per il testo del link per preservare le maiuscole
            link = f'<a href="{url_for("main.user_profile", user_id=user.id)}" class="mention-link">@{username_original}</a>'
            print(f"DEBUG: Sostituzione trovata! Rimpiazzo '@{username_original}' con il link.")
            return link
            
        return match.group(0)

    processed_content = re.sub(mention_pattern, replace_mention, content)
    
    print(f"Contenuto processato: '{processed_content}'")
    print(f"Utenti menzionati da notificare: {mentioned_users}")
    print(f"-------------------------------------------\n")
    
    return processed_content, mentioned_users


# In app/main/routes.py

def parse_and_link_hashtags(content, post_object):
    """
    Analizza un testo, trova gli #hashtag, li salva nel DB,
    li associa al post e li trasforma in link.
    """
    hashtag_pattern = r'#([a-zA-Z0-9_]+)'
    hashtags_in_content = re.findall(hashtag_pattern, content)
    
    # Sostituisce il testo con il link PRIMA di elaborare i tag
    def replace_hashtag(match):
        tag_name = match.group(1)
        link = f'<a href="{url_for("main.tag_search", tag_name=tag_name)}" class="hashtag-link">#{tag_name}</a>'
        return link
    processed_content = re.sub(hashtag_pattern, replace_hashtag, content)

    if not hashtags_in_content:
        return processed_content # Restituisce il contenuto (che potrebbe avere menzioni)

    # Ora salva e associa i tag all'oggetto post
    for tag_name in hashtags_in_content:
        # Cerca se l'hashtag esiste già, ignorando maiuscole/minuscole
        tag = Tag.query.filter(func.lower(Tag.name) == tag_name.lower()).first()
        
        # Se non esiste, lo creiamo
        if not tag:
            tag = Tag(name=tag_name)
            db.session.add(tag)
            # Usiamo flush per ottenere l'ID del nuovo tag prima del commit finale
            # Questo è utile se altre operazioni dipendono da questo
            db.session.flush()

        # Associa il tag al post (se non è già associato)
        # SQLAlchemy è abbastanza intelligente da gestire questo senza controlli duplicati
        if tag not in post_object.tags:
            post_object.tags.append(tag)
            
    return processed_content
###################################################################################################################################
# ... (altri import e la definizione della route upload_gpx) ...
@main.route('/upload-gpx', methods=['GET', 'POST'])
@login_required
def upload_gpx():
    if request.method == 'POST':
        # --- VALIDAZIONE CSRF MANUALE ---
        csrf_token_from_form = request.form.get('csrf_token')
        if not csrf_token_from_form or len(csrf_token_from_form) < 10:
            flash('Token CSRF mancante o non valido.', 'danger')
            return redirect(url_for('main.upload_gpx'))

        # --- Logica di upload del file ---
        if 'gpx_file' not in request.files:
            flash('Nessun file selezionato.', 'danger')
            return redirect(url_for('main.upload_gpx'))
        
        file = request.files['gpx_file']
        
        if file.filename == '':
            flash('Nessun file selezionato.', 'warning')
            return redirect(url_for('main.upload_gpx'))
            
        if file and file.filename.lower().endswith('.gpx'):
            filename = secure_filename(file.filename)
            try:
                gpx = gpxpy.parse(file.stream)
                
                points = []
                points_count = 0
                distance_km = 0.0
                duration_sec = 0

                if gpx.tracks and gpx.tracks[0].segments:
                    track_segment = gpx.tracks[0].segments[0] 
                    if track_segment.points:
                        points = [{'lat': p.latitude, 'lon': p.longitude} for p in track_segment.points]
                        points_count = len(points)
                        
                        distance_km = 0.0 # Default
                        try:
                            if gpx.length_3d():
                                distance_km = gpx.length_3d() / 1000.0
                            elif gpx.length_2d():
                                distance_km = gpx.length_2d() / 1000.0
                        except Exception as dist_e:
                            print(f"Errore nel calcolo della distanza GPX: {dist_e}")
                            distance_km = 0.0 # Fallback a 0 se c'è un problema

                        start_time = None
                        end_time = None
                        
                        if track_segment.points:
                            for p in track_segment.points:
                                if p.time:
                                    start_time = p.time
                                    break
                            for p in reversed(track_segment.points):
                                if p.time:
                                    end_time = p.time
                                    break
                        
                        if start_time and end_time:
                            duration_sec = (end_time - start_time).total_seconds()
                        elif gpx.get_time_first() and gpx.get_time_last():
                            duration_sec = (gpx.get_time_last() - gpx.get_time_first()).total_seconds()
                        
                        gpx_points_json = json.dumps(points)
                        
                        return render_template('upload_gpx_confirm.html', 
                                               filename=filename,
                                               points_count=points_count,
                                               distance_km=distance_km,
                                               duration_sec=duration_sec,
                                               gpx_points_json=gpx_points_json,
                                               # NON passare 'name' o 'description' qui
                                               )

                    else:
                        flash('Il segmento GPX non contiene punti di tracciato validi.', 'danger')
                        return redirect(url_for('main.upload_gpx'))
                else:
                    flash('Il file GPX non contiene tracce o segmenti validi.', 'danger')
                    return redirect(url_for('main.upload_gpx'))
            
            # --- MANTIENI SOLO L'ECCEZIONE GENERICA PER GLI ERRORI ---
            except Exception as e: # Cattura tutti gli errori generici durante il parsing/elaborazione GPX
                flash(f'Errore durante l\'elaborazione del file GPX: {e}', 'danger')
                print(f"Errore generico upload_gpx: {e}") # Log dell'errore sul server
                return redirect(url_for('main.upload_gpx'))
        else:
            flash('Formato file non valido. Si prega di caricare un file .gpx.', 'warning')
            return redirect(url_for('main.upload_gpx'))
            
    # Se è una richiesta GET, mostra semplicemente il form di upload
    return render_template('upload_gpx.html')

@main.route('/api/save-gpx-item', methods=['POST'])
@login_required
def save_gpx_item():
    """
    API endpoint per salvare un'attività o un percorso da dati GPX estratti.
    """
    # --- DEBUG: Stampa i dati ricevuti ---
    print("=== SAVE GPX ITEM - DATI RICEVUTI ===")
    
    if not request.is_json:
        print("ERRORE: Richiesta non è JSON")
        return jsonify({"status": "error", "message": "Richiesta deve essere JSON."}), 400
    
    data = request.get_json()
    
    # Stampa i dati per debug
    print(f"Filename: {data.get('filename')}")
    print(f"Name: {data.get('name')}")
    print(f"Distance: {data.get('distance')} (Tipo: {type(data.get('distance'))})")
    print(f"Duration: {data.get('duration')}")
    print(f"Activity Type: {data.get('activity_type')}")
    print(f"Item Type: {data.get('item_type')}")
    print(f"Points JSON presente: {bool(data.get('points_json'))}")
    print("=====================================")
    
    # --- Estrazione Dati ---
    filename = data.get('filename')
    name = data.get('name')
    description = data.get('description')
    activity_type = data.get('activity_type')
    distance_str = data.get('distance')
    duration_str = data.get('duration')
    points_json = data.get('points_json')
    item_type = data.get('item_type')
    route_id_for_activity = data.get('route_id')
    
    # --- Validazione Base ---
    if not name:
        return jsonify({"status": "error", "message": "Il nome è obbligatorio."}), 400
    
    if not activity_type:
        return jsonify({"status": "error", "message": "Il tipo di attività è obbligatorio."}), 400
    
    if not points_json or points_json == '[]':
        return jsonify({"status": "error", "message": "Il tracciato non contiene punti validi."}), 400
    
    if not item_type or item_type not in ['activity', 'route']:
        return jsonify({"status": "error", "message": "Tipo di elemento non valido."}), 400

    try:
        # --- Conversione Distanza ---
        distance_km = 0.0
        if distance_str and distance_str != 'N/D' and distance_str != '':
            try:
                distance_clean = str(distance_str).strip()
                distance_km = float(distance_clean)
                print(f"Distanza convertita: {distance_km} km")
            except (ValueError, TypeError) as e:
                print(f"Errore conversione distanza '{distance_str}': {e}")
                distance_km = 0.0
        else:
            print("Distanza non valida o vuota, uso 0.0")
        
        # --- Conversione Durata ---
        duration_sec = 0
        if duration_str and duration_str != 'N/D' and duration_str != '':
            try:
                duration_clean = str(duration_str).strip()
                duration_sec = int(float(duration_clean))
                print(f"Durata convertita: {duration_sec} secondi")
            except (ValueError, TypeError) as e:
                print(f"Errore conversione durata '{duration_str}': {e}")
                duration_sec = 0
        else:
            print("Durata non valida o vuota, uso 0")
        
        # --- CONVERSIONE A GEOJSON ---
        try:
            points = json.loads(points_json)
            
            # Crea geometria GeoJSON LineString
            geojson_geometry = {
                "type": "LineString",
                "coordinates": [[point['lon'], point['lat']] for point in points]  # [lon, lat] ordine GeoJSON
            }
            
            # Feature GeoJSON completa (opzionale)
            geojson_feature = {
                "type": "Feature",
                "geometry": geojson_geometry,
                "properties": {
                    "name": name,
                    "activity_type": activity_type,
                    "distance_km": distance_km,
                    "duration_sec": duration_sec
                }
            }
            
            print(f"✅ Convertito in GeoJSON: {len(points)} punti")
            print(f"✅ Primo punto GeoJSON: {geojson_geometry['coordinates'][0]}")
            
        except Exception as e:
            print(f"❌ Errore conversione GeoJSON: {e}")
            return jsonify({"status": "error", "message": "Errore nella conversione del tracciato."}), 400
        
        # --- Creazione Oggetto ---
        user_id = current_user.id
        
        if item_type == 'activity':
            # Crea una nuova Attività
            new_activity = Activity(
                user_id=user_id,
                route_id=route_id_for_activity,
                name=name,
                description=description or "",
                activity_type=activity_type,
                gps_track=points_json,  # Mantieni originale per Activity
                distance=distance_km,
                duration=duration_sec,
                avg_speed= (distance_km / (duration_sec / 3600.0)) if duration_sec > 0 else 0.0
            )
            db.session.add(new_activity)
            db.session.commit()
            
            print(f"Attività salvata con ID: {new_activity.id}")
            
            return jsonify({
                "status": "success", 
                "message": "Attività salvata con successo!", 
                "item_id": new_activity.id, 
                "item_type": "activity"
            })
            
        elif item_type == 'route':
            # Crea un nuovo Percorso CON GEOJSON
            new_route = Route(
                name=name,
                description=description or "",
                coordinates=json.dumps(geojson_geometry),   # ⚠️ SALVA GEOJSON invece del JSON originale
                distance_km=distance_km,
                duration=duration_sec,
                activity_type=activity_type,
                created_by=user_id
            )
            db.session.add(new_route)
            db.session.commit()
            
            # DEBUG per verificare
            print(f"✅ Percorso salvato con ID: {new_route.id}")
            print(f"✅ Distance_km salvata: {new_route.distance_km} km")
            print(f"✅ Coordinate salvate come GeoJSON: {type(new_route.coordinates)}")
            
            return jsonify({
                "status": "success", 
                "message": "Percorso salvato con successo!", 
                "item_id": new_route.id, 
                "item_type": "route"
            })
            
        else:
            return jsonify({"status": "error", "message": "Tipo di elemento non valido."}), 400

    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO in save_gpx_item: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return jsonify({"status": "error", "message": f"Errore interno del server: {str(e)}"}), 500
        

@main.route('/api/activity/<int:activity_id>/like', methods=['POST'])
@login_required
@csrf.exempt
def like_activity(activity_id):
    activity = Activity.query.get_or_404(activity_id)

    like = ActivityLike.query.filter_by(user_id=current_user.id, activity_id=activity_id).first()
    if like:
        db.session.delete(like)
        action = 'unliked'
    else:
        new_like = ActivityLike(user_id=current_user.id, activity_id=activity_id)
        db.session.add(new_like)
        action = 'liked'

    db.session.commit()

    return jsonify({
        'status': 'success',
        'action': action,
        'likes_count': activity.likes.count()
    })


# In app/main/routes.py

@main.route('/tag/<string:tag_name>')
def tag_search(tag_name):
    """
    Mostra tutti i post che contengono un determinato hashtag.
    """
    tag = Tag.query.filter(func.lower(Tag.name) == tag_name.lower()).first_or_404()
    
    # Accediamo ai post tramite la relazione di backref e li ordiniamo
    posts = tag.posts.order_by(Post.created_at.desc()).all()
    
    # Arricchiamo i post con le info sui like (codice che già conosci)
    if current_user.is_authenticated:
        post_ids = [p.id for p in posts]
        if post_ids:
            liked_post_ids = {like.post_id for like in PostLike.query.filter(PostLike.user_id == current_user.id, PostLike.post_id.in_(post_ids)).all()}
            for post in posts:
                post.current_user_liked = post.id in liked_post_ids
    
    return render_template('tag_search.html', tag=tag, posts=posts, is_homepage=False)



# ... (le tue altre rotte) ...

@main.route('/post-comment/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_post_comment(comment_id):
    comment = PostComment.query.get_or_404(comment_id)
    
    # Sicurezza: l'utente può modificare solo i propri commenti
    if comment.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Non autorizzato'}), 403

    new_content = request.form.get('content')
    if not new_content or not new_content.strip():
        return jsonify({'status': 'error', 'message': 'Il commento non può essere vuoto.'}), 400
    
    # Processiamo di nuovo il contenuto per eventuali nuove menzioni/hashtag
    processed_content, _ = parse_mentions(new_content)
    # Potresti voler ri-eseguire anche il parsing degli hashtag qui
    # final_content = parse_and_link_hashtags(processed_content, comment.post)
    
    comment.content = processed_content # o final_content
    db.session.commit()
    
    return jsonify({'status': 'success', 'new_content': comment.content})


@main.route('/post-comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_post_comment(comment_id):
    comment = PostComment.query.get_or_404(comment_id)
    
    # Sicurezza: l'utente può eliminare solo i propri commenti
    if comment.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Non autorizzato'}), 403
        
    post = comment.post # Salva il post di riferimento prima di eliminare
    db.session.delete(comment)
    db.session.commit()
    
    return jsonify({
        'status': 'success', 
        'message': 'Commento eliminato',
        'new_comment_count': post.comments.count()
    })


@main.route('/post/<int:post_id>/edit', methods=['POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Sicurezza: solo il proprietario può modificare
    if post.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Non autorizzato'}), 403

    new_content = request.form.get('content')
    if not new_content or not new_content.strip():
        return jsonify({'status': 'error', 'message': 'Il post non può essere vuoto.'}), 400
    
    # Riapplichiamo il parsing per menzioni e hashtag sul nuovo contenuto
    processed_content_mentions, _ = parse_mentions(new_content)
    final_content = parse_and_link_hashtags(processed_content_mentions, post)
    
    post.content = final_content
    db.session.commit()
    
    return jsonify({'status': 'success', 'new_content': post.content})


@main.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Sicurezza: solo il proprietario può eliminare
    if post.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Non autorizzato'}), 403
        
    db.session.delete(post)
    db.session.commit()
    
    return jsonify({'status': 'success', 'message': 'Post eliminato'})



@main.route('/explore')
@login_required # Decidi tu se renderla accessibile a tutti o solo agli utenti loggati
def explore():
    # Per ora, passiamo solo un titolo. Aggiungeremo i dati tra poco.
    return render_template('explore.html', is_homepage=False)


@main.route('/api/trending_tags')
def trending_tags():
    """
    API che restituisce gli hashtag più utilizzati.
    """
    # Query che conta quanti post sono associati a ogni tag,
    # ordina in modo decrescente e prende i primi 10.
    trending = db.session.query(
        Tag, func.count(post_tags.c.post_id).label('total')
    ).join(
        post_tags
    ).group_by(
        Tag.id
    ).order_by(
        func.count(post_tags.c.post_id).desc()
    ).limit(10).all()

    # Trasformiamo i risultati in un formato JSON semplice
    tags_list = [{'name': tag.name, 'count': total} for tag, total in trending]
    
    return jsonify(tags_list)

@main.route('/api/featured_routes') # o @api.route(...)
def featured_routes():
    """
    API che restituisce una lista di percorsi suggeriti,
    dando priorità a quelli vicini all'utente.
    """
    LIMIT = 6
    routes = []
    
    # 1. Prova a trovare percorsi IN EVIDENZA nella città dell'utente
    if current_user.is_authenticated and current_user.city:
        routes = Route.query.filter_by(
            is_featured=True, 
            classic_city=current_user.city
        ).order_by(Route.created_at.desc()).limit(LIMIT).all()

    # 2. Se non ne trova, prova a trovare percorsi RECENTI nella città dell'utente
    if not routes and current_user.is_authenticated and current_user.city:
        routes = Route.query.filter_by(
            classic_city=current_user.city
        ).order_by(Route.created_at.desc()).limit(LIMIT).all()

    # 3. Se ancora non trova nulla (o l'utente non ha una città),
    #    cerca percorsi IN EVIDENZA a livello globale.
    if not routes:
        routes = Route.query.filter_by(is_featured=True).order_by(Route.created_at.desc()).limit(LIMIT).all()

    # 4. Come ultima risorsa, prendi i percorsi più RECENTI a livello globale.
    if not routes:
        routes = Route.query.order_by(Route.created_at.desc()).limit(LIMIT).all()

    # La logica per creare il JSON rimane la stessa
    routes_list = []
    for route in routes:
        routes_list.append({
            'id': route.id,
            'name': route.name,
            'city': route.classic_city or 'N/D',
            'distance': route.distance_km,
            'activity_type': route.activity_type,
            'creator_username': route.creator.username,
            'url': url_for('main.route_detail', route_id=route.id)
        })
        
    return jsonify(routes_list)


@main.route('/api/suggested_users') # o @api.route(...)
def suggested_users():
    """
    API che restituisce una lista di utenti suggeriti.
    Logica attuale: i 5 utenti con più attività registrate.
    """
    # Escludiamo l'utente corrente dalla lista dei suggerimenti, se loggato
    query = db.session.query(
        User, func.count(Activity.id).label('activity_count')
    ).join(
        Activity
    ).group_by(
        User.id
    )

    if current_user.is_authenticated:
        query = query.filter(User.id != current_user.id)

    suggested = query.order_by(
        func.count(Activity.id).desc()
    ).limit(5).all()

    users_list = []
    for user, activity_count in suggested:
        users_list.append({
            'id': user.id,
            'username': user.username,
            'profile_image': url_for('static', filename=f'profile_pics/{user.profile_image}'),
            'city': user.city,
            'activity_count': activity_count,
            'url': url_for('main.user_profile', user_id=user.id)
        })
        
    return jsonify(users_list)

# In app/main/routes.py

@main.route("/routes/propose-classic", methods=["GET","POST"])
@login_required
def propose_classic_route():
    if request.method == "POST":
        # --- 1. ESTRAZIONE DELLA TRACCIA (Il tuo codice, che è corretto) ---
        coords_geojson_str = None
        distance_km = None

        # Prova a caricare dal file GPX
        if 'gpx_file' in request.files and request.files['gpx_file'].filename != '':
            gpx_file = request.files['gpx_file']
            try:
                gpx_data = gpxpy.parse(gpx_file.stream)
                points = [[p.longitude, p.latitude] for t in gpx_data.tracks for s in t.segments for p in s.points]
                if points:
                    coords_geojson_str = json.dumps({"type": "Feature", "geometry": {"type": "LineString", "coordinates": points}, "properties": {}})
                    distance_km = gpx_data.length_3d() / 1000 if gpx_data.length_3d() else gpx_data.length_2d() / 1000
                else:
                    flash('Il file GPX non contiene dati di percorso validi.', 'danger')
                    return redirect(url_for("main.propose_classic_route")) # Corretto redirect
            except Exception as e:
                flash(f'Errore nella lettura del file GPX: {e}', 'danger')
                return redirect(url_for("main.propose_classic_route")) # Corretto redirect
        
        # Se non c'è GPX, prova a prenderlo dalla mappa disegnata
        elif "coordinates" in request.form and request.form["coordinates"]:
            coords_geojson_str = request.form["coordinates"]
            try:
                geojson_obj = json.loads(coords_geojson_str)
                line_coords = geojson_obj['geometry']['coordinates']
                total_distance_meters = sum(calculate_distance_meters(line_coords[i][1], line_coords[i][0], line_coords[i+1][1], line_coords[i+1][0]) for i in range(len(line_coords) - 1))
                distance_km = total_distance_meters / 1000.0
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                distance_km = None # Lascia che sia il database a gestirlo se necessario

        # Validazione finale: deve esserci una traccia
        if not coords_geojson_str:
            flash('Devi disegnare un percorso sulla mappa o caricare un file GPX.', 'danger')
            return redirect(url_for("main.propose_classic_route"))

        # --- 2. CREAZIONE DI UN UNICO OGGETTO ROUTE CON TUTTI I CAMPI ---
        try:
            new_route = Route(
                # Campi base
                name=request.form["name"],
                description=request.form.get("description"),
                activity_type=request.form.get("activity_type"),
                coordinates=coords_geojson_str,
                created_by=current_user.id,
                distance_km=distance_km,
                
                # Campi "Classici" dal form
                classic_city=request.form.get("classic_city"),
                difficulty=request.form.get("difficulty"),
                landmarks=request.form.get("landmarks"),
                start_location=request.form.get("start_location"),
                end_location=request.form.get("end_location"),
                elevation_gain=request.form.get("elevation_gain", type=int, default=None),
                estimated_time=request.form.get("estimated_time"),
                
                # Stato della proposta
                is_classic=False,  # Sarà l'admin a deciderlo
                classic_status='proposed'
            )
            
            db.session.add(new_route)
            add_prestige(current_user, 'new_route')
            db.session.commit()
            
            flash('Proposta inviata con successo! Verrai notificato quando verrà revisionata.', 'success')
            return redirect(url_for("main.index"))

        except Exception as e:
            db.session.rollback()
            flash(f"Si è verificato un errore durante il salvataggio della proposta: {e}", 'danger')
            return redirect(url_for("main.propose_classic_route"))

    # Metodo GET: mostra semplicemente il form
    return render_template('propose_classic.html', is_homepage=False)



@main.route('/groups')
@login_required
def list_groups():
    page = request.args.get('page', 1, type=int)
    # Mostra i gruppi impaginati
    groups_pagination = Group.query.order_by(Group.name.asc()).paginate(page=page, per_page=10, error_out=False)
    return render_template('list_groups.html', groups_pagination=groups_pagination, is_homepage=False)

@main.route('/groups/new', methods=['GET', 'POST'])
@login_required
def create_group():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        city = request.form.get('city')
        
        if not name:
            flash('Il nome del gruppo è obbligatorio.', 'danger')
            return redirect(url_for('main.create_group'))

        new_group = Group(
            name=name,
            description=description,
            city=city,
            owner_id=current_user.id
        )
        
        # Il creatore diventa automaticamente il primo membro
        new_group.members.append(current_user)
        
        db.session.add(new_group)
        db.session.commit()
        
        flash(f"Gruppo '{name}' creato con successo!", 'success')
        return redirect(url_for('main.group_detail', group_id=new_group.id))
        
    return render_template('create_group.html', is_homepage=False)

@main.route('/group/<int:group_id>')
@login_required
def group_detail(group_id):
    group = Group.query.get_or_404(group_id)

    # Controlliamo lo stato dell'utente corrente in modo efficiente
    is_member = group.members.filter(User.id == current_user.id).first() is not None
    is_owner = group.owner_id == current_user.id
    
    # La logica per i post del gruppo è corretta
    group_posts = group.posts.order_by(Post.created_at.desc()).all()
    if current_user.is_authenticated:
        for post in group_posts:
            post.current_user_liked = post.likes.filter_by(user_id=current_user.id).first() is not None
            
    # La logica per gli eventi è corretta
    now = datetime.utcnow()
    upcoming_events = group.events.filter(Event.event_time >= now).order_by(Event.event_time.asc()).limit(5).all()

    return render_template('group_detail.html', 
                           group=group, 
                           # 'members' non viene più passato
                           is_member=is_member,
                           is_owner=is_owner,
                           group_posts=group_posts,
                           upcoming_events=upcoming_events,
                           is_homepage=False)

@main.route('/group/<int:group_id>/join', methods=['POST'])
@login_required
def join_group(group_id):
    group = Group.query.get_or_404(group_id)
    # Controlla se l'utente è già membro
    if current_user in group.members:
        flash('Sei già un membro di questo gruppo.', 'info')
        return redirect(url_for('main.group_detail', group_id=group.id))

    group.members.append(current_user)
    complete_onboarding_step(current_user, 'joined_group')
    db.session.commit()

    flash(f"Ti sei iscritto con successo a '{group.name}'!", 'success')
    return redirect(url_for('main.group_detail', group_id=group.id))


@main.route('/group/<int:group_id>/leave', methods=['POST'])
@login_required
def leave_group(group_id):
    group = Group.query.get_or_404(group_id)

    # Controlla se l'utente è effettivamente un membro
    if current_user not in group.members:
        flash('Non sei un membro di questo gruppo.', 'info')
        return redirect(url_for('main.group_detail', group_id=group.id))
        
    # Impedisce al proprietario di abbandonare il proprio gruppo (logica da migliorare in futuro)
    if group.owner_id == current_user.id:
        flash('Non puoi abbandonare un gruppo che hai creato.', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))

    group.members.remove(current_user)
    db.session.commit()

    flash(f"Hai abbandonato il gruppo '{group.name}'.", 'success')
    return redirect(url_for('main.list_groups')) # Reindirizziamo alla lista dei gruppi


@main.route('/group/<int:group_id>/events/new', methods=['GET', 'POST'])
@login_required
def create_event(group_id):
    group = Group.query.get_or_404(group_id)
    
    # Sicurezza: solo i membri del gruppo possono creare eventi
    if current_user not in group.members:
        flash('Devi essere un membro del gruppo per creare un evento.', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        event_time_str = request.form.get('event_time')
        location = request.form.get('location')

        if not name or not event_time_str:
            flash('Nome e data/ora dell\'evento sono obbligatori.', 'danger')
            return redirect(url_for('main.create_event', group_id=group.id))

        try:
            # Converte la stringa dal form in un oggetto datetime
            event_time = datetime.strptime(event_time_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Formato data/ora non valido.', 'danger')
            return redirect(url_for('main.create_event', group_id=group.id))
            
        new_event = Event(
            name=name,
            description=description,
            event_time=event_time,
            location=location,
            creator_id=current_user.id,
            group_id=group.id
        )
        
        # Il creatore partecipa automaticamente
        new_event.participants.append(current_user)
        
        db.session.add(new_event)
        db.session.commit()
        
        flash('Evento creato con successo!', 'success')
        return redirect(url_for('main.event_detail', event_id=new_event.id))
        
    return render_template('create_event.html', group=group, is_homepage=False)


@main.route('/event/<int:event_id>')
@login_required
def event_detail(event_id):
    event = Event.query.get_or_404(event_id)
    
    # Sicurezza: per ora, rendiamo gli eventi visibili solo ai membri del gruppo
    if current_user not in event.group.members:
        flash('Devi essere un membro del gruppo per vedere questo evento.', 'warning')
        return redirect(url_for('main.group_detail', group_id=event.group.id))

    participants = event.participants.all()
    is_participating = current_user in participants
    is_creator = event.creator_id == current_user.id
    
    return render_template('event_detail.html', 
                           event=event, 
                           participants=participants, 
                           is_participating=is_participating,
                           is_creator=is_creator,
                           is_homepage=False)


@main.route('/event/<int:event_id>/join', methods=['POST'])
@login_required
def join_event(event_id):
    event = Event.query.get_or_404(event_id)
    
    # Sicurezza aggiuntiva
    if current_user not in event.group.members:
        flash('Devi essere un membro del gruppo per partecipare a questo evento.', 'danger')
        return redirect(url_for('main.group_detail', group_id=event.group.id))

    if current_user not in event.participants:
        event.participants.append(current_user)
        db.session.commit()
        flash('Partecipazione confermata!', 'success')
    else:
        flash('Stai già partecipando a questo evento.', 'info')
        
    return redirect(url_for('main.event_detail', event_id=event.id))


@main.route('/event/<int:event_id>/leave', methods=['POST'])
@login_required
def leave_event(event_id):
    event = Event.query.get_or_404(event_id)
    
    if current_user in event.participants:
        # Impedisce al creatore di annullare la propria partecipazione (potrebbe cancellare l'evento)
        if event.creator_id == current_user.id:
            flash('L\'organizzatore non può annullare la propria partecipazione.', 'warning')
            return redirect(url_for('main.event_detail', event_id=event.id))
            
        event.participants.remove(current_user)
        db.session.commit()
        flash('Hai annullato la tua partecipazione.', 'success')
    else:
        flash('Non stavi partecipando a questo evento.', 'info')

    return redirect(url_for('main.event_detail', event_id=event.id))


@main.route('/group/<int:group_id>/manage', methods=['GET', 'POST'])
@login_required
def manage_group(group_id):
    group = Group.query.get_or_404(group_id)
    
    # Sicurezza: solo il proprietario può gestire il gruppo
    if group.owner_id != current_user.id:
        flash('Non hai i permessi per gestire questo gruppo.', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))

    if request.method == 'POST':
        # Aggiorna i dati del gruppo
        group.name = request.form.get('name', group.name)
        group.description = request.form.get('description', group.description)
        group.city = request.form.get('city', group.city)
        
        # Aggiungi qui la logica per l'upload dell'immagine del gruppo se vuoi
        
        db.session.commit()
        flash('Le impostazioni del gruppo sono state aggiornate.', 'success')
        return redirect(url_for('main.manage_group', group_id=group.id))
        
    members = group.members.all()
    return render_template('manage_group.html', group=group, members=members, is_homepage=False)


@main.route('/group/<int:group_id>/remove_member/<int:user_id>', methods=['POST'])
@login_required
def remove_member(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    user_to_remove = User.query.get_or_404(user_id)
    
    # Sicurezza: solo il proprietario può rimuovere membri
    if group.owner_id != current_user.id:
        flash('Non hai i permessi per eseguire questa azione.', 'danger')
        return redirect(url_for('main.group_detail', group_id=group.id))
        
    # Sicurezza: non si può rimuovere il proprietario
    if user_to_remove.id == group.owner_id:
        flash('Il proprietario non può essere rimosso dal gruppo.', 'warning')
        return redirect(url_for('main.manage_group', group_id=group.id))
        
    if user_to_remove in group.members:
        group.members.remove(user_to_remove)
        db.session.commit()
        flash(f"{user_to_remove.username} è stato rimosso dal gruppo.", 'success')
    else:
        flash('Questo utente non è un membro del gruppo.', 'info')
        
    return redirect(url_for('main.manage_group', group_id=group.id))

@main.route('/bets')
@login_required
def bets_hall():
    """
    Pagina dedicata alle scommesse (la "Sala Scommesse").
    """
    # --- 1. SCOMMESSE PERSONALI (Logica che già hai) ---
    my_bets_won = Bet.query.filter_by(winner_id=current_user.id).order_by(Bet.status.asc(), Bet.created_at.desc()).all()
    my_bets_lost = Bet.query.filter_by(loser_id=current_user.id).order_by(Bet.status.asc(), Bet.created_at.desc()).all()

    # --- 2. SCOMMESSE RECENTI DELLA COMMUNITY ---
    # Recuperiamo le ultime 10 scommesse concluse (pagate)
    recent_community_bets = Bet.query.filter(
        Bet.status == 'paid'
    ).order_by(
        Bet.paid_at.desc()
    ).limit(10).all()

    return render_template('bets_hall.html', 
                           my_bets_won=my_bets_won,
                           my_bets_lost=my_bets_lost,
                           recent_community_bets=recent_community_bets,
                           is_homepage=False)

@main.route('/api/search_users')
@login_required
def search_users_api():
    query = request.args.get('q', '', type=str)
    
    # Restituisci una lista vuota se la ricerca è troppo breve per evitare risultati inutili
    if len(query) < 2:
        return jsonify([])
    
    # Cerca utenti il cui username inizia con la query (case-insensitive)
    # e che non siano l'utente corrente
    users = User.query.filter(
        User.username.ilike(f'{query}%'),
        User.id != current_user.id
    ).limit(5).all()
    
    # Formattiamo i dati nel modo specifico che Tribute.js si aspetta:
    # una lista di oggetti con chiavi 'key' (il testo da mostrare) e 'value' (il testo da inserire).
    users_list = [
        {
            'key': user.username, 
            'value': user.username,
            'avatar': url_for('static', filename=f'profile_pics/{user.profile_image}')
        } 
        for user in users
    ]
    
    return jsonify(users_list)


# /test/run_close_challenges

@main.route('/test/run_close_challenges')
@login_required # Mettiamola dietro login per sicurezza
def run_close_challenges_test():
    """
    Esegue manualmente la funzione per chiudere le sfide scadute.
    """
    print("\n--- [DEBUG] ESECUZIONE MANUALE DI close_expired_challenges ---")
    try:
        # Chiamiamo la funzione importata
        closed_count = close_expired_challenges()
        
        if closed_count > 0:
            message = f"✅ Esecuzione completata. Chiuse {closed_count} sfide."
            flash(message, 'success')
        else:
            message = "ℹ️ Esecuzione completata. Nessuna sfida scaduta da chiudere."
            flash(message, 'info')
            
        print(f"--- [DEBUG] FINE ESECUZIONE MANUALE --- \n")
        return redirect(url_for('main.challenges_list'))

    except Exception as e:
        import traceback
        error_message = f"❌ Errore durante l'esecuzione manuale: {e}\n{traceback.format_exc()}"
        print(error_message)
        flash('Si è verificato un errore. Controlla il log del server.', 'danger')
        return redirect(url_for('main.challenges_list'))
    
@main.route('/api/post/<int:post_id>/likers')
@login_required 
def get_post_likers(post_id):
    post = Post.query.get_or_404(post_id)
    
    # post.likes.all() restituisce una lista di oggetti PostLike
    likes = post.likes.all() 

    likers_data = []
    # Cicliamo su ogni oggetto 'like' (di tipo PostLike)
    for like in likes:
        # Da ogni 'like', accediamo all'utente correlato tramite la relazione (es. like.user)
        user_object = like.user  # Assumendo che la relazione si chiami 'user'
        
        likers_data.append({
            'id': user_object.id,  # Prendiamo l'ID dell'utente
            'username': user_object.username, # Prendiamo lo username dell'utente
            'profile_image_url': url_for('static', filename=f'profile_pics/{user_object.profile_image}'),
            'profile_url': url_for('main.user_profile', user_id=user_object.id)
        })
        
    return jsonify(likers_data)


@main.route('/api/post/<int:post_id>/add_comment', methods=['POST'])
@login_required
def add_comment_to_post_ajax(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')

    if not content or not content.strip():
        return jsonify({'status': 'error', 'message': 'Il commento non può essere vuoto.'}), 400

    processed_content, mentioned_users = parse_mentions(content)

    new_comment = PostComment(
        user_id=current_user.id,
        post_id=post_id,
        content=processed_content
    )
    db.session.add(new_comment)
    add_prestige(current_user, 'new_comment')

    for user in mentioned_users:
        if user.id != current_user.id:
            notification = Notification(
                recipient_id=user.id,
                actor_id=current_user.id,
                action='mention_in_comment',
                object_id=post.id,
                object_type='post'
            )
            db.session.add(notification)

    db.session.commit()

    comment_html = render_template(
        'partials/feed_items/_comment.html',
        comment=new_comment,
        PostComment=PostComment
    )

    return jsonify({
        'status': 'success',
        'message': 'Commento aggiunto!',
        'comment_html': comment_html,
        'new_comment_count': post.comments.count()
    })


# --- NUOVE ROUTE PER LA MODIFICA DELL'ATTIVITÀ ---

@main.route("/activity/<int:activity_id>/edit", methods=["GET"])
@login_required # Richiede che l'utente sia loggato
def edit_activity(activity_id):
    """
    Visualizza il modulo per modificare i dettagli di un'attività.
    """
    activity = Activity.query.get_or_404(activity_id)

    # Controllo autorizzazioni: solo il proprietario dell'attività può modificarla.
    if activity.user_id != current_user.id:
        flash("Non hai il permesso di modificare questa attività.", "danger")
        # Reindirizza alla pagina di dettaglio dell'attività
        return redirect(url_for("main.activity_detail", activity_id=activity_id))

    # Se l'utente è autorizzato, renderizza il template di modifica
    return render_template("edit_activity.html", activity=activity)


@main.route("/activity/<int:activity_id>/edit", methods=["POST"])
@login_required # Richiede che l'utente sia loggato
def update_activity(activity_id):
    """
    Gestisce l'invio del modulo di modifica e aggiorna l'attività nel database.
    """
    activity = Activity.query.get_or_404(activity_id)

    # Controllo autorizzazioni: solo il proprietario dell'attività può modificarla.
    if activity.user_id != current_user.id:
        flash("Non hai il permesso di modificare questa attività.", "danger")
        return redirect(url_for("main.activity_detail", activity_id=activity_id))

    # Recupera i dati dal form inviato
    new_name = request.form.get("name")
    new_description = request.form.get("description")

    # Aggiorna i campi dell'attività nel modello
    activity.name = new_name
    activity.description = new_description

    try:
        db.session.commit()
        flash("Attività aggiornata con successo!", "success")
        # Reindirizza alla pagina di dettaglio dell'attività, dove si vedranno le modifiche
        return redirect(url_for("main.activity_detail", activity_id=activity_id))
    except Exception as e:
        db.session.rollback() # Annulla le modifiche in caso di errore
        flash(f"Errore durante l'aggiornamento dell'attività: {e}", "danger")
        # Reindirizza di nuovo al modulo di modifica, passando i dati inseriti dall'utente
        # per evitare perdite di dati.
        return render_template("edit_activity.html", activity=activity, name=new_name, description=new_description)

# --- FINE NUOVE ROUTE ---