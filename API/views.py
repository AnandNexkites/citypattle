from django.shortcuts import render
from rest_framework.views import APIView
from django.contrib.auth.hashers import make_password,check_password
from rest_framework.response import Response
from rest_framework import status
from .models import User, Venue
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import models
from django.conf import settings
from django.core.mail import send_mail
import random
try:
    from twilio.rest import Client
except Exception:  # Twilio may not be installed in some environments
    Client = None

#creating user api
@method_decorator(csrf_exempt, name='dispatch')
class CreateUserAPIView(APIView):
    def post(self, request):
        required_fields = [
            "full_name",
            "username",
            "email",
            "phone_number",
            "password",
            "city",
            "country_id"
        ]

        # 🔍 Check missing fields
        missing_fields = [field for field in required_fields if not request.data.get(field)]
        if missing_fields:
            return Response({
                "status": False,
                "message": f"{', '.join(missing_fields)} is required",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        full_name = request.data.get("full_name")
        username = request.data.get("username")
        email = request.data.get("email")
        phone_number = request.data.get("phone_number")
        password = request.data.get("password")
        city = request.data.get("city")
        country_id = request.data.get("country_id")

        # 🔍 Check uniqueness
        if User.objects.filter(username=username).exists():
            return Response({
                "status": False,
                "message": "Username already exists",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({
                "status": False,
                "message": "Email already exists",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(phone_number=phone_number).exists():
            return Response({
                "status": False,
                "message": "Phone number already exists",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # ✅ Create user
            user = User.objects.create(
                full_name=full_name,
                username=username,
                email=email,
                phone_number=phone_number,
                password_hash=make_password(password),  # hash password
                city=city,
                country_id=country_id,
            )

            return Response({
                "status": True,
                "message": "User created successfully",
                "data": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "phone_number": user.phone_number,
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as exc:
            return Response({
                "status": False,
                "message": f"Failed to create user: {str(exc)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#Login API
@method_decorator(csrf_exempt, name='dispatch')
class UserAuthAPIView(APIView):
    def post(self, request):
        username_or_phone = request.data.get('username')
        password = request.data.get('password')

        if not username_or_phone or not password:
            return Response({
                'status': False,
                'message': 'Username/Phone and password required.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # ✅ Find user by username OR phone
            user = User.objects.get(
                models.Q(username=username_or_phone) | models.Q(phone_number=username_or_phone)
            )

            # ✅ Verify hashed password
            if not check_password(password, user.password_hash):
                return Response({
                    'status': False,
                    'message': 'Invalid password.',
                    'data': None
                }, status=status.HTTP_401_UNAUTHORIZED)

            # ✅ Return user data on success
            user_data = {
                'id': user.id,
                'full_name': user.full_name,
                'username': user.username,
                'email': user.email,
                'phone_number': user.phone_number,
                'city': user.city,
                'country_id': user.country_id,
                'created_at': user.created_at,
            }

            return Response({
                'status': True,
                'message': 'Login successful.',
                'data': user_data
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({
                'status': False,
                'message': 'User not found.',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)

# APi to fetch venue
@method_decorator(csrf_exempt, name='dispatch')
class VenueAPIView(APIView):
    def get(self, request):
        venues = Venue.objects.all()
        return Response({
            'status': True,
            'message': 'Venues fetched successfully.',
            'data': venues
        }, status=status.HTTP_200_OK)

#otp on sms and email api
@method_decorator(csrf_exempt, name='dispatch')
class OTPAPIView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        send_via_email = request.data.get('email', False)
        country_code = request.data.get("country_code")

        # Handle different boolean representations
        if send_via_email in ["true", "True", 1, "1"]:
            send_via_email = True
        elif send_via_email in ["false", "False", 0, "0"]:
            send_via_email = False

        # phone_number is required for both flows now
        if not phone_number:
            return Response({
                'status': False,
                'message': 'phone_number is required',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        otp_code = f"{random.randint(1000, 9999)}"
        user_id = None  # default

        # If email flag is set, send OTP via email
        if send_via_email:
            try:
                subject = "CityPattle verification code"
                message_body = f"Your CityPattle verification code is {otp_code}"
                # Fetch user by phone_number. If not found, return error.
                try:
                    user = User.objects.get(phone_number=phone_number)
                    user_id = user.id   # ✅ store user id
                except User.DoesNotExist:
                    return Response({
                        'status': False,
                        'message': 'User not found',
                        'data': None
                    }, status=status.HTTP_404_NOT_FOUND)

                send_mail(subject, message_body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
            except Exception as exc:
                return Response({
                    'status': False,
                    'message': f'Failed to send email OTP: {str(exc)}',
                    'data': None
                }, status=status.HTTP_502_BAD_GATEWAY)
        else:
            # SMS path via Twilio
            account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
            auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
            from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')

            if not all([account_sid, auth_token, from_number]):
                return Response({
                    'status': False,
                    'message': 'Twilio is not configured on server',
                    'data': None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if Client is None:
                return Response({
                    'status': False,
                    'message': 'Twilio SDK is not installed',
                    'data': None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            try:
                client = Client(account_sid, auth_token)
                message = client.messages.create(
                    body=f"Your CityPattle verification code is {otp_code}",
                    from_=from_number,
                    to=country_code + phone_number
                )
                # Try fetching user for SMS path also (if user exists)
                try:
                    user = User.objects.get(phone_number=phone_number)
                    user_id = user.id
                except User.DoesNotExist:
                    pass
            except Exception as exc:
                return Response({
                    'status': False,
                    'message': f'Failed to send OTP: {str(exc)}',
                    'data': None
                }, status=status.HTTP_502_BAD_GATEWAY)

        return Response({
            'status': True,
            'message': 'OTP sent successfully',
            'data': {
                'otp': otp_code,
                'user_id': user_id   # ✅ send user id (or None if not found)
            }
        }, status=status.HTTP_200_OK)

@method_decorator(csrf_exempt, name='dispatch')
class ResetPasswordAPIView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")
        new_password = request.data.get("new_password")

        # ✅ Check required fields
        if not user_id:
            return Response({
                'status': False,
                'message': 'user_id is required',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        if not new_password:
            return Response({
                'status': False,
                'message': 'new_password is required',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
            if not isinstance(new_password, str):
                new_password = str(new_password)

            # 🔐 Hash password before saving
            user.password_hash = make_password(new_password)
            user.save()

            return Response({
                'status': True,
                'message': 'Password updated successfully',
                'data': {'user_id': user.id}
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({
                'status': False,
                'message': 'User not found',
                'data': None
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'status': False,
                'message': f'Failed to update password: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
