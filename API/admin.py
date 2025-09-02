from django.contrib import admin
from .models import Country, User, Venue, Slot, Booking

@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Country._meta.fields]

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = [field.name for field in User._meta.fields]

@admin.register(Venue)
class UserAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Venue._meta.fields]

@admin.register(Slot)
class UserAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Slot._meta.fields]

@admin.register(Booking)
class UserAdmin(admin.ModelAdmin):
    list_display = [field.name for field in Booking._meta.fields]
