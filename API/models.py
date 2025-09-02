from django.db import models

# Create your models here.

class Country(models.Model):
    name = models.CharField(max_length=100)
    iso_code = models.CharField(max_length=5)
    phone_code = models.CharField(max_length=5)
    flag_url = models.TextField()

    def __str__(self):
        return self.name

class User(models.Model):
    full_name = models.CharField(max_length=100)
    username = models.CharField(max_length=50, unique=True)
    email = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=15, unique=True)
    password_hash = models.TextField()
    city = models.CharField(max_length=100)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username

class Venue(models.Model):
    name = models.CharField(max_length=150)
    image_url = models.URLField()
    address = models.TextField()
    hours = models.CharField(max_length=50)  # e.g. "7am - 2am"
    phone = models.CharField(max_length=20)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    rating = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Slot(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name="slots")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_booked = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.venue.name} - {self.date} {self.start_time}-{self.end_time}"

class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookings")
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE)
    slot = models.ForeignKey(Slot, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(
        max_length=20,
        choices=[("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed")],
        default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking {self.id} - {self.user.username} - {self.venue.name}"
