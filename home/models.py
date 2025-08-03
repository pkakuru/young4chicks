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