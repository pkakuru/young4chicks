from django.urls import path
from home.views import homePage, public_request_status, user_login, logout_view

urlpatterns = [
    path('', homePage, name='homepage'),
    path('status/', public_request_status, name='public_request_status'),
    path('login/', user_login, name='login'),
    path('logout/', logout_view, name='logout'),
]
