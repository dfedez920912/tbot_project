from django import template
import hashlib

register = template.Library()

@register.filter
def make_md5(email):
    return hashlib.md5(email.lower().strip().encode('utf-8')).hexdigest()