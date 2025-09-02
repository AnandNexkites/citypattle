from django.urls import path
from .views import UserAuthAPIView, VenueAPIView, OTPAPIView,ResetPasswordAPIView,CreateUserAPIView

urlpatterns = [
    path('create-user/', CreateUserAPIView.as_view(), name='create-user'),
    path('auth/', UserAuthAPIView.as_view(), name='user-auth'),
    path('venues/', VenueAPIView.as_view(), name='venues'),
    path('send-otp/', OTPAPIView.as_view(), name='send-otp'),
    path('reset-password/', ResetPasswordAPIView.as_view(), name='reset-password'),
]