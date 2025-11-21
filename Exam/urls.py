from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QuestionViewSet, OptionViewSet, ExamViewSet, ExamSectionViewSet,
    StudentExamViewSet, ExaminerViewSet
)

router = DefaultRouter()
router.register(r"questions", QuestionViewSet, basename="questions")
router.register(r"options", OptionViewSet, basename="options")
router.register(r"exams", ExamViewSet, basename="exams")
router.register(r"sections", ExamSectionViewSet, basename="sections")
# student endpoints (not a ModelViewSet) exposed as viewset actions
router.register(r"student-exams", StudentExamViewSet, basename="student-exams")
router.register(r"examiner", ExaminerViewSet, basename="examiner")

urlpatterns = [
    path("", include(router.urls)),
]
