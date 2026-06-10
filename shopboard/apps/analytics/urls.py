from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.home, name="home"),
    path("channel/", views.channel_select, name="channel_select"),
    path("channel/activate/", views.channel_activate, name="channel_activate"),
]
