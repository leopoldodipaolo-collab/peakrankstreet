# File: app/main/services.py
from app import db
from app.models import Post, PostLike
from sqlalchemy.orm import joinedload
from flask_login import current_user

def get_community_feed_items(limit: int = 5):
    posts = Post.query.options(joinedload(Post.user)).order_by(Post.created_at.desc()).limit(limit).all()

    if current_user.is_authenticated:
        post_ids = [p.id for p in posts]
        liked_post_ids = {like.post_id for like in PostLike.query.filter(PostLike.user_id == current_user.id, PostLike.post_id.in_(post_ids)).all()}
        for post in posts:
            post.current_user_liked = post.id in liked_post_ids
    else:
        for post in posts:
            post.current_user_liked = False
            
    return posts