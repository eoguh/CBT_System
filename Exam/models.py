from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from authentication.models import User

# ----- Questions & Options -----
class Question(models.Model):
    OBJECTIVE = "OBJECTIVE"
    OSCE = "OSCE"
    THEORY = "THEORY"
    TYPE_CHOICES = [
        (OBJECTIVE, "Objective (MCQ)"),
        (OSCE, "OSCE (Practical/Oral)"),
        (THEORY, "Theory / Essay"),
    ]

    question_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    text_question = models.TextField(blank=True, null=True)
    image_question = models.ImageField(upload_to="questions/", blank=True, null=True)
    maximum_mark = models.DecimalField(max_digits=6, decimal_places=2, default=1.0, validators=[MinValueValidator(0)])
    # For essay/OSCE extra fields if needed:
    # essay_image etc. (omitted, reuse text_question/image_question)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_questions")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Q{self.pk} ({self.question_type})"


class Option(models.Model):
    # Options are tied to a question (only for objective questions)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options")
    text_option = models.TextField(blank=True, null=True)
    image_option = models.ImageField(upload_to="options/", blank=True, null=True)

    # is_correct is optional because we may have single-correct scenario (we will also store correct reference).
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"Option {self.pk} for Q{self.question_id}"


# If you'd rather keep a single correct FK in Question, you can, but here we support Option.is_correct as the source of truth.
# ----- Exam structure -----
class Exam(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    target_level = models.CharField(max_length=20, choices=User.LEVEL_CHOICES, blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="exams_created")
    scheduled_date = models.DateTimeField(blank=True, null=True)
    # published flag
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} (id={self.pk})"


class ExamSection(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=200)
    section_type = models.CharField(max_length=20, choices=Question.TYPE_CHOICES)
    time_lapse_seconds = models.PositiveIntegerField(default=0, help_text="Time allowed in seconds for this section (0 => unlimited)")
    # ManyToMany to collect questions for the section. Order can be controlled with through model if needed.
    questions = models.ManyToManyField(Question, related_name="sections", blank=True)

    order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.section_type})"


# ----- Student attempts and answers -----
class ExamAttempt(models.Model):
    STATUS_CHOICES = [
        ("IN_PROGRESS", "In Progress"),
        ("SUBMITTED", "Submitted"),
        ("GRADED", "Graded"),
    ]
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="IN_PROGRESS")
    total_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"Attempt {self.pk} by {self.student} on {self.exam}"


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="answers")
    section = models.ForeignKey(ExamSection, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="student_answers")
    selected_option = models.ForeignKey(Option, on_delete=models.SET_NULL, null=True, blank=True)  # for objective                                                                                                                                                                                                                                                                                                                      
    essay_answer = models.TextField(blank=True, null=True)  # for theory
    # Examiner can set mark_gained
    mark_gained = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="graded_answers")
    graded_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"Answer Q{self.question_id} by {self.attempt.student.username}"


# OSCE marks can be represented as StudentAnswer entries for OSCE questions (mark_gained set by examiner).
# But if you want separate model:
class OSCEMark(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="osce_marks")
    osce_question = models.ForeignKey(Question, on_delete=models.CASCADE, limit_choices_to={"question_type": Question.OSCE})
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mark_gained = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="osce_graded")
    graded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"OSCEMark Q{self.osce_question_id} - {self.student.username}"


# ----- SectionScore/ExamResult summary helper model (denormalized if you want) -----
class SectionScore(models.Model):
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name="section_scores")
    section = models.ForeignKey(ExamSection, on_delete=models.CASCADE)
    score = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        unique_together = ("attempt", "section")

    def __str__(self):
        return f"SectionScore {self.section.name} for attempt {self.attempt_id}"
