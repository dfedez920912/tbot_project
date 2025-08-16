# logs/models.py
from django.db import models

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
    source = models.CharField(max_length=50, blank=True)  # e.g., "bot_handler"

    def __str__(self):
        return f"[{self.level}] {self.message[:50]}"