from django.db import models
from datetime import date
from django.conf import settings
from manager.models import ChickStock
from django.contrib.auth.models import User
from manager.models import ChickStock


# Create your models here.

# Farmer Model
class Farmer(models.Model):
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
    )
    FARMER_TYPE_CHOICES = (
        ('starter', 'Starter'),
        ('returning', 'Returning'),
    )

    name = models.CharField(max_length=100)
    dob = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    nin = models.CharField(max_length=20, unique=True)
    recommender = models.CharField(max_length=100)
    recommender_nin = models.CharField(max_length=20)
    contact = models.CharField(max_length=15)
    farmer_type = models.CharField(max_length=10, choices=FARMER_TYPE_CHOICES, default='starter')

    @property
    def age(self):
        today = date.today()
        return (
            today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))
        )

    def __str__(self):
        return self.name
    
# Chick request model
class ChickRequest(models.Model):
    CHICK_TYPE_CHOICES = (
        ('broiler_local', 'Broiler - Local'),
        ('broiler_exotic', 'Broiler - Exotic'),
        ('layer_local', 'Layer - Local'),
        ('layer_exotic', 'Layer - Exotic'),
    )
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE)
    chick_type = models.CharField(max_length=20, choices=CHICK_TYPE_CHOICES)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    submitted_on = models.DateField(auto_now_add=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete = models.SET_NULL,
        null = True,
        blank = True,
        related_name = 'approved_chick_request'
    )
    approval_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    is_picked = models.BooleanField(default=False)
    picked_on = models.DateField(null=True, blank=True)
    pickup_notes = models.TextField(null=True, blank=True)

    decision_note = models.TextField(null=True, blank=True)
    decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decided_chick_requests'
    )
    decision_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Request #{self.id} - {self.farmer.name}"

# Manufaturer model   
class Manufacturer(models.Model):
    name = models.CharField(max_length=100, unique=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name

# Supplier model
class Supplier(models.Model):
    name = models.CharField(max_length=100, unique=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name
    

# FeedStock model
class FeedStock(models.Model):
    FEED_TYPE_CHOICES = (
        ('starter', 'Starter'),
        ('grower', 'Grower'),
        ('finisher', 'Finisher'),
    )

    feed_type = models.CharField(max_length=10, choices=FEED_TYPE_CHOICES)
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.SET_NULL, null=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True)
    quantity_bags = models.PositiveIntegerField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    arrival_date = models.DateField()
    expiry_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.get_feed_type_display()} - {self.quantity_bags} bags"



# FeedDistribution model
class FeedDistribution(models.Model):
    DISTRIBUTION_TYPE_CHOICES = (
        ('initial', 'Initial Allocation (Entitled)'),
        ('purchase', 'Extra Purchase'),
    )
    farmer = models.ForeignKey('Farmer', on_delete=models.CASCADE)
    feed_stock = models.ForeignKey('FeedStock', on_delete=models.SET_NULL, null=True, blank=True)
    distribution_type = models.CharField(max_length=10, choices=DISTRIBUTION_TYPE_CHOICES)
    quantity_bags = models.PositiveIntegerField()
    distribution_date = models.DateField(auto_now_add=True)
    due_date = models.DateField(null=True, blank=True, help_text="Payment due date (for initial allocations)")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.farmer.name} - {self.get_distribution_type_display()} - {self.quantity_bags} bags"


# Payment model
class Payment(models.Model):
    PAYMENT_FOR_CHOICES = (
        ('chicks', 'Chicks'),
        ('feeds', 'Feeds'),
        ('both', 'Chicks and Feeds'),
        ('other', 'Other'),
    )
    farmer = models.ForeignKey('Farmer', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_for = models.CharField(max_length=10, choices=PAYMENT_FOR_CHOICES)
    related_feed_distribution = models.ForeignKey('FeedDistribution', on_delete=models.SET_NULL, null=True, blank=True)
    payment_date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.farmer.name} - {self.payment_for} - UGX {self.amount}"


class FeedRequest(models.Model):
    FEED_TYPE_CHOICES = (
        ('starter', 'Starter'),
        ('grower', 'Grower'),
        ('finisher', 'Finisher'),
    )

    FEED_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    PICKUP_STATUS_CHOICES = (
        ('not_picked', 'Not Picked'),
        ('picked', 'Picked Up'),
    )

    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE)
    feed_type = models.CharField(max_length=10, choices=FEED_TYPE_CHOICES)
    quantity_bags = models.PositiveIntegerField()
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='feed_requests_made')
    submitted_on = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=10, choices=FEED_STATUS_CHOICES, default='pending')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='feed_requests_approved')
    approved_on = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True, null=True)

    pickup_status = models.CharField(max_length=12, choices=PICKUP_STATUS_CHOICES, default='not_picked')

    
    picked_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_on']

    def __str__(self):
        return f"{self.farmer.name} - {self.quantity_bags} bags ({self.feed_type})"

