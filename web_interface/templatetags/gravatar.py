from django import template
from django.contrib.auth.models import User
import hashlib

register = template.Library()

@register.filter
def make_md5(email):
    """Convierte un email a MD5 para Gravatar"""
    return hashlib.md5(email.lower().encode('utf-8')).hexdigest()