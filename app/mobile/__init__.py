# app/mobile/__init__.py
from flask import Blueprint

mobile = Blueprint('mobile', __name__)

from app.mobile import routes