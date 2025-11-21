from django.contrib import admin
from .models import Question, Option, Exam, ExamSection, ExamAttempt, StudentAnswer, SectionScore, OSCEMark


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "question_type", "maximum_mark", "created_by", "created_at")
    search_fields = ("text_question",)
    list_filter = ("question_type",)

@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "text_option", "is_correct")
    list_filter = ("is_correct",)

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "target_level", "is_published", "scheduled_date")
    list_filter = ("is_published", "target_level")

@admin.register(ExamSection)
class ExamSectionAdmin(admin.ModelAdmin):
    list_display = ("id", "exam", "name", "section_type", "time_lapse_seconds", "order")
    list_filter = ("section_type",)

@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ("id", "exam", "student", "status", "total_score", "started_at", "submitted_at")
    list_filter = ("status",)

@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "question", "selected_option", "mark_gained", "graded_by", "graded_at")
    list_filter = ("graded_by",)

@admin.register(SectionScore)
class SectionScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "attempt", "section", "score")
