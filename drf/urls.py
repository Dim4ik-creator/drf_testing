from django.contrib import admin
from django.urls import path, include, re_path
from testing.views import *
from rest_framework import routers
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

router = routers.SimpleRouter()
router.register(r"news", NewsViewSet)

urlpatterns = [
    path("admin/", admin.site.urls),
    
    path("api/v1/", include(router.urls)),
    path("api/v1/drf-auth/", include("rest_framework.urls")),
    path("api/v1/auth/", include("djoser.urls")),

    re_path(r"^auth/", include("djoser.urls.authtoken")),
    
    path("api/v1/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/token/verify/", TokenVerifyView.as_view(), name="token_verify"),
    # path("api/v1/Newslist", NewsViewSet.as_view()),
    # path("api/v1/Newslist/<int:pk>/", NewsAPIUpdate.as_view()),
]
