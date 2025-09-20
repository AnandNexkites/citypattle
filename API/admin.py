from django.contrib import admin
from .models import Country, State, City, User, Venue, Slot, Booking, VenueImage, FCMToken, UserVerification

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Country._meta.fields]

@admin.register(State)
class StateAdmin(admin.ModelAdmin):
    list_display = [field.name for field in State._meta.fields]

@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = [field.name for field in City._meta.fields]

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [field.name for field in User._meta.fields]
    
@admin.register(UserVerification)
class UserVerificationAdmin(admin.ModelAdmin):
    list_display = [field.name for field in UserVerification._meta.fields]

@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Venue._meta.fields]

@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Slot._meta.fields]

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Booking._meta.fields]

@admin.register(VenueImage)
class VenueImageAdmin(admin.ModelAdmin):
    list_display = [field.name for field in VenueImage._meta.fields]

@admin.register(FCMToken)
class FCMTokenAdmin(admin.ModelAdmin):
    list_display = [field.name for field in FCMToken._meta.fields]
