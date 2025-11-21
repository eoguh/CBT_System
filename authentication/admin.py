from django.contrib import admin
from .models import User





@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "first_name", "last_name", "is_student", "is_exam_manager", "is_examiner", "level")
    search_fields = ("username", "first_name", "last_name", "email")
    list_filter = ("is_student", "is_exam_manager", "is_examiner", "level")
