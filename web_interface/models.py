# web_interface/models.py
from django.db import models
import logging

class LogEntry(models.Model):
    LEVEL_CHOICES = [
        ('INFO', 'Info'),
        ('WARNING', 'Warning'),
        ('ERROR', 'Error'),
        ('CRITICAL', 'Critical'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    message = models.TextField()
    source = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"[{self.level}] {self.message[:60]}"

    class Meta:
        verbose_name = "Log Entry"
        ordering = ['-timestamp']

class AppSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)

    @classmethod
    def get_bool(cls, key, default=False):
        try:
            value = cls.objects.get(key=key).value.lower().strip("'\"")
            return value in ['true', '1', 'yes', 'on']
        except cls.DoesNotExist:
            return default

    @classmethod
    def set_bool(cls, key, value, description=''):
        logger = logging.getLogger(__name__)
        logger.debug(f"AppSetting.set_bool: key={key}, value={value}, description={description}")
        obj, created = cls.objects.update_or_create(
            key=key,
            defaults={'value': 'true' if value else 'false', 'description': description}
        )
        logger.debug(f"AppSetting.set_bool: {'Creado' if created else 'Actualizado'} registro con ID={obj.id}")

    class Meta:
        db_table = 'app_auth_settings'  # ← Nombre exacto de la tabla que creaste