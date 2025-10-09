# app/mobile/routes.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from app.models import User, Activity, Route, Challenge 
from app import db
from datetime import datetime
import math
import json
import uuid # Assicurati che questo sia importato

mobile = Blueprint('mobile', __name__)

# Funzione helper per calcolare distanza
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Raggio della Terra in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2) * math.sin(dlat/2) + 
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * 
         math.sin(dlon/2) * math.sin(dlon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# NUOVA FUNZIONE: Calcola statistiche da GPS track
def calculate_activity_stats(gps_track_json):
    coordinates = json.loads(gps_track_json)
    if not coordinates or len(coordinates) < 2:
        return 0.0, 0, 0.0 # (distance_km, duration_seconds, avg_speed_kmh)

    total_distance_km = 0.0
    
    # Calcola la distanza totale sommando i segmenti
    for i in range(1, len(coordinates)):
        prev = coordinates[i-1]
        curr = coordinates[i]
        total_distance_km += calculate_distance(
            prev['latitude'], prev['longitude'],
            curr['latitude'], curr['longitude']
        )
    
    # Calcola la durata totale
    try:
        start_time = datetime.fromisoformat(coordinates[0]['timestamp'].replace('Z', '+00:00'))
        end_time = datetime.fromisoformat(coordinates[-1]['timestamp'].replace('Z', '+00:00'))
        duration_seconds = (end_time - start_time).total_seconds()
    except ValueError:
        try:
            start_time = datetime.fromisoformat(coordinates[0]['timestamp'])
            end_time = datetime.fromisoformat(coordinates[-1]['timestamp'])
            duration_seconds = (end_time - start_time).total_seconds()
        except Exception:
            duration_seconds = 0


    avg_speed_kmh = (total_distance_km / duration_seconds) * 3600 if duration_seconds > 0 else 0.0
    
    return total_distance_km, int(duration_seconds), avg_speed_kmh


# ========== AUTENTICAZIONE MOBILE ==========

@mobile.route('/auth/login', methods=['POST'])
def mobile_login():
    try:
        data = request.json
        login_identifier = data.get('email')
        password = data.get('password')
        
        if not login_identifier or not password:
            return jsonify({
                'success': False,
                'error': 'Email/Username e password richiesti'
            }), 400
        
        user = User.query.filter(
            (User.email == login_identifier) | (User.username == login_identifier)
        ).first()
        
        if user and user.check_password(password):
            access_token = create_access_token(
                identity=str(user.id),
                expires_delta=False
            )
                        
            return jsonify({
                'success': True,
                'token': access_token,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'name': user.username,
                    'is_admin': user.is_admin,
                    'city': user.city,
                    'profile_image': user.profile_image
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Email/Username o password errati'
            }), 401
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@mobile.route('/auth/register', methods=['POST'])
def mobile_register():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        username = data.get('username', email.split('@')[0])
        
        if not email or not password:
            return jsonify({
                'success': False,
                'error': 'Email e password richieste'
            }), 400
        
        if User.query.filter_by(email=email).first():
            return jsonify({
                'success': False,
                'error': 'Email già registrata'
            }), 400
        
        if User.query.filter_by(username=username).first():
            return jsonify({
                'success': False,
                'error': 'Username già esistente'
            }), 400
        
        user = User(
            username=username,
            email=email,
            city=data.get('city', ''),
            profile_image='default.png'
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        access_token = create_access_token(identity=str(user.id))
        
        return jsonify({
            'success': True,
            'message': 'Registrazione completata',
            'token': access_token,
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'name': user.username,
                'is_admin': user.is_admin,
                'city': user.city,
                'profile_image': user.profile_image
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== TRACKING MOBILE ALLINEATO AI TUOI MODELLI ==========

@mobile.route('/tracking/start', methods=['POST'])
@jwt_required()
def start_tracking():
    # Inizializza le variabili a None prima del try/except
    # Questo assicura che esistano anche in caso di errore precoce
    target_route_id = None
    target_challenge_id = None
    route_name_for_response = "Errore di inizializzazione" # Fallback per il nome
    activity = None # Inizializza activity a None

    try:
        user_id = get_jwt_identity()
        data = request.json
        
        challenge_id_from_frontend = data.get('challenge_id')
        route_id_from_frontend = data.get('route_id')
        activity_type = data.get('activity_type', 'Corsa')
        current_city_from_frontend = data.get('current_city')
        
        if challenge_id_from_frontend:
            challenge = Challenge.query.get(challenge_id_from_frontend)
            if not challenge:
                return jsonify({"success": False, "error": f"Sfida con ID {challenge_id_from_frontend} non trovata."}), 404
            
            if route_id_from_frontend and route_id_from_frontend != challenge.route_id:
                return jsonify({"success": False, "error": "Il route_id fornito non corrisponde al percorso della sfida selezionata."}), 400

            target_challenge_id = challenge.id
            target_route_id = challenge.route_id
            route_name_for_response = challenge.route_info.name

        elif route_id_from_frontend:
            route = Route.query.get(route_id_from_frontend)
            if not route:
                return jsonify({"success": False, "error": f"Percorso con ID {route_id_from_frontend} non trovato."}), 404
            target_route_id = route.id
            route_name_for_response = route.name
        else:
            print(f"DEBUG: Avvio tracking libero per user {user_id}")
            new_free_route_name = f"Tracciamento Libero - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            free_route = Route(
                name=new_free_route_name,
                description="Percorso generato automaticamente da un tracciamento libero.",
                coordinates='[]',
                activity_type=activity_type,
                created_by=user_id,
                distance_km=0.0,
                is_classic=False,
                classic_city=current_city_from_frontend if current_city_from_frontend else 'Sconosciuta' 
            )
            db.session.add(free_route)
            db.session.flush()
            target_route_id = free_route.id
            route_name_for_response = new_free_route_name


        activity = Activity( # <--- LA VARIABILE 'activity' VIENE DEFINITA QUI
            user_id=user_id,
            route_id=target_route_id,
            challenge_id=target_challenge_id,
            activity_type=activity_type,
            gps_track='[]',
            duration=0,
            avg_speed=0.0,
            distance=0.0
        )
        
        db.session.add(activity)
        db.session.commit()
        print(f"✅ Attività creata: {activity.id}, collegata a Route: {target_route_id}, Challenge: {target_challenge_id}")
        
        return jsonify({
            "success": True,
            "activity_id": activity.id,
            "route_id": target_route_id,
            "route_name": route_name_for_response,
            "message": "Sessione di tracciamento avviata"
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Errore start_tracking: {str(e)}")
        # QUI, activity potrebbe essere None se l'errore si è verificato prima della sua definizione
        # Gestisci il caso in cui activity non sia ancora definito
        return jsonify({
            "success": False,
            "error": str(e),
            "debug_info": { # Aggiungi info di debug
                "activity_id_attempt": activity.id if activity else "N/A",
                "target_route_id": target_route_id,
                "target_challenge_id": target_challenge_id
            }
        }), 500
    
@mobile.route('/tracking/update', methods=['POST'])
@jwt_required()
def update_tracking():
    try:
        user_id = get_jwt_identity()
        data = request.json
        activity_id = data.get('activity_id')
        location_point = data.get('location')
        
        if not location_point:
            return jsonify({"success": False, "error": "Dati di localizzazione mancanti."}), 400

        activity = Activity.query.filter_by(id=activity_id, user_id=user_id).first()
        if not activity:
            return jsonify({"success": False, "error": "Attività non trovata o non autorizzata"}), 404
        
        gps_track_data = json.loads(activity.gps_track) if activity.gps_track else []
        
        new_coord_formatted = {
            'latitude': location_point['latitude'],
            'longitude': location_point['longitude'],
            'timestamp': location_point['timestamp'],
            'speed': location_point.get('speed', 0),
            'altitude': location_point.get('altitude', 0),
            'accuracy': location_point.get('accuracy', 0)
        }
        gps_track_data.append(new_coord_formatted)
        
        activity.gps_track = json.dumps(gps_track_data)
        
        total_distance, duration, avg_speed = calculate_activity_stats(activity.gps_track)
        
        activity.distance = total_distance
        activity.duration = duration
        activity.avg_speed = avg_speed
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "activity_id": activity.id,
            "locations_count": len(gps_track_data),
            "current_distance": round(activity.distance, 3),
            "current_speed": round(activity.avg_speed, 2) if activity.avg_speed else 0,
            "message": "Posizione aggiornata"
        })
    except Exception as e:
        db.session.rollback()
        print(f"❌ Errore update_tracking: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@mobile.route('/tracking/stop', methods=['POST'])
@jwt_required()
def stop_tracking():
    try:
        user_id = get_jwt_identity()
        data = request.json
        activity_id = data.get('activity_id')
        
        activity = Activity.query.filter_by(id=activity_id, user_id=user_id).first()
        if not activity:
            return jsonify({"success": False, "error": "Attività non trovata o non autorizzata"}), 404
        
        route = Route.query.get(activity.route_id)
        if not route:
            return jsonify({"success": False, "error": "Percorso associato all'attività non trovato"}), 404
        
        final_distance, final_duration, final_avg_speed = calculate_activity_stats(activity.gps_track)
        
        activity.distance = final_distance
        activity.duration = final_duration
        activity.avg_speed = final_avg_speed
        
        db.session.commit()
        
        return jsonify({
            "success": True,
            "activity_data": {
                "id": activity.id,
                "route_id": route.id,
                "route_name": route.name,
                "total_locations": len(json.loads(activity.gps_track)),
                "total_distance": round(activity.distance, 3),
                "average_speed": round(activity.avg_speed, 2) if activity.avg_speed else 0,
                "duration": activity.duration,
                "activity_type": activity.activity_type
            },
            "message": "Tracciamento attività terminato e salvato."
        })
    except Exception as e:
        db.session.rollback()
        print(f"❌ Errore stop_tracking: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# ========== UTILITIES ==========

@mobile.route('/test', methods=['GET'])
def test_connection():
    return jsonify({
        "success": True,
        "message": "StreetSport Mobile API is working!",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0"
    })

@mobile.route('/debug/users', methods=['GET'])
def debug_users():
    """Endpoint di debug per vedere gli utenti"""
    users = User.query.all()
    users_data = []
    for user in users:
        users_data.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'created_at': user.created_at.isoformat() if user.created_at else None
        })
    
    return jsonify({
        "success": True,
        "users": users_data
    })


@mobile.route('/challenges', methods=['GET'])
@jwt_required() 
def get_challenges():
    try:
        user_id = get_jwt_identity()
        
        challenges = Challenge.query.filter(Challenge.is_active == True, Challenge.end_date >= datetime.utcnow()).all()
        
        challenges_data = []
        for challenge in challenges:
            route = Route.query.get(challenge.route_id) 
            if route: 
                challenges_data.append({
                    'id': challenge.id,
                    'name': challenge.name,
                    'description': route.description,
                    'route_id': challenge.route_id,
                    'route_name': route.name,
                    'activity_type': route.activity_type,
                    'start_date': challenge.start_date.isoformat() if challenge.start_date else None,
                    'end_date': challenge.end_date.isoformat() if challenge.end_date else None,
                    'bet_type': challenge.bet_type,
                    'bet_value': challenge.bet_value
                })
            else:
                print(f"Warning: Challenge '{challenge.name}' (ID: {challenge.id}) ha un route_id non valido: {challenge.route_id}. Saltata.")
        
        return jsonify({"success": True, "challenges": challenges_data})
        
    except Exception as e:
        print(f"❌ Errore API GET /challenges: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500