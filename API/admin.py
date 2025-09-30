from django.contrib import admin
from .models import Country, SavedVenue, State, City, User, Venue, Slot, Booking, VenueImage, FCMToken, UserVerification

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

@admin.register(SavedVenue)
class VenueAdmin(admin.ModelAdmin):
    list_display = [field.name for field in SavedVenue._meta.fields]

@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Slot._meta.fields]

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Booking._meta.fields] + ['display_slots']

    def display_slots(self, obj):
        # Shows start and end time of all slots in the booking
        return ", ".join([f"{slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}" 
                          for slot in obj.slots.all()])
    display_slots.short_description = "Slots"

@admin.register(VenueImage)
class VenueImageAdmin(admin.ModelAdmin):
    list_display = [field.name for field in VenueImage._meta.fields]

@admin.register(FCMToken)
class FCMTokenAdmin(admin.ModelAdmin):
    list_display = [field.name for field in FCMToken._meta.fields]
