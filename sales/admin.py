from django.contrib import admin
from sales.models import Farmer, ChickRequest

# Register your models here.
@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ('name', 'nin', 'contact', 'gender', 'dob', 'farmer_type')
    search_fields = ('name', 'nin', 'recommender', 'contact')
    list_filter = ('gender', 'farmer_type')


@admin.register(ChickRequest)
class ChickRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'farmer', 'chick_type', 'quantity', 'status', 'submitted_on')
    list_filter = ('status', 'chick_type')
    search_fields = ('farmer_name', 'farmer_nin')