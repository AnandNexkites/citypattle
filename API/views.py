from django.shortcuts import render
from rest_framework.views import APIView
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.response import Response
from rest_framework import status
from .models import FCMToken, Slot, User, Venue, Country, City,UserVerification
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import models
from django.conf import settings
from django.core.mail import send_mail
import random
from django.utils import timezone
try:
    from twilio.rest import Client
except Exception:
    Client = None
from datetime import datetime, timedelta, time


# ----------------------------
# Add Country API
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class AddCountryAPIView(APIView):
    def post(self, request):
        name = request.data.get('name')
        iso_code = request.data.get('iso_code')
        phone_code = request.data.get('phone_code')
        flag = request.FILES.get('flag')  # ✅ file upload

        if not all([name, iso_code, phone_code, flag]):
            return Response({
                'status': False,
                'message': 'All fields are required.',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            country = Country.objects.create(
                name=name,
                iso_code=iso_code,
                phone_code=phone_code,
                flag=flag
            )

            return Response({
                'status': True,
                'message': 'Country added successfully.',
                'data': {
                    'id': country.id,
                    'name': country.name,
                    'iso_code': country.iso_code,
                    'phone_code': country.phone_code,
                    'flag': str(country.flag.url) if country.flag else None
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({
                'status': False,
                'message': f'Error: {str(e)}',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ----------------------------
# Create User API
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class CreateUserAPIView(APIView):
    def post(self, request):
        required_fields = ["full_name", "email", "phone_number", "password", "city"]
        missing = [f for f in required_fields if not request.data.get(f)]
        if missing:
            return Response({
                "status": False,
                "message": f"{', '.join(missing)} is required",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        email = request.data["email"]
        phone_number = request.data["phone_number"]

        # Uniqueness checks
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
            # Fetch city, state, country
            city_id = request.data["city"]
            city_obj = City.objects.get(id=city_id)
            state_obj = city_obj.state
            country_obj = state_obj.country

            # Create user
            user = User.objects.create(
                full_name=request.data["full_name"],
                email=email,
                phone_number=phone_number,
                password_hash=make_password(request.data["password"]),
                city=city_obj,
                created_at=timezone.now()
            )

            # Create verification record and mark both verified
            UserVerification.objects.create(
                user=user,
                is_email_verified=True,
                is_phone_verified=True
            )

            return Response({
                "status": True,
                "message": "User created successfully",
                "data": {
                    "id": user.id,
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "country": country_obj.name,
                    "country_id": country_obj.id,
                    "country_iso_code": country_obj.iso_code,
                    "country_phone_code": country_obj.phone_code,
                    "state": state_obj.name,
                    "state_id": state_obj.id,
                    "city_id": city_obj.id,
                    "city": city_obj.name,
                    "created_at": user.created_at.isoformat(),
                    "is_email_verified": True,
                    "is_phone_verified": True
                }
            }, status=status.HTTP_201_CREATED)

        except City.DoesNotExist:
            return Response({
                "status": False,
                "message": "City not found",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            return Response({
                "status": False,
                "message": f"Failed to create user: {str(exc)}",
                "data": None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# ----------------------------
# Helper function to update or add fmc tocken for user
# ----------------------------
def save_fcm_token(user, token, device_type="android"):
    """
    Save or update an FCM token for the user.
    - If the token already exists, update the user & device_type.
    - If new, create a record.
    - Deactivate old tokens for the same user if needed.
    """
    if not token:
        return None

    fcm, created = FCMToken.objects.get_or_create(
        token=token,
        defaults={
            "user": user,
            "device_type": device_type,
            "is_active": True,
        }
    )

    if not created:
        # Token already exists → update owner and activate it
        fcm.user = user
        fcm.device_type = device_type
        fcm.is_active = True
        fcm.save()

    return fcm

# ----------------------------
# Login API (email OR phone)
# ----------------------------
class UserAuthAPIView(APIView):
    def post(self, request):
        identifier = request.data.get('username')
        password = request.data.get('password')
        fcm_token = request.data.get("fcm_token")
        device_type = request.data.get("device_type", "android")

        if not identifier:
            return Response({'status': False, 'message': 'Username required.', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)
        if not password:
            return Response({'status': False, 'message': 'Password required.', 'data': None},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(models.Q(email=identifier) | models.Q(phone_number=identifier))

            if not check_password(password, user.password_hash):
                return Response({'status': False, 'message': 'Invalid password.', 'data': None},
                                status=status.HTTP_401_UNAUTHORIZED)

            # ✅ Save FCM Token
            if fcm_token:
                save_fcm_token(user, fcm_token, device_type)

            return Response({
                'status': True,
                'message': 'Login successful.',
                'data': {
                    "id": user.id,
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "city": user.city.name if user.city else None,
                    "city_id": user.city.id if user.city else None,
                    "tokens": list(user.fcm_tokens.values("token", "device_type", "is_active")),  # ✅ return all tokens
                }
            }, status=status.HTTP_200_OK)

        except User.DoesNotExist:
            return Response({'status': False, 'message': 'User not found.', 'data': None},
                            status=status.HTTP_404_NOT_FOUND)


# ----------------------------
# Login API for google user
# ----------------------------
class GoogleLoginAPIView(APIView):
    def post(self, request):
        email = request.data.get("email")
        full_name = request.data.get("full_name", "")
        phone_number = request.data.get("phone_number", "")
        city_id = request.data.get("city_id")  # match key with Flutter request
        fcm_token = request.data.get("fcm_token")
        device_type = request.data.get("device_type", "android")

        if not email:
            return Response(
                {"status": False, "message": "Email is required from Google", "data": None},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # ✅ Handle city
            city_obj = City.objects.filter(id=city_id).first() if city_id else None
            if not city_obj:
                city_obj = City.objects.filter(id=1).first()

            # ✅ Get or create Google user
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "full_name": full_name,
                    "phone_number": phone_number if phone_number else f"google-{int(timezone.now().timestamp())}",
                    "password_hash": "",
                    "created_at": timezone.now(),
                    "city": city_obj,
                }
            )

            # ✅ Save FCM token
            if fcm_token:
                save_fcm_token(user, fcm_token, device_type)

            # ✅ Ensure email verification
            verification, _ = UserVerification.objects.get_or_create(user=user)
            if not verification.is_email_verified:
                verification.is_email_verified = True
                verification.save()

            return Response({
                "status": True,
                "message": "Google login successful" if not created else "Google user created successfully",
                "data": {
                    "id": user.id,
                    "full_name": user.full_name,
                    "email": user.email,
                    "phone_number": user.phone_number,
                    "city": user.city.name if user.city else None,
                    "city_id": user.city.id if user.city else None,
                    "state": user.state.name if hasattr(user, 'state') and user.state else "",
                    "state_id": user.state.id if hasattr(user, 'state') and user.state else "",
                    "country": user.country.name if hasattr(user, 'country') and user.country else "",
                    "country_id": user.country.id if hasattr(user, 'country') and user.country else "",
                    "country_iso_code": user.country_iso_code if hasattr(user, 'country_iso_code') else "",
                    "country_phone_code": user.country_phone_code if hasattr(user, 'country_phone_code') else "",
                    "created_at": user.created_at,
                    "tokens": list(user.fcm_tokens.values("token", "device_type", "is_active")),
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"status": False, "message": f"Failed to login with Google: {str(e)}", "data": None},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# ----------------------------
# OTP API (Email + SMS)
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class OTPAPIView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        send_via_email = request.data.get('email', False)
        country_code = request.data.get("country_code")

        if send_via_email in ["true", "True", 1, "1"]:
            send_via_email = True
        elif send_via_email in ["false", "False", 0, "0"]:
            send_via_email = False

        if not phone_number:
            return Response({
                'status': False,
                'message': 'phone_number is required',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        otp_code = f"{random.randint(1000, 9999)}"
        user_id = None

        if send_via_email:
            try:
                user = User.objects.get(phone_number=phone_number)
                user_id = user.id
                send_mail(
                    "CityPattle verification code",
                    f"Your CityPattle verification code is {otp_code}",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False
                )
            except User.DoesNotExist:
                return Response({
                    'status': False,
                    'message': 'User not found',
                    'data': None
                }, status=status.HTTP_404_NOT_FOUND)
            except Exception as exc:
                return Response({
                    'status': False,
                    'message': f'Failed to send email OTP: {str(exc)}',
                    'data': None
                }, status=status.HTTP_502_BAD_GATEWAY)
        else:
            account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
            auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
            from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')

            if not all([account_sid, auth_token, from_number]):
                return Response({
                    'status': False,
                    'message': 'Twilio is not configured',
                    'data': None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if Client is None:
                return Response({
                    'status': False,
                    'message': 'Twilio SDK not installed',
                    'data': None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            try:
                client = Client(account_sid, auth_token)
                client.messages.create(
                    body=f"Your CityPattle verification code is {otp_code}",
                    from_=from_number,
                    to=country_code + phone_number
                )
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
                'user_id': user_id
            }
        }, status=status.HTTP_200_OK)

#-------------------------
#Email OTP Varification
#-------------------------
@method_decorator(csrf_exempt, name='dispatch')
class EmailOTPAPIView(APIView):
    def post(self, request):
        email = request.data.get('email')

        if not email:
            return Response({
                'status': False,
                'message': 'email is required',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        otp_code = f"{random.randint(1000, 9999)}"

        try:
            send_mail(
                "CityPattle verification code",
                f"Your CityPattle verification code is {otp_code}",
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False
            )
        except Exception as exc:
            return Response({
                'status': False,
                'message': f'Failed to send email OTP: {str(exc)}',
                'data': None
            }, status=status.HTTP_502_BAD_GATEWAY)

        # ⚠️ Returning OTP in response is useful for testing, but unsafe for production
        return Response({
            'status': True,
            'message': 'OTP sent successfully on email',
            'data': {
                'otp': otp_code,
                'email': email
            }
        }, status=status.HTTP_200_OK)
#-------------------------
#Email OTP Varification
#-------------------------
@method_decorator(csrf_exempt, name='dispatch')
class SmsOTPAPIView(APIView):
    def post(self, request):
        phone_number = request.data.get('phone_number')
        country_code = request.data.get("country_code")

        if not country_code:
            return Response({
                'status': False,
                'message': 'phone_number is required',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        if not phone_number:
            return Response({
                'status': False,
                'message': 'country_code is required',
                'data': None
            }, status=status.HTTP_400_BAD_REQUEST)

        otp_code = f"{random.randint(1000, 9999)}"
        user_id = None

        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        from_number = getattr(settings, 'TWILIO_FROM_NUMBER', '')

        if not all([account_sid, auth_token, from_number]):
            return Response({
                'status': False,
                'message': 'Twilio is not configured',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if Client is None:
            return Response({
                'status': False,
                'message': 'Twilio SDK not installed',
                'data': None
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            client = Client(account_sid, auth_token)
            client.messages.create(
                body=f"Your CityPattle verification code is {otp_code}",
                from_=from_number,
                to=country_code + phone_number
            )
            try:
                user = User.objects.get(phone_number=phone_number)
                user_id = user.id
            except User.DoesNotExist:
                pass
        except Exception as exc:
            return Response({
                'status': False,
                'message': 'Failed to send OTP',
                'data': None
            }, status=status.HTTP_502_BAD_GATEWAY)

        return Response({
            'status': True,
            'message': 'OTP sent successfully via SMS',
            'data': {
                'otp': otp_code,
                'user_id': user_id
            }
        }, status=status.HTTP_200_OK)

# ----------------------------
# Reset Password API
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class ResetPasswordAPIView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")
        new_password = request.data.get("new_password")

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
            user.password_hash = make_password(str(new_password))
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

# ----------------------------
# Venues API
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class VenueAPIView(APIView):
    def get(self, request):
        venues = Venue.objects.all()
        data = []

        for venue in venues:
            country = venue.city.country  # shortcut

            data.append({
                "id": venue.id,
                "name": venue.name,
                "address": venue.address,
                "club": venue.club,
                "contact": venue.contact,
                "map_url": venue.map_url,
                "opening_time": venue.opening_time.strftime("%I:%M %p") if venue.opening_time else None,
                "closing_time": venue.closing_time.strftime("%I:%M %p") if venue.closing_time else None,
                "price": float(venue.price),
                "ratings": venue.ratings,
                "created_at": venue.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "city": venue.city.name,
                "state": venue.city.state.name,
                "country": country.name,
                "iso_code": getattr(country, "iso_code", None),       # 👈 ISO code
                "phone_code": getattr(country, "phone_code", None),   # 👈 Phone code
                "images": [request.build_absolute_uri(img.image.url) for img in venue.images.all()]
            })

        return Response(data, status=status.HTTP_200_OK)

# ----------------------------
# Slots of Venues API
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class GenerateSlotsAPIView(APIView):
    """
    Generate 1-hour slots for a given venue and date.
    POST request with JSON: {"venue_id": 1, "date": "2025-09-18"}
    """
    def post(self, request):
        venue_id = request.data.get("venue_id")
        date_str = request.data.get("date")

        if not venue_id or not date_str:
            return Response(
                {"status": False, "message": "Both 'venue_id' and 'date' are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            slot_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"status": False, "message": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            venue = Venue.objects.get(id=venue_id)
        except Venue.DoesNotExist:
            return Response(
                {"status": False, "message": "Venue not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not venue.opening_time or not venue.closing_time:
            return Response(
                {"status": False, "message": "Venue opening or closing time not set"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 🔹 Fetch all booked slots for that venue & date
        booked_slots = Slot.objects.filter(
            venue=venue,
            date=slot_date,
            is_booked=True
        ).values("start_time", "end_time")

        booked_set = {(s["start_time"], s["end_time"]) for s in booked_slots}

        # 🔹 Generate slots
        slots_list = []
        current_time = datetime.combine(slot_date, venue.opening_time)
        closing_time = datetime.combine(slot_date, venue.closing_time)

        while current_time < closing_time:
            end_time = current_time + timedelta(hours=1)

            # Mark slot as booked if it exists in DB booked_set
            is_booked = (current_time.time(), end_time.time()) in booked_set

            slots_list.append({
                "start_time": current_time.strftime("%I:%M %p"),
                "end_time": end_time.strftime("%I:%M %p"),
                "price": float(venue.price),  # use venue price for all generated slots
                "is_booked": is_booked
            })

            current_time = end_time

        return Response({
            "status": True,
            "message": f"Slots generated for {venue.name} on {slot_date}",
            "data": slots_list
        }, status=status.HTTP_200_OK)
