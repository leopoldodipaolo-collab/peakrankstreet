from flask_login import current_user
from sqlalchemy import union_all, literal_column, or_
from sqlalchemy.orm import joinedload
from app import db
from app.models import Post, Activity, PostLike, ActivityLike

def get_unified_feed_items(user=None, page=1, per_page=10):
    """
    Recupera un feed unificato e impaginato.
    - Se l'utente è loggato (`user` viene passato), mostra un feed personalizzato.
    - Se l'utente non è loggato (`user` è None), mostra il feed pubblico globale.
    """
    
    if user and user.is_authenticated:
        # --- FEED PERSONALIZZATO PER UTENTE LOGGATO ---
        followed_user_ids = [u.id for u in user.followed]
        joined_group_ids = [g.id for g in user.joined_groups]
        special_categories = ['admin_announcement', 'weekly_tip', 'system_record', 'system_badge', 'system_new_classic']

        posts_query = db.session.query(
            Post.id.label('item_id'),
            Post.created_at.label('timestamp'),
            literal_column("'post'").label('item_type')
        ).filter(
            or_(
                Post.user_id.in_(followed_user_ids),
                Post.user_id == user.id,
                Post.post_category.in_(special_categories)
            ),
            Post.group_id.is_(None)  # 👈 Escludi i post dei gruppi
        )

        
        activities_query = db.session.query(
            Activity.id.label('item_id'),
            Activity.created_at.label('timestamp'),
            literal_column("'activity'").label('item_type')
        ).filter(
            or_(
                Activity.user_id.in_(followed_user_ids),
                Activity.user_id == user.id
            )
        )

    else:
        # --- FEED PUBBLICO PER VISITATORI ---
        special_categories = ['admin_announcement', 'weekly_tip']
         # Mostriamo gli annunci e i post pubblici (non di gruppo)
        posts_query = db.session.query(
            Post.id.label('item_id'),
            Post.created_at.label('timestamp'),
            literal_column("'post'").label('item_type')
        ).filter(
            Post.group_id.is_(None) # Escludi i post dei gruppi
        )
        
        # Mostriamo tutte le attività
        activities_query = db.session.query(
            Activity.id.label('item_id'),
            Activity.created_at.label('timestamp'),
            literal_column("'activity'").label('item_type')
        )
    
    # --- LOGICA COMUNE ---
    unified_query = union_all(posts_query, activities_query).alias('unified')
    paginated_ids = db.session.query(unified_query).order_by(
        unified_query.c.timestamp.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    post_ids_to_fetch = [item.item_id for item in paginated_ids.items if item.item_type == 'post']
    activity_ids_to_fetch = [item.item_id for item in paginated_ids.items if item.item_type == 'activity']

    posts = []
    if post_ids_to_fetch:
        posts = Post.query.options(
            joinedload(Post.user)
        ).filter(Post.id.in_(post_ids_to_fetch)).all()
        
    activities = []
    if activity_ids_to_fetch:
        activities = Activity.query.options(
            joinedload(Activity.user_activity),
            joinedload(Activity.route_activity)
        ).filter(Activity.id.in_(activity_ids_to_fetch)).all()

    items_map = {f'post_{p.id}': p for p in posts}
    items_map.update({f'activity_{a.id}': a for a in activities})
    final_items = [items_map.get(f'{item.item_type}_{item.item_id}') for item in paginated_ids.items if items_map.get(f'{item.item_type}_{item.item_id}') is not None]

    if user and user.is_authenticated:
        for item in final_items:
            if isinstance(item, Post):
                item.current_user_liked = PostLike.query.filter_by(user_id=user.id, post_id=item.id).first() is not None
            elif isinstance(item, Activity):
                item.current_user_liked = ActivityLike.query.filter_by(user_id=user.id, activity_id=item.id).first() is not None
    
    return final_items, paginated_ids.has_next