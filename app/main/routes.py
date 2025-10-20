# app/main/routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import User, Route, Activity, ActivityLike, Challenge, Comment, Like, RouteRecord, Badge, UserBadge, Notification, ChallengeInvitation, Bet, Post, PostComment, PostLike
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
from .services import get_community_feed_items # Aggiungi l'import
import re # <-- Aggiungi questo import all'inizio del file

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
        db.session.add(badge_post)
        # --- FINE NUOVO CODICE ---
        
        db.session.commit() # Questo salverà sia UserBadge che il nuovo Post
        flash(f'Congratulazioni! Hai ottenuto il badge: "{badge.name}"!', 'info')
        return True
    return False

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Route Principali e Social ---

# In app/main/routes.py

# Assicurati di avere questo import all'inizio del file
from sqlalchemy import case, func

# ... (gli altri import e le altre rotte) ...

@main.route('/')
def index():
    user_city = current_user.city if current_user.is_authenticated else None
    
    # --- LOGICA FEED DELLA COMMUNITY (VERSIONE CORRETTA E COMPLETA) ---
    
    PER_PAGE = 5 # Quanti post per pagina
    
    # 1. Definiamo l'ordinamento speciale per mettere in evidenza i post admin
    special_post_order = case(
        (Post.post_category.in_(['admin_announcement', 'weekly_tip']), 0),
        else_=1
    )

    # 2. Eseguiamo la query per la PRIMA PAGINA del feed con l'ordinamento speciale
    posts_pagination = Post.query.options(joinedload(Post.user)).order_by(
        special_post_order, 
        Post.created_at.desc()
    ).paginate(page=1, per_page=PER_PAGE, error_out=False)
    
    community_posts = posts_pagination.items # Questa è la lista dei primi 5 post (o meno)

    # 3. Arricchiamo i post con le informazioni sui "Mi piace" dell'utente corrente
    if current_user.is_authenticated:
        post_ids = [p.id for p in community_posts]
        if post_ids: # Esegui la query solo se ci sono post da controllare
            liked_post_ids = {like.post_id for like in PostLike.query.filter(PostLike.user_id == current_user.id, PostLike.post_id.in_(post_ids)).all()}
            for post in community_posts:
                post.current_user_liked = post.id in liked_post_ids
        else: # Se non ci sono post, non c'è nulla da fare
             for post in community_posts:
                post.current_user_liked = False
    else:
        for post in community_posts:
            post.current_user_liked = False

    # --- FINE LOGICA FEED ---


    # --- ALTRI DATI PER LA HOME PAGE (il tuo codice originale, che va bene) ---
    
    recent_activities = Activity.query.order_by(Activity.created_at.desc()).limit(5).all()
    
    top_users_data = (
        db.session.query(User, func.sum(Activity.distance).label('total_distance'))
        .join(Activity).group_by(User).order_by(func.sum(Activity.distance).desc()).limit(5).all()
    )
    top_users = [{'user': user, 'total_distance': total_distance or 0} for user, total_distance in top_users_data]
    
    recent_challenges_in_city = []
    if user_city:
        challenges_query = db.session.query(Challenge).join(Route).filter(
            Route.classic_city == user_city,
            Challenge.end_date >= datetime.utcnow(),
            Challenge.is_active == True,
            Challenge.bet_type != 'none'
        ).order_by(Challenge.start_date.asc()).limit(3).all()
        recent_challenges_in_city = challenges_query
        
        
    # --- PASSAGGIO DATI AL TEMPLATE ---
    return render_template("index.html", 
                           user_city=user_city, 
                           is_homepage=True, 
                           recent_activities=recent_activities,
                           recent_challenges_in_city=recent_challenges_in_city,
                           top_users=top_users,
                           community_posts=community_posts, # Passiamo i post già pronti
                           has_next_feed_page=posts_pagination.has_next, # Passiamo l'info per il pulsante
                           total_posts=posts_pagination.total, # <-- AGGIUNGI QUESTO
                           now=datetime.utcnow()
                           )
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
                           Route=Route)


@main.route('/user/edit', methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        new_username = request.form.get("username")
        new_email = request.form.get("email")
        new_password = request.form.get("password")
        new_city = request.form.get("city")
        
        if 'profile_image' in request.files and request.files['profile_image'].filename != '':
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                filename = str(uuid.uuid4()) + os.path.splitext(file.filename)[1]
                filepath = os.path.join(current_app.config['PROFILE_PICS_FOLDER'], filename)  # <-- cambio qui
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
            current_user.set_password(new_password)
        
        if new_city is not None:
            current_user.city = new_city

        db.session.commit()
        flash('Profilo aggiornato con successo!', 'success')
        return redirect(url_for('main.user_profile', user_id=current_user.id))

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
        db.session.commit()
        
        flash('Percorso creato con successo!', 'success')
        return redirect(url_for("main.index"))
    return render_template('new_route.html', is_homepage=False)

@main.route("/route/<int:route_id>", methods=["GET", "POST"])
def route_detail(route_id):
    route = Route.query.options(joinedload(Route.creator)).get_or_404(route_id)
    route_geojson_data = json.dumps(json.loads(route.coordinates)) if route.coordinates else "{}"

    challenges_for_route = Challenge.query.filter(Challenge.route_id == route.id, Challenge.end_date >= datetime.utcnow()).order_by(Challenge.start_date).all()

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

    comments = Comment.query.options(joinedload(Comment.author), selectinload(Comment.likes)).filter_by(route_id=route.id).order_by(Comment.created_at.desc()).all()
    
    comments_with_like_info = [{
        'comment': c,
        'like_count': len(c.likes),
        'has_liked': any(like.user_id == current_user.id for like in c.likes) if current_user.is_authenticated else False
    } for c in comments]
    
    route_record = RouteRecord.query.filter_by(route_id=route.id).order_by(RouteRecord.duration.asc()).first()
    top_5_activities_for_route = Activity.query.filter_by(route_id=route.id).order_by(Activity.duration.asc()).limit(5).all()

    return render_template("route_detail.html", route=route, route_geojson_data=route_geojson_data,
                           challenges_for_route=challenges_for_route, comments_with_like_info=comments_with_like_info,
                           route_record=route_record, top_5_activities_for_route=top_5_activities_for_route, is_homepage=False)

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
    return jsonify({'status': 'success', 'action': action, 'new_like_count': len(comment.likes), 'comment_id': comment_id})

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
        
        # === NUOVI CAMPI ===
        challenge_type = request.form.get("challenge_type", "open")
        bet_type = request.form.get("bet_type", "none")
        custom_bet = request.form.get("custom_bet", "")
        invited_friends = request.form.getlist("invited_friends")  # Lista di user_id
        # === FINE NUOVI CAMPI ===
        
        # --- VALIDAZIONE OBBLIGATORIA PER route_id ---
        if not route_id_str:
            flash('Devi selezionare un percorso per creare la sfida.', 'warning')
            return redirect(url_for('main.create_challenge'))
        
        try:
            route_id = int(route_id_str)
        except ValueError:
            flash('ID del percorso non valido.', 'danger')
            return redirect(url_for('main.create_challenge'))

        # Verifica che la route esista nel DB
        route = Route.query.get(route_id)
        if not route:
            flash(f'Il percorso selezionato (ID: {route_id}) non esiste.', 'danger')
            return redirect(url_for('main.create_challenge'))
        # --- FINE VALIDAZIONE route_id ---

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        except ValueError:
            flash('Formato data non valido.', 'danger')
            return redirect(url_for('main.create_challenge'))
        
        if start_date >= end_date:
            flash('La data di inizio deve essere precedente alla data di fine.', 'danger')
            return redirect(url_for('main.create_challenge'))

        # === NUOVA VALIDAZIONE: PER SFIDE CHIUSE ===
        if challenge_type == "closed" and not invited_friends:
            flash('Per le sfide chiuse devi invitare almeno un amico.', 'danger')
            return redirect(url_for('main.create_challenge'))

        # === GESTIONE VALORE SCOMMESSA ===
        bet_value = get_bet_value(bet_type, custom_bet)
        
        # Crea la sfida con tutti i campi
        new_challenge = Challenge(
            name=challenge_name, 
            route_id=route_id,
            start_date=start_date, 
            end_date=end_date, 
            created_by=current_user.id,
            # === NUOVI CAMPI ===
            challenge_type=challenge_type,
            bet_type=bet_type,
            custom_bet=custom_bet,
            bet_value=bet_value
        )
        
        try:
            db.session.add(new_challenge)
            db.session.flush()  # Ottieni l'ID della sfida per le invitation
            
            # === GESTIONE INVITI PER SFIDE CHIUSE ===
            if challenge_type == "closed" and invited_friends:
                for friend_id in invited_friends:
                    try:
                        friend_id_int = int(friend_id)
                        # Verifica che l'utente esista
                        friend = User.query.get(friend_id_int)
                        if friend:
                            invitation = ChallengeInvitation(
                                challenge_id=new_challenge.id,
                                invited_user_id=friend_id_int
                            )
                            db.session.add(invitation)
                            
                            # === CODICE AGGIUNTO: CREA NOTIFICA ===
                            notification = Notification(
                                recipient_id=friend_id_int,
                                actor_id=current_user.id,  # Chi ha creato la sfida
                                action='challenge_invitation',
                                object_id=new_challenge.id,
                                object_type='challenge'
                            )
                            db.session.add(notification)
                            # === FINE CODICE AGGIUNTO ===
                            
                    except (ValueError, TypeError):
                        continue  # Salta ID non validi
            
            db.session.commit()
            
            # Messaggio di successo personalizzato
            success_message = f'Sfida "{challenge_name}" creata con successo!'
            if challenge_type == "closed":
                success_message += f' {len(invited_friends)} amici invitati.'
            if bet_type != "none":
                success_message += f' Scommessa: {bet_value}'
                
            flash(success_message, 'success')
            return redirect(url_for('main.index'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Errore durante la creazione della sfida: {str(e)}', 'danger')
            return redirect(url_for('main.create_challenge'))
        
    # Metodo GET
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

        # Manteniamo i parametri per il redirect in caso di errore
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
                # --- FINE NUOVO CODICE ---
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
    # Anche qui potremmo usare una funzione simile se il formato potesse variare
    route_geojson_data = None
    if activity.route_activity and activity.route_activity.coordinates:
        try:
            route_geojson_data = json.loads(activity.route_activity.coordinates)
        except Exception as e:
            print(f"Error parsing route coordinates: {e}")
    
    # --- GESTIONE GEOJSON DELL'ATTIVITÀ CON LA NUOVA FUNZIONE ---
    print("Parsing activity GPS track...")
    activity_geojson_data = parse_gps_to_geojson(activity.gps_track)
    
    if activity_geojson_data:
        print(f"Successfully parsed GPS track. Coordinates count: {len(activity_geojson_data['coordinates'])}")
    else:
        print("Failed to parse GPS track.")
        
    print("=======================\n")
    
    return render_template("activity_detail.html",
                           activity=activity, 
                           user=activity.user_activity, 
                           route=activity.route_activity,
                           challenge=activity.challenge_info,
                           activity_geojson_data=activity_geojson_data, 
                           route_geojson_data=route_geojson_data, 
                           is_homepage=False)

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
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all', type=str)
    now = datetime.utcnow()
    
    # Query base per sfide aperte a tutti
    query = Challenge.query.filter_by(challenge_type='open')
    
    if status_filter == 'active':
        query = query.filter(Challenge.end_date >= now, Challenge.is_active == True)
    elif status_filter == 'finished':
        query = query.filter(Challenge.end_date < now, Challenge.is_active == False)
    elif status_filter == 'closed_only':
        query = Challenge.query.filter_by(challenge_type='closed')
    # 'all' mostra tutto
    
    pagination = query.order_by(Challenge.start_date.desc()).paginate(page=page, per_page=5, error_out=False)

    # Sfide chiuse a cui l'utente è invitato (sempre visibili)
    invited_challenges = Challenge.query.join(ChallengeInvitation)\
                                       .filter(
                                           Challenge.challenge_type == 'closed',
                                           ChallengeInvitation.invited_user_id == current_user.id,
                                           ChallengeInvitation.status == 'pending'
                                       )\
                                       .order_by(Challenge.created_at.desc())\
                                       .all()

    # Sfide create dall'utente (sempre visibili)
    my_challenges = Challenge.query.filter_by(created_by=current_user.id)\
                                  .order_by(Challenge.created_at.desc())\
                                  .all()

    return render_template("challenges_list.html", 
                         challenges_pagination=pagination, 
                         challenges=pagination.items, 
                         invited_challenges=invited_challenges,
                         my_challenges=my_challenges,
                         status_filter=status_filter,
                         now=now,
                         is_homepage=False)

@main.route("/leaderboards/total_distance")
def leaderboard_total_distance():
    # Query: somma totale delle distanze per utente
    results = (
        db.session.query(
            User,
            func.sum(Activity.distance).label('total_distance')
        )
        .join(Activity)
        .group_by(User)
        .order_by(func.sum(Activity.distance).desc())
        .limit(20)
        .all()
    )

    # Conversione in dizionari per un accesso più comodo nel template
    leaderboard_data = [
        {
            'id': user.id,
            'username': user.username,
            'profile_image': user.profile_image,
            'total_distance': total_distance or 0
        }
        for user, total_distance in results
    ]

    return render_template(
        "leaderboard_total_distance.html",
        leaderboard_data=leaderboard_data,
        is_homepage=False
    )


@main.route("/leaderboards/most_routes")
def leaderboard_most_routes():
    # Query: conteggio totale dei percorsi creati per utente
    results = (
        db.session.query(
            User,
            func.count(Route.id).label('total_routes_created')
        )
        .join(Route, User.id == Route.created_by)
        .group_by(User)
        .order_by(func.count(Route.id).desc())
        .limit(20)
        .all()
    )

    # Conversione in dizionari per compatibilità con i template
    leaderboard_data = [
        {
            'id': user.id,
            'username': user.username,
            'profile_image': user.profile_image,
            'total_routes_created': total_routes_created or 0
        }
        for user, total_routes_created in results
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
    # DEBUG: mostra tutte le notifiche
    all_notifications = Notification.query.filter_by(recipient_id=current_user.id).all()
    print(f"📢 DEBUG: Notifiche per {current_user.username}: {len(all_notifications)}")
    
    for n in all_notifications:
        print(f"📢 DEBUG: Notifica ID: {n.id}, Action: {n.action}, Object: {n.object_id}")

    # Recupera le notifiche ordinate
    user_notifications = current_user.notifications.order_by(Notification.timestamp.desc()).all()
    
    # Conta le notifiche non lette
    unread_count = Notification.query.filter_by(recipient_id=current_user.id, read=False).count()
    
    notification_messages = []
    
    for n in user_notifications:
        message = ""
        link = url_for('main.my_bets')  # Default
        icon = "🔔"  # Default icon
        bg_color = "bg-secondary"  # Default background
        
        print(f"📝 DEBUG: Processing notification: {n.action} - {n.object_id}")
        
        if n.action == 'new_follower':
            message = f"<strong>{n.actor.username}</strong> ha iniziato a seguirti."
            link = url_for('main.user_profile', user_id=n.actor_id)
            icon = "👥"
            bg_color = "bg-info"
        
        elif n.action == 'like_activity':
            activity = Activity.query.get(n.object_id)
            if activity:
                message = f"A <strong>{n.actor.username}</strong> piace la tua attività su <em>{activity.route_activity.name}</em>."
                link = url_for('main.activity_detail', activity_id=activity.id)
                icon = "❤️"
                bg_color = "bg-danger"
            else:
                message = f"A <strong>{n.actor.username}</strong> piace una tua attività che è stata rimossa."
                icon = "❤️"
                bg_color = "bg-secondary"
        
        elif n.action == 'challenge_invitation':
            challenge = Challenge.query.get(n.object_id)
            if challenge:
                message = f"<strong>{n.actor.username}</strong> ti ha sfidato in: <em>{challenge.name}</em>"
                link = url_for('main.challenge_detail', challenge_id=challenge.id)
                icon = "🎯"
                bg_color = "bg-warning"
            else:
                message = f"<strong>{n.actor.username}</strong> ti ha invitato a una sfida che è stata rimossa."
                icon = "🎯"
                bg_color = "bg-secondary"
        
        elif n.action == 'challenge_accepted':
            challenge = Challenge.query.get(n.object_id)
            if challenge:
                message = f"<strong>{n.actor.username}</strong> ha accettato la tua sfida: <em>{challenge.name}</em>"
                link = url_for('main.challenge_detail', challenge_id=challenge.id)
                icon = "✅"
                bg_color = "bg-success"
            else:
                message = f"<strong>{n.actor.username}</strong> ha accettato una tua sfida che è stata rimossa."
                icon = "✅"
                bg_color = "bg-secondary"
        
        elif n.action == 'bet_won':
            challenge = Challenge.query.get(n.object_id)
            if challenge:
                message = f"🎉 Hai vinto una scommessa! <strong>{n.actor.username}</strong> ti deve: <em>{challenge.bet_value}</em>"
                # CERCA LA SCOMMESSA CORRELATA
                bet = Bet.query.filter_by(challenge_id=challenge.id, winner_id=current_user.id).first()
                if bet:
                    link = url_for('main.bet_details', bet_id=bet.id)
                    print(f"✅ DEBUG: Trovata scommessa ID {bet.id} per notifica bet_won")
                else:
                    print(f"❌ DEBUG: Nessuna scommessa trovata per challenge {challenge.id}")
                icon = "🎉"
                bg_color = "bg-success"
            else:
                message = f"🎉 Hai vinto una scommessa contro <strong>{n.actor.username}</strong>!"
                icon = "🎉"
                bg_color = "bg-success"
        
        elif n.action == 'bet_lost':
            challenge = Challenge.query.get(n.object_id)
            if challenge:
                message = f"💸 Hai perso una scommessa! Devi a <strong>{n.actor.username}</strong>: <em>{challenge.bet_value}</em>"
                # CERCA LA SCOMMESSA CORRELATA
                bet = Bet.query.filter_by(challenge_id=challenge.id, loser_id=current_user.id).first()
                if bet:
                    link = url_for('main.bet_details', bet_id=bet.id)
                    print(f"✅ DEBUG: Trovata scommessa ID {bet.id} per notifica bet_lost")
                else:
                    print(f"❌ DEBUG: Nessuna scommessa trovata per challenge {challenge.id}")
                icon = "💸"
                bg_color = "bg-danger"
            else:
                message = f"💸 Hai perso una scommessa contro <strong>{n.actor.username}</strong>"
                icon = "💸"
                bg_color = "bg-danger"
        
        # --- AGGIUNGI QUESTO BLOCCO ELIF ---
        elif n.action == 'mention_in_comment':
            post = Post.query.get(n.object_id)
            if post:
                message = f"<strong>{n.actor.username}</strong> ti ha menzionato in un commento."
                link = url_for('main.post_detail', post_id=post.id) + '#comments' # Linka direttamente ai commenti
                icon = "💬"
                bg_color = "bg-info"
            else:
                message = f"<strong>{n.actor.username}</strong> ti ha menzionato in un commento su un post che è stato rimosso."
                icon = "💬"
                bg_color = "bg-secondary"
        # --- FINE BLOCCO AGGIUNTO ---


        notification_messages.append({
            'message': message,
            'link': link,
            'timestamp': n.timestamp,
            'read': n.read,
            'icon': icon,
            'bg_color': bg_color,
            'id': n.id
        })

    # Segna come lette
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
    if challenge.end_date < datetime.utcnow() and challenge.is_active:
        challenge.is_active = False
        db.session.commit()
        flash('Questa sfida è appena scaduta!', 'info')
        
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


@main.route("/bet/<int:bet_id>/mark_paid", methods=["GET", "POST"])  # ⬅️ AGGIUNGI GET
@login_required
def mark_bet_paid(bet_id):
    """Segna una scommessa come pagata"""
    bet = Bet.query.get_or_404(bet_id)
    
    # Verifica che l'utente corrente sia il perdente
    if bet.loser_id != current_user.id:
        flash('Non puoi segnare come pagata una scommessa che non hai perso.', 'danger')
        return redirect(url_for('main.user_profile', user_id=current_user.id))
    
    # Aggiorna lo stato
    bet.status = 'paid'
    bet.paid_at = datetime.utcnow()
    db.session.commit()

    # --- CREA NOTIFICA PER IL VINCITORE ---
    winner_notification = Notification(
    recipient_id=bet.winner_id,
    actor_id=current_user.id, # L'attore è il perdente che ha pagato
    action='bet_paid',       # Nuova azione per indicare pagamento
    object_id=bet.id,        # L'oggetto è la scommessa
    object_type='bet'        # Tipo di oggetto
)
    db.session.add(winner_notification)
    db.session.commit() # Commit finale per la notifica
    # --- FINE CREAZIONE NOTIFICA ---

    flash(f'✅ Scommessa segnata come pagata! {bet.bet_value} a {bet.winner.username}', 'success')
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

@main.route('/privacy')
def privacy_policy():
    """
    Renderizza la pagina della Privacy Policy.
    Assicurati di avere un template chiamato 'privacy.html' nella tua cartella 'app/templates/'.
    Se non hai un template separato, puoi modificare questa funzione per restituire direttamente HTML.
    """
    print("Debug: Richiesta alla rotta privacy_policy ricevuta.") # Debug print
    return render_template('privacy.html')


# In app/main/routes.py
# --- Funzione helper per controllare il tipo di file ---
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@main.route('/posts/new', methods=['GET', 'POST'])
@login_required
def create_post():
    # Imposta la cartella di upload
    upload_dir = os.path.join(current_app.root_path, 'static', 'posts_images')
    os.makedirs(upload_dir, exist_ok=True)
    current_app.config['UPLOAD_FOLDER'] = upload_dir

    if request.method == 'POST':
        content = request.form.get('content', '') # Default a stringa vuota per sicurezza
        post_type = request.form.get('post_type', 'text')
        image_file = request.files.get('image')
        link = request.form.get('link')

        # Validazione
        if not content.strip() and not image_file and not link:
            flash('Il post non può essere vuoto. Aggiungi testo, immagine o link.', 'warning')
            return redirect(url_for('main.create_post'))

        image_filename = None

        # Gestione Immagine
        if image_file and image_file.filename != '':
            if allowed_file(image_file.filename):
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

        # --- LOGICA MENZIONI E NOTIFICHE ---
        # 1. Analizziamo il contenuto per trovare menzioni e creare i link
        processed_content, mentioned_users = parse_mentions(content)
        # --- FINE LOGICA MENZIONI ---

        # Creazione del Post
        new_post = Post(
            user_id=current_user.id,
            content=processed_content,  # <-- Usiamo il contenuto processato!
            image_url=image_filename,
            post_type=post_type,
            # Se hai il campo 'post_category' nel tuo modello, assicurati di salvarlo
            # post_category=request.form.get('post_category', 'user_post')
        )
        
        # Gestione del link (se il tuo modello ha un campo 'link')
        # if post_type == 'link' and link:
        #    new_post.link = link

        try:
            db.session.add(new_post)
            db.session.flush() # Ottiene l'ID del post prima del commit finale

            # --- CREAZIONE NOTIFICHE ---
            # 2. Creiamo una notifica per ogni utente menzionato
            for user in mentioned_users:
                if user.id != current_user.id:
                    notification = Notification(
                        recipient_id=user.id,
                        actor_id=current_user.id,
                        action='mention_in_post',
                        object_id=new_post.id, # Usiamo l'ID appena ottenuto
                        object_type='post'
                    )
                    db.session.add(notification)
            # --- FINE CREAZIONE NOTIFICHE ---

            db.session.commit()
            flash('Post creato con successo!', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la creazione del post: {e}", 'danger')
            return redirect(url_for('main.create_post'))

    # Metodo GET → mostra il form per creare un post
    return render_template('create_post.html', is_homepage=False)



# --- Assicurati che la funzione allowed_file sia definita (probabilmente in routes.py o una utility) ---
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Aggiungi la route per visualizzare un singolo post (necessaria per i link) ---
@main.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    
    # Recupera i commenti per questo post
    post_comments = PostComment.query.filter_by(post_id=post_id).join(User).order_by(PostComment.created_at.asc()).all()
    
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
                           is_homepage=False)

# --- Esempi di route per commenti e like (da aggiungere) ---

@main.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def add_comment_to_post(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')
    
    if not content:
        flash('Il commento non può essere vuoto.', 'warning')
        return redirect(url_for('main.post_detail', post_id=post_id))
        
    new_comment = PostComment(
        user_id=current_user.id,
        post_id=post_id,
        content=content
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
        
    db.session.commit()
    
    # Restituisce il conteggio usando il metodo .count() di SQLAlchemy
    return jsonify({'status': 'success', 'action': action, 'new_like_count': post.likes.count()})


@main.route('/api/post/<int:post_id>/add_comment', methods=['POST'])
@login_required
def add_comment_to_post_ajax(post_id):
    """
    API endpoint per aggiungere un commento a un post in modo asincrono.
    """
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')
    
    # 1. Validazione
    if not content or not content.strip():
        return jsonify({'status': 'error', 'message': 'Il commento non può essere vuoto.'}), 400
        
    # --- NUOVA LOGICA QUI ---
    # 1. Processiamo il contenuto per trovare menzioni e creare i link
    processed_content, mentioned_users = parse_mentions(content)
    # --- FINE NUOVA LOGICA ---

    new_comment = PostComment(
        user_id=current_user.id,
        post_id=post_id,
        content=processed_content # <-- Usiamo il contenuto processato!
    )
    db.session.add(new_comment)
    
    # --- NUOVA LOGICA PER LE NOTIFICHE ---
    # 2. Creiamo una notifica per ogni utente menzionato (e che non sia se stesso)
    for user in mentioned_users:
        if user.id != current_user.id: # Non notificare te stesso
            notification = Notification(
                recipient_id=user.id,
                actor_id=current_user.id,
                action='mention_in_comment', # Nuova azione!
                object_id=post.id, # L'oggetto è il post a cui appartiene il commento
                object_type='post'
            )
            db.session.add(notification)
    # --- FINE NUOVA LOGICA ---
    
    db.session.commit()
    
    # 3. Renderizzazione del solo HTML per il nuovo commento
    # Passiamo l'oggetto 'comment' appena creato al nostro nuovo template parziale
    comment_html = render_template('partials/feed_items/_comment.html', comment=new_comment)
    
    # 4. Restituzione di una risposta JSON di successo
    return jsonify({
        'status': 'success',
        'message': 'Commento aggiunto!',
        'comment_html': comment_html,
        'new_comment_count': post.comments.count()
    })

@main.route('/api/feed')
def api_feed():
    """
    API endpoint per restituire i post del feed in blocchi impaginati.
    Accetta un parametro 'page' nella query string.
    """
    page = request.args.get('page', 1, type=int)
    PER_PAGE = 5
    
    # --- MODIFICA QUI: APPLICHIAMO LO STESSO ORDINAMENTO SPECIALE ---
    special_post_order = case(
        (Post.post_category.in_(['admin_announcement', 'weekly_tip']), 0),
        else_=1
    )

    posts_pagination = Post.query.options(joinedload(Post.user)).order_by(
        special_post_order, 
        Post.created_at.desc()
    ).paginate(page=page, per_page=PER_PAGE, error_out=False)
    # --- FINE MODIFICA ---
    
    posts = posts_pagination.items
    
    # Il resto della logica per arricchire con i "Mi piace" è corretto
    if current_user.is_authenticated:
        post_ids = [p.id for p in posts]
        if post_ids:
            liked_post_ids = {like.post_id for like in PostLike.query.filter(PostLike.user_id == current_user.id, PostLike.post_id.in_(post_ids)).all()}
            for post in posts:
                post.current_user_liked = post.id in liked_post_ids
        else:
             for post in posts:
                post.current_user_liked = False
    else:
        for post in posts:
            post.current_user_liked = False

    # Renderizziamo l'HTML del "pezzo" di feed
    posts_html = render_template('partials/_feed_posts_chunk.html', posts=posts)
    
    # Restituiamo il JSON
    return jsonify({
        'html': posts_html,
        'has_next_page': posts_pagination.has_next
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