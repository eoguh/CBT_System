from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdminUserViewSet, LoginView


router = DefaultRouter()
router.register(r"admin-users", AdminUserViewSet, basename="admin-users")

urlpatterns = [
    path("", include(router.urls)),
    path("login/", LoginView.as_view(), name="login"),
]