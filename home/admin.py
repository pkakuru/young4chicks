from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from home.models import User, Announcement

# Register your models here.
# Register custome user model with extended UserAdmin
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'role', 'phone_number', 'dob', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Info', {
            'fields': ('role', 'phone_number', 'dob')
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Info', {
            'fields': ('role', 'phone_number', 'dob')
        }),
    )

# Register Announcements
@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'posted_on')
    search_fields = ('title', 'content')
    ordering = ('-posted_on',)