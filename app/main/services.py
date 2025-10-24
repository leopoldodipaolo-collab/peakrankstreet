# File: app/main/services.py
from app import db
from app.models import Post, PostLike
from sqlalchemy.orm import joinedload
from flask_login import current_user

# In app/main/services.py

from sqlalchemy import union_all, select, literal_column
from app.models import Post, Activity, ActivityLike # Assicurati di importare entrambi

def get_unified_feed_items(page=1, per_page=5):
    """
    Recupera una lista unificata e impaginata di Post e Activity,
    ordinata per data di creazione.
    """
     # 1. Query per i Post PUBBLICI
    posts_query = db.session.query(
        Post.id.label('item_id'),
        Post.created_at.label('timestamp'),
        literal_column("'post'").label('item_type')
    ).filter(
        Post.group_id == None  # <-- QUESTO È IL FILTRO FONDAMENTALE
    )

    # 2. Query per le Activity
    activities_query = db.session.query(
        Activity.id.label('item_id'),
        Activity.created_at.label('timestamp'),
        literal_column("'activity'").label('item_type')
    )


    # 3. Uniamo le due query. `union_all` è più veloce di `union`.
    unified_query = union_all(posts_query, activities_query).alias('unified')

    # 4. Ordiniamo i risultati uniti e applichiamo la paginazione
    paginated_ids = db.session.query(unified_query).order_by(
        unified_query.c.timestamp.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    # 5. Ora abbiamo una lista di ID e tipi. Dobbiamo "idratare" questi dati,
    #    cioè recuperare gli oggetti completi.
    post_ids_to_fetch = [item.item_id for item in paginated_ids.items if item.item_type == 'post']
    activity_ids_to_fetch = [item.item_id for item in paginated_ids.items if item.item_type == 'activity']

    posts = Post.query.filter(Post.id.in_(post_ids_to_fetch)).all()
    # --- MODIFICA QUESTA RIGA ---
    activities = Activity.query.options(
        joinedload(Activity.user_activity),
        joinedload(Activity.route_activity)
    ).filter(Activity.id.in_(activity_ids_to_fetch)).all()
    # --- FINE MODIFICA ---

    # Uniamo gli oggetti in un'unica mappa per un recupero veloce
    items_map = {f'post_{p.id}': p for p in posts}
    items_map.update({f'activity_{a.id}': a for a in activities})

    # 6. Ricostruiamo la lista finale nell'ordine corretto
    final_items = [items_map[f'{item.item_type}_{item.item_id}'] for item in paginated_ids.items]

    # Arricchiamo i post con le informazioni sui like (codice che già hai)
    # (Questa logica può essere ottimizzata ulteriormente, ma per ora va bene)
    if current_user.is_authenticated:
        for item in final_items:
            if isinstance(item, Post):
                # La logica dei like per i Post
                item.current_user_liked = PostLike.query.filter_by(user_id=current_user.id, post_id=item.id).first() is not None
            elif isinstance(item, Activity):
                # La logica dei like per le Activity
                item.current_user_liked = ActivityLike.query.filter_by(user_id=current_user.id, activity_id=item.id).first() is not None
    
    return final_items, paginated_ids.has_next