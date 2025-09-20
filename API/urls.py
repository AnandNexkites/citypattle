from django.urls import path
from .views import GenerateSlotsAPIView, UserAuthAPIView, VenueAPIView, OTPAPIView,ResetPasswordAPIView,CreateUserAPIView,AddCountryAPIView,EmailOTPAPIView,SmsOTPAPIView,GoogleLoginAPIView
urlpatterns = [
    path('create-user/', CreateUserAPIView.as_view(), name='create-user'),
    path('auth/', UserAuthAPIView.as_view(), name='user-auth'),
    path('venues/', VenueAPIView.as_view(), name='venues'),
    path('send-otp/', OTPAPIView.as_view(), name='send-otp'),
    path('otp/email/', EmailOTPAPIView.as_view(), name='email-otp'),
    path('otp/sms/', SmsOTPAPIView.as_view(), name='email-otp'),
    path('reset-password/', ResetPasswordAPIView.as_view(), name='reset-password'),
    path('add-country/', AddCountryAPIView.as_view(), name='add-country'),
    path('venues/generate-slots/', GenerateSlotsAPIView.as_view(), name='generate-slots'),
    path('google-user-create-login/', GoogleLoginAPIView.as_view(), name='creat-google-user-or-login'),
]