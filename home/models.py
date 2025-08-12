from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here.
class User(AbstractUser):
    ROLE_CHOICES = (
        ('brooder_manager', 'Brooder Manager'),
        ('sales_rep', 'Sales Representative'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone_number = models.CharField(max_length=15)
    dob = models.DateField(null=True, blank=True) # Date of Birth

class Announcement(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    posted_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
    
class Training(models.Model):
    title = models.CharField(max_length=120)
    date = models.DateField()
    location = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.title} ({self.date})"

class FarmerTip(models.Model):
    text = models.CharField(max_length=200)  # short & sweet tips
    created_on = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return self.text[:50]
    
class QuoteOfTheWeek(models.Model):
    text = models.TextField()
    author = models.CharField(max_length=100, blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)  # leave blank for “until changed”
    posted_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return (self.text[:40] + '…') if len(self.text) > 40 else self.text
