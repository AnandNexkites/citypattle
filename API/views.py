from django.shortcuts import render
from rest_framework.views import APIView
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.response import Response
from rest_framework import status
from .models import FCMToken, SavedVenue, Slot, User, Venue, Country, City,UserVerification, Booking
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
from firebase_admin import messaging
try:
    from CityPattle import firebase_config
    print("Firebase config imported successfully")
except Exception as e:
    print("Import error:", e)

from django.shortcuts import get_object_or_404
import razorpay
import threading
from datetime import timedelta


#-----------------------------------------------------------------------------------------------------
# Helper functions
#----------------------------------------------------------------------------------------------------
import requests
def send_push_notification(user_id: int, title: str, body: str):
    """
    Sends a push notification to all active FCM tokens of a user.
    """
    print("--------push notification function called--------")
    print(f"--------user id is {user_id} title is {title} and body is {body} --------")
    # Fetch all active tokens for this user
    tokens = FCMToken.objects.filter(user_id=user_id, is_active=True).values_list('token', flat=True)

    if not tokens:
        print("--------No tocken found--------")
        return {"status": False, "message": "No active FCM tokens found for this user."}


    results = []
    for token in tokens:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            token=token
        )
        try:
            response = messaging.send(message)
            results.append({"token": token, "status": True, "message": response})
        except Exception as e:
            results.append({"token": token, "status": False, "message": str(e)})
    print("--------push notification send suceccfully--------")

    return {"status": True, "results": results}
#----------------------------------------------------------------------------------------------------------------------------------------------------------------------

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
        fcm_token = request.data.get("fcm_token")  # <-- Get FCM token from request
        device_type = request.data.get("device_type", "android")  # optional, default to android

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

            # -------------------------------
            # Save FCM token for this user
            # -------------------------------
            if fcm_token:
                save_fcm_token(user, fcm_token, device_type)

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
                status=400
            )

        try:
            slot_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"status": False, "message": "Invalid date format. Use YYYY-MM-DD."},
                status=400
            )

        try:
            venue = Venue.objects.get(id=venue_id)
        except Venue.DoesNotExist:
            return Response(
                {"status": False, "message": "Venue not found"},
                status=404
            )

        if not venue.opening_time or not venue.closing_time:
            return Response(
                {"status": False, "message": "Venue opening or closing time not set"},
                status=400
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
        now = datetime.now()  # current time to compare

        while current_time < closing_time:
            end_time = current_time + timedelta(hours=1)

            # Mark slot as booked if it exists in DB booked_set
            is_booked = (current_time.time(), end_time.time()) in booked_set

            # ✅ If slot is not booked but end time has passed, mark it as booked
            if not is_booked and end_time <= now:
                is_booked = True

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
        }, status=200)
#----------------------------
# test notification api
#----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class TestNotificationAPIView(APIView):
    """
    Send a test push notification to a device using FCM token.
    POST request with JSON:
    {
        "token": "DEVICE_FCM_TOKEN",
        "title": "Hello",
        "body": "This is a test notification"
    }
    """

    def post(self, request):
        token = request.data.get("token")
        title = request.data.get("title", "Test Notification")
        body = request.data.get("body", "Hello from Django FCM!")

        if not token:
            return Response(
                {"status": False, "message": "FCM token is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Build notification message
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=token,
            data={  # optional custom payload
                "click_action": "FLUTTER_NOTIFICATION_CLICK",
                "id": "1",
                "status": "done"
            }
        )

        try:
            response = messaging.send(message)
            return Response(
                {"status": True, "message": "Notification sent", "response": response},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"status": False, "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


#-----------------------------------------
# Booking a slot API
#-----------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class BookSlotsAPIView(APIView):
    """
    Book multiple slots for a venue with payment info.
    POST request JSON:
    {
        "user_id": 1,
        "venue_id": 1,
        "date": "2025-09-18",
        "slots": [
            {"start_time": "10:00", "end_time": "11:00"},
            {"start_time": "11:00", "end_time": "12:00"}
        ],
        "amount": 200.0,
        "transaction_id": "TXN123456",
        "razorpay_order_id": "order_ABC123",
        "razorpay_payment_id": "pay_XYZ456",
        "razorpay_signature": "signature_string"
    }
    """
    def post(self, request):
        data = request.data
        user_id = data.get("user_id")
        venue_id = data.get("venue_id")
        date_str = data.get("date")
        slots_data = data.get("slots", [])
        amount = data.get("amount")
        transaction_id = data.get("transaction_id")
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        if not user_id or not venue_id or not date_str or not slots_data or not amount:
            return Response({
                "status": False,
                "message": "Required fields missing",
                "data": None
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
            venue = Venue.objects.get(id=venue_id)
            slot_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except User.DoesNotExist:
            return Response({"status": False, "message": "User not found", "data": None}, status=status.HTTP_404_NOT_FOUND)
        except Venue.DoesNotExist:
            return Response({"status": False, "message": "Venue not found", "data": None}, status=status.HTTP_404_NOT_FOUND)
        except ValueError:
            return Response({"status": False, "message": "Invalid date format", "data": None}, status=status.HTTP_400_BAD_REQUEST)

        booked_slots = []
        for s in slots_data:
            try:
                start_time = datetime.strptime(s["start_time"], "%H:%M").time()
                end_time = datetime.strptime(s["end_time"], "%H:%M").time()
            except ValueError:
                return Response({
                    "status": False,
                    "message": "Invalid time format in slots. Use HH:MM",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check if slot already exists
            slot_obj, created = Slot.objects.get_or_create(
                venue=venue,
                date=slot_date,
                start_time=start_time,
                end_time=end_time,
                defaults={"price": amount, "is_booked": True}
            )

            if not created and slot_obj.is_booked:
                return Response({
                    "status": False,
                    "message": f"Slot {s['start_time']}-{s['end_time']} is already booked",
                    "data": None
                }, status=status.HTTP_400_BAD_REQUEST)

            # Mark as booked
            slot_obj.is_booked = True
            slot_obj.price = amount
            slot_obj.save()

            # Create booking entry
            booking = Booking.objects.create(
                user=user,
                venue=venue,
                slot=slot_obj,
                amount=amount,
                payment_status="paid",
                transaction_id=transaction_id,
                razorpay_order_id=razorpay_order_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_signature=razorpay_signature
            )

            booked_slots.append({
                "slot_id": slot_obj.id,
                "start_time": slot_obj.start_time.strftime("%H:%M"),
                "end_time": slot_obj.end_time.strftime("%H:%M"),
                "booking_id": booking.id
            })

        return Response({
            "status": True,
            "message": f"{len(booked_slots)} slot(s) booked successfully",
            "data": booked_slots
        }, status=status.HTTP_200_OK)

#-----------------------------------------
# Booking a slot API and getting order id
#-----------------------------------------

razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

@method_decorator(csrf_exempt, name='dispatch')
class CreateBookingAPIView(APIView):
    def post(self, request):
        data = request.data
        user_id = data.get("user_id")
        venue_id = data.get("venue_id")
        date = data.get("date")
        slots_data = data.get("slots", [])
        total_amount = data.get("amount")

        # ----------------
        # Validations
        # ----------------
        if not user_id:
            return Response({"status": False, "message": "User ID required."}, status=status.HTTP_400_BAD_REQUEST)
        if not venue_id:
            return Response({"status": False, "message": "Venue ID required."}, status=status.HTTP_400_BAD_REQUEST)
        if not date:
            return Response({"status": False, "message": "Date required."}, status=status.HTTP_400_BAD_REQUEST)
        if not slots_data:
            return Response({"status": False, "message": "Slots required."}, status=status.HTTP_400_BAD_REQUEST)
        if not total_amount:
            return Response({"status": False, "message": "Amount required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = get_object_or_404(User, id=user_id)
            venue = get_object_or_404(Venue, id=venue_id)

            # -------------------------------
            # Check for pending bookings
            # -------------------------------
            pending_booking = Booking.objects.filter(
                user=user, venue=venue, payment_status="pending"
            ).first()

            if pending_booking:
                for slot in pending_booking.slots.all():
                    slot.is_booked = False
                    slot.save()
                pending_booking.delete()
                print(f"⚠️ Previous pending booking deleted for user {user_id}")

            # -------------------------------
            # Create / mark slots
            # -------------------------------
            created_slots = []
            for slot_info in slots_data:
                start_time_obj = datetime.strptime(slot_info["start_time"], "%I:%M %p").time()
                end_time_obj = datetime.strptime(slot_info["end_time"], "%I:%M %p").time()

                existing_slot = Slot.objects.filter(
                    venue=venue,
                    date=date,
                    start_time=start_time_obj,
                    end_time=end_time_obj
                ).first()

                if existing_slot:
                    if existing_slot.is_booked:
                        return Response({
                            "status": False,
                            "message": f"Slot {slot_info['start_time']} - {slot_info['end_time']} is already booked."
                        }, status=status.HTTP_400_BAD_REQUEST)
                    slot = existing_slot
                    slot.is_booked = True
                    slot.save()
                else:
                    slot = Slot.objects.create(
                                        venue=venue,
                                        date=date,
                                        start_time=start_time_obj,
                                        end_time=end_time_obj,
                                        price=venue.price,  # <-- use the price from Venue model
                                        is_booked=True
                                    )
                created_slots.append(slot)

            # -------------------------------
            # Create Razorpay order
            # -------------------------------
            razorpay_order = razorpay_client.order.create({
                "amount": int(float(total_amount) * 100),
                "currency": "INR",
                "payment_capture": 1
            })

            # -------------------------------
            # Create new booking
            # -------------------------------
            booking = Booking.objects.create(
                user=user,
                venue=venue,
                amount=total_amount,
                razorpay_order_id=razorpay_order["id"],
                payment_status="pending"
            )
            booking.slots.set(created_slots)

            # -------------------------------
            # Auto-delete after 10 minutes if payment is pending
            # -------------------------------
            def auto_delete_booking(booking_id, user_id):
                try:
                    booking_obj = Booking.objects.get(id=booking_id)
                    if booking_obj.payment_status == "pending" and timezone.now() > booking_obj.created_at + timedelta(minutes=10):
                        for slot in booking_obj.slots.all():
                            slot.is_booked = False
                            slot.save()
                        booking_obj.delete()
                        print(f"Booking {booking_id} deleted due to non-payment.")

                        # 🔔 Send push notification to user
                        send_push_notification(
                            user_id=user_id,
                            title="Booking Cancelled",
                            body=f"Your booking (ID: {booking_id}) was cancelled due to non-payment."
                        )
                except Booking.DoesNotExist:
                    pass

            threading.Timer(600, auto_delete_booking, args=[booking.id, user.id]).start()

            # -------------------------------
            # Return booking response
            # -------------------------------
            return Response({
                "status": True,
                "message": "Booking created. Complete payment to confirm.",
                "data": {
                    "booking_id": booking.id,
                    "razorpay_order_id": razorpay_order["id"],
                    "amount": total_amount,
                    "currency": "INR",
                    "slots": [
                        {
                            "id": s.id,
                            "start_time": s.start_time.strftime("%H:%M"),
                            "end_time": s.end_time.strftime("%H:%M"),
                            "date": str(s.date),
                            "price": str(s.price)
                        } for s in created_slots
                    ]
                }
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#----------------------------------------------------
# varify the payment and set booking status to paid
#---------------------------------------------------

@method_decorator(csrf_exempt, name='dispatch')
class UpdateBookingPaymentAPIView(APIView):
    def post(self, request):
        data = request.data
        booking_id = data.get("booking_id")
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        if not all([booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response(
                {"status": False, "message": "All payment fields required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            booking = get_object_or_404(Booking, id=booking_id, razorpay_order_id=razorpay_order_id)

            # ✅ Step 1: Verify signature
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            try:
                razorpay_client.utility.verify_payment_signature(params_dict)
            except Exception as e:
                booking.payment_status = "failed"
                booking.save()
                return Response(
                    {"status": False, "message": f"Signature verification failed: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Step 2: Fetch payment details from Razorpay
            payment = razorpay_client.payment.fetch(razorpay_payment_id)

            if payment["status"] == "captured":  # 👈 Payment successfully received
                booking.razorpay_payment_id = razorpay_payment_id
                booking.razorpay_signature = razorpay_signature
                booking.transaction_id = razorpay_payment_id  # Treat this as transaction_id
                booking.payment_status = "paid"
                booking.save()

                # 🔔 Send push notification to user
                send_push_notification(
                    user_id=booking.user.id,
                    title="Booking Confirmed",
                    body=f"Your booking (ID: {booking.id}) has been confirmed."
                )

                return Response({
                    "status": True,
                    "message": "Payment verified & booking confirmed.",
                    "data": {
                        "booking_id": booking.id,
                        "transaction_id": booking.transaction_id,
                        "payment_status": booking.payment_status
                    }
                }, status=status.HTTP_200_OK)

            else:
                # Payment not captured (could be authorized but not captured)
                booking.payment_status = "failed"
                booking.save()
                return Response({
                    "status": False,
                    "message": f"Payment not successful. Current status: {payment['status']}"
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

#----------------------------------------------------
# send push notification
#---------------------------------------------------

# @method_decorator(csrf_exempt, name='dispatch')
# class SendPushNotificationAPIView(APIView):
#     def post(self, request):
#         user_id = request.data.get("user_id")
#         title = request.data.get("title")
#         body = request.data.get("body")

#         if not all([user_id, title, body]):
#             return Response(
#                 {"status": False, "message": "user_id, title, and body are required."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         try:
#             # Send notification
#             result = send_push_notification(user_id, title, body)
#             return Response(result, status=status.HTTP_200_OK if result.get("status") else status.HTTP_400_BAD_REQUEST)

#         except Exception as e:
#             return Response(
#                 {"status": False, "message": str(e)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


#----------------------------------------------------
# Save venue API
#---------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class SaveVenueAPIView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")
        venue_id = request.data.get("venue_id")

        if not user_id or not venue_id:
            return Response({
                "status": False,
                "message": "user_id and venue_id are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(User, id=user_id)
        venue = get_object_or_404(Venue, id=venue_id)

        # Check if already saved
        if SavedVenue.objects.filter(user=user, venue=venue).exists():
            return Response({
                "status": False,
                "message": "Venue already saved."
            }, status=status.HTTP_400_BAD_REQUEST)

        saved_venue = SavedVenue.objects.create(user=user, venue=venue)

        return Response({
            "status": True,
            "message": "Venue saved successfully.",
            "data": {
                "saved_venue_id": saved_venue.id,
                "user_id": user.id,
                "venue_id": venue.id,
                "venue_name": venue.name,
                "created_at": saved_venue.created_at.isoformat()
            }
        }, status=status.HTTP_201_CREATED)

#----------------------------------------------------
# Fetch saved venues
#---------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class ListSavedVenuesAPIView(APIView):
    def post(self, request):
        # Get user_id from request body
        user_id = request.data.get("user_id")
        if not user_id:
            return Response({
                "status": False,
                "message": "user_id is required.",
                "data": []
            }, status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(User, id=user_id)
        saved_venues = SavedVenue.objects.filter(user=user).select_related(
            "venue__city__state__country"
        ).prefetch_related("venue__images")

        data = []
        for sv in saved_venues:
            venue = sv.venue
            country = venue.city.country if venue.city else None

            data.append({
                "id": venue.id,
                "name": venue.name,
                "address": venue.address,
                "club": venue.club,
                "contact": venue.contact,
                "map_url": venue.map_url,
                "opening_time": venue.opening_time.strftime("%I:%M %p") if venue.opening_time else None,
                "closing_time": venue.closing_time.strftime("%I:%M %p") if venue.closing_time else None,
                "price": float(venue.price) if venue.price else 0,
                "ratings": venue.ratings,
                "created_at": venue.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "city": venue.city.name if venue.city else None,
                "state": venue.city.state.name if venue.city else None,
                "country": country.name if country else None,
                "iso_code": getattr(country, "iso_code", None),
                "phone_code": getattr(country, "phone_code", None),
                "images": [request.build_absolute_uri(img.image.url) for img in venue.images.all()]
            })

        return Response({
            "status": True,
            "message": f"{len(data)} venues saved by user.",
            "data": data
        }, status=status.HTTP_200_OK)

#----------------------------------------------------
#  Unsavesaved venues
#---------------------------------------------------
@method_decorator(csrf_exempt, name='dispatch')
class UnsaveVenueAPIView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")
        venue_id = request.data.get("venue_id")

        if not user_id or not venue_id:
            return Response({
                "status": False,
                "message": "user_id and venue_id are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = get_object_or_404(User, id=user_id)
        venue = get_object_or_404(Venue, id=venue_id)

        # Check if venue is saved
        saved_venue = SavedVenue.objects.filter(user=user, venue=venue).first()
        if not saved_venue:
            return Response({
                "status": False,
                "message": "Venue is not saved by this user."
            }, status=status.HTTP_404_NOT_FOUND)

        saved_venue.delete()

        return Response({
            "status": True,
            "message": "Venue unsaved successfully.",
            "data": {
                "user_id": user.id,
                "venue_id": venue.id,
                "venue_name": venue.name,
            }
        }, status=status.HTTP_200_OK)

# ----------------------------
# ACTIVE BOOKINGS API
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class UserBookingsAPIView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")

        if not user_id:
            return Response(
                {"status": False, "message": "User ID required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = get_object_or_404(User, id=user_id)
            bookings = Booking.objects.filter(user=user).order_by("-created_at")

            booking_list = []
            now = datetime.now()

            for booking in bookings:
                # ✅ Keep only slots that are still valid (end time not passed yet)
                valid_slots = []
                for slot in booking.slots.all():
                    slot_end = datetime.combine(slot.date, slot.end_time)
                    if slot_end >= now:  # include future or ongoing slots
                        valid_slots.append(slot)

                # Skip this booking if no valid slots
                if not valid_slots:
                    continue

                # Include booking (pending or confirmed) if at least one slot is valid
                booking_list.append(self.serialize_booking(booking, valid_slots, user))

            if not booking_list:
                return Response(
                    {"status": False, "message": "No active bookings"},
                    status=status.HTTP_200_OK
                )

            return Response({
                "status": True,
                "message": "User bookings fetched successfully.",
                "data": booking_list
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def serialize_booking(self, booking, slots, user):
        return {
            "booking_id": booking.id,
            "venue": {
                "id": booking.venue.id,
                "name": booking.venue.name,
                "contact":booking.venue.contact,
                "club":booking.venue.club,
                "address": booking.venue.address,
                "price_per_slot": str(getattr(booking.venue, "price", 0))
            },
            "amount": str(booking.amount),
            "payment_status": booking.payment_status,
            "razorpay_order_id": booking.razorpay_order_id,
            "transaction_id": booking.razorpay_payment_id,
            "created_at": timezone.localtime(booking.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            "slots": [
                {
                    "id": slot.id,
                    "date": str(slot.date),
                    "start_time": slot.start_time.strftime("%I:%M %p"),
                    "end_time": slot.end_time.strftime("%I:%M %p"),
                    "price": str(slot.price)
                }
                for slot in slots
            ],
            "qr_data": {
                "booking_id": booking.id,
                "user": user.full_name or user.email,
                "venue": booking.venue.name,
                "amount": str(booking.amount),
                "payment_status": booking.payment_status,
                "slots": [
                    {
                        "date": str(slot.date),
                        "start_time": slot.start_time.strftime("%I:%M %p"),
                        "end_time": slot.end_time.strftime("%I:%M %p"),
                    }
                    for slot in slots
                ]
            }
        }


# ----------------------------
# BOOKING HISTORY API
# ----------------------------
@method_decorator(csrf_exempt, name='dispatch')
class UserBookingHistoryAPIView(APIView):
    def post(self, request):
        user_id = request.data.get("user_id")

        if not user_id:
            return Response(
                {"status": False, "message": "User ID required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = get_object_or_404(User, id=user_id)
            bookings = Booking.objects.filter(user=user).order_by("-created_at")

            booking_list = []
            now = datetime.now()

            for booking in bookings:
                # ✅ Keep only slots that have fully ended
                expired_slots = []
                for slot in booking.slots.all():
                    slot_end = datetime.combine(slot.date, slot.end_time)
                    if slot_end < now:  # only past slots
                        expired_slots.append(slot)

                # Skip booking if not all slots have expired
                if len(expired_slots) != booking.slots.count():
                    continue

                booking_list.append(self.serialize_booking(booking, expired_slots, user))

            if not booking_list:
                return Response(
                    {"status": False, "message": "No past bookings"},
                    status=status.HTTP_200_OK
                )

            return Response({
                "status": True,
                "message": "Booking history fetched successfully.",
                "data": booking_list
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"status": False, "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def serialize_booking(self, booking, slots, user):
        return {
            "booking_id": booking.id,
            "venue": {
                "id": booking.venue.id,
                "name": booking.venue.name,
                "contact":booking.venue.contact,
                "club":booking.venue.club,
                "address": booking.venue.address,
                "price_per_slot": str(getattr(booking.venue, "price", 0))
            },
            "amount": str(booking.amount),
            "payment_status": booking.payment_status,
            "razorpay_order_id": booking.razorpay_order_id,
            "transaction_id": booking.razorpay_payment_id,
            "created_at": timezone.localtime(booking.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            "slots": [
                {
                    "id": slot.id,
                    "date": str(slot.date),
                    "start_time": slot.start_time.strftime("%I:%M %p"),
                    "end_time": slot.end_time.strftime("%I:%M %p"),
                    "price": str(slot.price)
                }
                for slot in slots
            ],
            "qr_data": {
                "booking_id": booking.id,
                "user": user.full_name or user.email,
                "venue": booking.venue.name,
                "amount": str(booking.amount),
                "payment_status": booking.payment_status,
                "slots": [
                    {
                        "date": str(slot.date),
                        "start_time": slot.start_time.strftime("%I:%M %p"),
                        "end_time": slot.end_time.strftime("%I:%M %p"),
                    }
                    for slot in slots
                ]
            }
        }