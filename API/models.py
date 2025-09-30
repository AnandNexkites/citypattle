from decimal import Decimal
from django.db import models


# ----------------------------
# Country Table
# ----------------------------
class Country(models.Model):
    name = models.CharField(max_length=100)
    iso_code = models.CharField(max_length=5)
    phone_code = models.CharField(max_length=5)
    flag = models.ImageField(upload_to="flags/", blank=True, null=True)  
    # Saves to MEDIA_ROOT/flags/filename.jpg

    def __str__(self):
        return self.name


# ----------------------------
# State Table
# ----------------------------
class State(models.Model):
    name = models.CharField(max_length=100)
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="states")

    def __str__(self):
        return f"{self.name}, {self.country.name}"


# ----------------------------
# City Table
# ----------------------------
class City(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name="cities")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="cities")

    def __str__(self):
        return f"{self.name}, {self.state.name}, {self.country.name}"


# ----------------------------
# User Table
# ----------------------------
class User(models.Model):
    full_name = models.CharField(max_length=100)
    email = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=15, unique=True)
    password_hash = models.TextField()  # ⚠️ Better: use AbstractUser
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name or self.email


# ----------------------------
# User Verification Table
# ----------------------------
class UserVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="verification")
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Verification for {self.user.full_name or self.user.email}"


# ----------------------------
# Venue Table
# ----------------------------
class Venue(models.Model):
    name = models.CharField(max_length=150)
    address = models.TextField()
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="venues")
    club = models.CharField(max_length=150, blank=True, null=True)  # e.g., "· Playground"
    contact = models.CharField(max_length=20, blank=True, null=True)  # store as string to preserve formatting
    map_url = models.URLField(blank=True, null=True)  # e.g., Google Maps link
    opening_time = models.TimeField(blank=True, null=True)  # e.g., 06:00 AM
    closing_time = models.TimeField(blank=True, null=True)  # e.g., 02:00 AM
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.0"))
    ratings = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.city.name}, {self.city.state.name}, {self.city.country.name})"
# ----------------------------
# Saved Venue Table
# ----------------------------
class SavedVenue(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_venues")
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="saved_by_users")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "venue")  # prevent duplicates

    def __str__(self):
        return f"{self.user.full_name} saved {self.venue.name}"
# ----------------------------
# Venue Images Table
# ----------------------------
class VenueImage(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="venues/")  
    # Saves to MEDIA_ROOT/venues/filename.jpg

    def __str__(self):
        return f"Image for {self.venue.name}"


# ----------------------------
# Slot Table
# ----------------------------
class Slot(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="slots")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_booked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.venue.name} - {self.date} {self.start_time}-{self.end_time}"


# ----------------------------
# Booking Table
# ----------------------------
# ----------------------------
# Booking Table
# ----------------------------
class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    slots = models.ManyToManyField(Slot, related_name="bookings")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    payment_status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed")],
        default="pending"
    )

    # Razorpay transaction identifiers
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(  # This is also your Transaction ID
        max_length=100, unique=True, blank=True, null=True
    )
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking {self.id} - {self.user.full_name} - {self.venue.name}"



# ----------------------------
# FCM Token Table
# ----------------------------
class FCMToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fcm_tokens")
    token = models.TextField(unique=True)  # The actual FCM token
    device_type = models.CharField(
        max_length=20,
        choices=[("android", "Android"), ("ios", "iOS"), ("web", "Web")],
        default="android"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    

    def __str__(self):
        return f"{self.user.email} - {self.device_type}"
