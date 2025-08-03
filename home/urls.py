from django.urls import path
from home.views import homePage

urlpatterns = [
    path('', homePage, name='homepage'),
]
