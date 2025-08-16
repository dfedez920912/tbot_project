from django.db import models
from django.utils import timezone

# telegram_bot/models.py

# telegram_bot/models.py
class Usuario(models.Model):
    username = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    mail = models.CharField(max_length=254)
    telephonenumber = models.CharField(max_length=15)

    class Meta:
        db_table = 'telegram_bot_usuario'


# telegram_bot/models.py
class Session(models.Model):
    session_id = models.CharField(max_length=255, primary_key=True)
    session_data = models.TextField()
    email = models.CharField(max_length=254, null=True)  # Nuevo campo
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_updated = models.DateTimeField()

    class Meta:
        db_table = 'telegram_bot_sessions'

    def save(self, *args, **kwargs):
        self.last_updated = timezone.now() + timezone.timedelta(minutes=30)
        super().save(*args, **kwargs)

class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    last_active = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} (@{self.username or self.telegram_id})"