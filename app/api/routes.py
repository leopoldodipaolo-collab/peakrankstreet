# app/api/routes.py

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from app.models import Route, Challenge, Activity, User, RouteRecord, ActivityLike, Notification
from app import db
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from math import cos as math_cos, radians as math_radians
import json
from shapely.geometry import LineString, box, Point # Importa anche Point per il controllo
from datetime import datetime

api = Blueprint('api', __name__)

@api.route('/map_data')
def get_map_data():
    lat = request.args.get('lat', type=float)
    lon = request.args.get('lon', type=float)
    radius_km = request.args.get('radius_km', 20, type=float)
    activity_type = request.args.get('activity_type', 'all', type=str)

    all_routes_query = Route.query.options(joinedload(Route.creator))
    all_challenges_query = Challenge.query.options(
        joinedload(Challenge.challenger),
        joinedload(Challenge.route_info)
    ).order_by(Challenge.created_at.desc())
    all_activities_query = Activity.query.options(
        joinedload(Activity.user_activity),
        joinedload(Activity.route_activity),
        joinedload(Activity.challenge_info)
    ).order_by(Activity.created_at.desc())
    
    if activity_type != 'all':
        all_routes_query = all_routes_query.filter(Route.activity_type == activity_type)
        all_activities_query = all_activities_query.filter(Activity.activity_type == activity_type)
        all_challenges_query = all_challenges_query.join(Route).filter(Route.activity_type == activity_type)

    all_routes_from_db = all_routes_query.all()
    all_challenges_from_db = all_challenges_query.all()
    all_activities_from_db = all_activities_query.all()

    query_routes_to_serialize = []
    query_challenges_to_serialize = []
    query_activities_to_serialize = []

    route_ids_in_area = set()

    if lat is None or lon is None:
        query_routes_to_serialize = all_routes_from_db[:10]
        query_challenges_to_serialize = all_challenges_from_db[:3]
        query_activities_to_serialize = all_activities_from_db[:10]
        route_ids_in_area = {r.id for r in query_routes_to_serialize}
    else:
        delta_lat = radius_km / 111.0
        delta_lon = radius_km / (111.0 * abs(math_cos(math_radians(lat)))) if lat != 0 else radius_km / 111.0 
        min_lat, max_lat = lat - delta_lat, lat + delta_lat
        min_lon, max_lon = lon - delta_lon, lon + delta_lon
        
        bbox_polygon_shapely = box(min_lon, min_lat, max_lon, max_lat) # Definisci una volta

        for route in all_routes_from_db:
            processed_geojson = None # Variabile per memorizzare il GeoJSON in formato standard
            if route.coordinates:
                try:
                    loaded_coords = json.loads(route.coordinates)
                    
                    if isinstance(loaded_coords, dict) and 'geometry' in loaded_coords and 'coordinates' in loaded_coords['geometry']:
                        # Caso 1: È un oggetto GeoJSON Feature completo
                        processed_geojson = loaded_coords
                    elif isinstance(loaded_coords, dict) and 'type' in loaded_coords and loaded_coords['type'] == 'LineString' and 'coordinates' in loaded_coords:
                        # Caso 2: È un oggetto GeoJSON LineString diretto
                        processed_geojson = {"type": "Feature", "geometry": loaded_coords, "properties": {}}
                    elif isinstance(loaded_coords, list) and all(isinstance(coord, list) and len(coord) >= 2 for coord in loaded_coords):
                        # Caso 3: È un semplice array di [lon, lat] o [lon, lat, alt]
                        processed_geojson = {
                            "type": "Feature",
                            "geometry": {
                                "type": "LineString",
                                "coordinates": loaded_coords
                            },
                            "properties": {}
                        }
                    # else: Formato non riconosciuto, processed_geojson rimane None
                except json.JSONDecodeError:
                    print(f"Warning: Errore di decodifica JSON per la rotta {route.id}. Coordinates: {route.coordinates[:100]}...")
            
            # Se abbiamo un GeoJSON valido e processato, controlliamo l'intersezione
            if processed_geojson and 'geometry' in processed_geojson and 'coordinates' in processed_geojson['geometry']:
                geo_type = processed_geojson['geometry']['type']
                geo_coords = processed_geojson['geometry']['coordinates']

                shapely_geometry = None
                if geo_type == 'LineString':
                    shapely_geometry = LineString(geo_coords)
                elif geo_type == 'Point' and geo_coords: # Se una rotta fosse un singolo punto (improbabile ma possibile)
                    shapely_geometry = Point(geo_coords)
                # Aggiungi altri tipi di geometria GeoJSON se necessario (Polygon, etc.)

                if shapely_geometry and shapely_geometry.intersects(bbox_polygon_shapely):
                    query_routes_to_serialize.append(route) # Aggiungi l'intera rotta per la serializzazione
                    route_ids_in_area.add(route.id) # Aggiungi l'ID per filtrare sfide/attività
        
        # Filtra sfide e attività basandosi sugli ID delle rotte nell'area
        query_challenges_to_serialize = [c for c in all_challenges_from_db if c.route_id in route_ids_in_area]
        query_activities_to_serialize = [a for a in all_activities_from_db if a.route_id in route_ids_in_area]
        
        # Applica i limiti se necessario (già fatto sopra)
        query_challenges_to_serialize = query_challenges_to_serialize[:3]
        query_activities_to_serialize = query_activities_to_serialize[:10]


    serializable_routes_for_api = []
    serializable_featured_routes_for_api = []
    
    for route in query_routes_to_serialize:
        # Recupera il record holder e le top 5 attività (la logica rimane simile)
        route_record = RouteRecord.query.options(
            joinedload(RouteRecord.record_holder),
            joinedload(RouteRecord.activity)
        ).filter_by(route_id=route.id).order_by(RouteRecord.duration.asc()).first()

        king_queen_data = None
        if route_record and route_record.record_holder and route_record.activity:
            king_queen_data = {
                'username': route_record.record_holder.username,
                'user_id': route_record.record_holder.id,
                'profile_image': route_record.record_holder.profile_image,
                'duration': route_record.duration,
                'activity_id': route_record.activity.id,
                'created_at': route_record.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        
        top_5_activities = Activity.query.options(
            joinedload(Activity.user_activity)
        ).filter_by(route_id=route.id).order_by(Activity.duration.asc()).limit(5).all()

        top_5_activities_data = []
        for activity in top_5_activities:
            if activity.user_activity:
                top_5_activities_data.append({
                    'username': activity.user_activity.username,
                    'user_id': activity.user_activity.id,
                    'profile_image': activity.user_activity.profile_image,
                    'duration': activity.duration,
                    'distance': activity.distance,
                    'avg_speed': activity.avg_speed,
                    'activity_id': activity.id
                })

        creator_username = route.creator.username if route.creator else "Sconosciuto"
        creator_id = route.creator.id if route.creator else None
        creator_profile_image = route.creator.profile_image if route.creator else "default.png"

        # Anche qui, assicurati che le coordinate siano sempre un oggetto GeoJSON ben formato per la risposta
        # altrimenti potrebbero esserci problemi nel frontend con le mappe
        final_coordinates_for_api = None
        if route.coordinates:
             try:
                 loaded_coords_for_api = json.loads(route.coordinates)
                 if isinstance(loaded_coords_for_api, dict) and 'geometry' in loaded_coords_for_api:
                     final_coordinates_for_api = loaded_coords_for_api # Già un Feature
                 elif isinstance(loaded_coords_for_api, dict) and 'type' in loaded_coords_for_api and loaded_coords_for_api['type'] == 'LineString':
                     final_coordinates_for_api = {"type": "Feature", "geometry": loaded_coords_for_api, "properties": {}}
                 elif isinstance(loaded_coords_for_api, list):
                     final_coordinates_for_api = {
                         "type": "Feature",
                         "geometry": {
                             "type": "LineString",
                             "coordinates": loaded_coords_for_api
                         },
                         "properties": {}
                     }
             except json.JSONDecodeError:
                 print(f"Warning: Errore di decodifica JSON durante la serializzazione per rotta {route.id}.")


        route_data = {
            'id': route.id,
            'name': route.name,
            'description': route.description,
            'coordinates': final_coordinates_for_api, # <-- USA IL PROCESSED GEOJSON QUI
            'created_at': route.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'created_by_id': creator_id,
            'created_by_username': creator_username,
            'profile_image': creator_profile_image,
            'distance_km': route.distance_km,
            'is_featured': route.is_featured,
            'featured_image': route.featured_image,
            'king_queen': king_queen_data,
            'top_5_activities': top_5_activities_data,
            'activity_type': route.activity_type 
        }

        serializable_routes_for_api.append(route_data)

        if route.is_featured:
            serializable_featured_routes_for_api.append(route_data)

    serializable_challenges_for_api = []
    for challenge in sorted(query_challenges_to_serialize, key=lambda c: c.created_at, reverse=True):
        serializable_challenges_for_api.append({
            'id': challenge.id,
            'name': challenge.name,
            'route_id': challenge.route_id,
            'route_name': challenge.route_info.name,
            'start_date': challenge.start_date.strftime('%Y-%m-%d'),
            'end_date': challenge.end_date.strftime('%Y-%m-%d'),
            'created_by_id': challenge.challenger.id,
            'created_by_username': challenge.challenger.username,
            'is_active': challenge.end_date >= datetime.utcnow(),
            'created_at': challenge.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    serializable_activities_for_api = []
    for activity in query_activities_to_serialize:
        if activity.user_activity and activity.route_activity:
            
            # --- NUOVA LOGICA PER I LIKE ---
            like_count = activity.likes.count()
            user_has_liked = False
            # Verifica se l'utente corrente è autenticato prima di accedere a current_user.id
            if current_user.is_authenticated:
                # Controlla se esiste un like di questo utente per questa attività
                if activity.likes.filter(ActivityLike.user_id == current_user.id).first():
                    user_has_liked = True
            # --- FINE NUOVA LOGICA ---

            serializable_activities_for_api.append({
                'id': activity.id,
                'user_id': activity.user_id,
                'username': activity.user_activity.username,
                'user_profile_image': activity.user_activity.profile_image,
                'route_id': activity.route_id,
                'route_name': activity.route_activity.name,
                'challenge_id': activity.challenge_id,
                'challenge_name': activity.challenge_info.name if activity.challenge_info else None,
                'distance': activity.distance,
                'duration': activity.duration,
                'avg_speed': activity.avg_speed,
                'created_at': activity.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                 # --- NUOVI DATI AGGIUNTI AL JSON ---
                'like_count': like_count,
                'user_has_liked': user_has_liked
            })

    # >>> INIZIO NUOVA SEZIONE: CLASSIFICHE LOCALI <<<
    local_top_distance = []
    local_top_creators = []

    if route_ids_in_area: # Calcola solo se ci sono percorsi nell'area
        local_top_distance_raw = db.session.query(
            User.id, User.username, User.profile_image,
            func.sum(Activity.distance).label('total_distance')
        ).join(Activity, User.id == Activity.user_id)\
        .filter(Activity.route_id.in_(route_ids_in_area))\
        .group_by(User.id, User.username, User.profile_image)\
        .order_by(func.sum(Activity.distance).desc())\
        .limit(5).all()

        local_top_creators_raw = db.session.query(
            User.id, User.username, User.profile_image,
            func.count(Route.id).label('total_routes_created')
        ).join(Route, User.id == Route.created_by)\
        .filter(Route.id.in_(route_ids_in_area))\
        .group_by(User.id, User.username, User.profile_image)\
        .order_by(func.count(Route.id).desc())\
        .limit(5).all()
        
        # Serializza i risultati grezzi
        local_top_distance = [
            {'id': u.id, 'username': u.username, 'profile_image': u.profile_image, 'total_distance': float(u.total_distance)}
            for u in local_top_distance_raw
        ]
        local_top_creators = [
            {'id': u.id, 'username': u.username, 'profile_image': u.profile_image, 'total_routes_created': u.total_routes_created}
            for u in local_top_creators_raw
        ]
    # >>> FINE NUOVA SEZIONE <<<


    return jsonify({
        "routes": serializable_routes_for_api,
        "challenges": serializable_challenges_for_api,
        "recent_activities": serializable_activities_for_api,
        "featured_routes": serializable_featured_routes_for_api,
        "local_leaderboards": {
            "distance": local_top_distance,
            "creators": local_top_creators
        }
    })


# In app/api/routes.py, dopo la funzione get_map_data

@api.route('/activity/<int:activity_id>/like', methods=['POST'])
@login_required
def toggle_activity_like(activity_id):
    activity = Activity.query.get_or_404(activity_id)
    like = ActivityLike.query.filter_by(user_id=current_user.id, activity_id=activity.id).first()
    
    if like:
        # L'utente sta togliendo il like, quindi potremmo voler cancellare la notifica
        # Per semplicità, per ora non facciamo nulla in caso di "unlike"
        db.session.delete(like)
        action = 'unliked'
    else:
        # L'utente sta mettendo il like, creiamo la notifica
        new_like = ActivityLike(user_id=current_user.id, activity_id=activity.id)
        db.session.add(new_like)
        action = 'liked'
        
        # --- NUOVA LOGICA NOTIFICHE ---
        # Invia una notifica al proprietario dell'attività,
        # ma solo se non sta mettendo like a una sua stessa attività
        if activity.user_id != current_user.id:
            notification = Notification(
                recipient_id=activity.user_id,    # La notifica è per chi ha creato l'attività
                actor_id=current_user.id,         # L'attore è chi ha messo like
                action='like_activity',
                object_id=activity.id,            # ID dell'attività
                object_type='activity'
            )
            db.session.add(notification)
        # --- FINE NUOVA LOGICA ---

    db.session.commit()
    
    return jsonify({
        'status': 'success',
        'action': action,
        'new_like_count': activity.likes.count()
    })


# Aggiungi questa route al tuo file api/routes.py
@api.route('/classic-routes/<city>')
def get_classic_routes(city):
    """Restituisce i percorsi classici per una città specifica, con top 5 tempi opzionali"""
    from app.models import Route, RouteRecord, Activity
    from sqlalchemy import func

    include_top_times = request.args.get('include_top_times', 'false').lower() == 'true'

    # Recupera tutte le route classiche della città, case-insensitive
    classic_routes = Route.query.filter(
        Route.is_classic == True,
        Route.classic_city.ilike(f"%{city}%")
    ).order_by(Route.name).all()

    routes_data = []
    for route in classic_routes:
        # Recupera il record holder (il migliore) per la route
        record = RouteRecord.query.filter_by(route_id=route.id).order_by(RouteRecord.duration.asc()).first()

        route_data = {
            'id': route.id,
            'name': route.name,
            'description': route.description,
            'activity_type': route.activity_type,
            'start_location': route.start_location,
            'end_location': route.end_location,
            'distance_km': route.distance_km,
            'elevation_gain': route.elevation_gain,
            'difficulty': route.difficulty,
            'estimated_time': route.estimated_time,
            'landmarks': route.landmarks,
            'featured_image': route.featured_image,
            'total_activities': len(route.activities),
            'record_holder': None,
            'top_5_times': []
        }

        if record and record.record_holder:
            route_data['record_holder'] = {
                'username': record.record_holder.username,
                'duration': record.duration
            }

        # --- LOGICA TOP 5 TEMPI ---
        if include_top_times:
            top_5_activities = Activity.query.options(
                joinedload(Activity.user_activity)
            ).filter_by(route_id=route.id).order_by(Activity.duration.asc()).limit(5).all()

            top_5_activities_data = []
            for activity in top_5_activities:
                if activity.user_activity:
                    top_5_activities_data.append({
                        'username': activity.user_activity.username,
                        'user_id': activity.user_activity.id,
                        'profile_image': activity.user_activity.profile_image,
                        'duration': activity.duration,
                        'distance': activity.distance,
                        'avg_speed': activity.avg_speed,
                        'activity_id': activity.id
                    })
            route_data['top_5_times'] = top_5_activities_data

        routes_data.append(route_data)

    return jsonify(routes_data)



# Aggiungi questa route dopo le altre route API

@api.route('/my-friends')
@login_required
def my_friends():
    """API per ottenere la lista degli amici seguiti dall'utente corrente"""
    try:
        # Ottieni gli utenti che l'utente corrente segue
        followed_users = current_user.followed.all()
        
        friends_list = []
        for user in followed_users:
            friends_list.append({
                'id': user.id,
                'username': user.username,
                'profile_image': user.profile_image
            })
        
        return jsonify(friends_list)
        
    except Exception as e:
        print(f"Errore nel caricamento amici: {e}")
        return jsonify({'error': 'Errore nel caricamento degli amici'}), 500