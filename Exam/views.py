import csv
import io

from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.parsers import MultiPartParser, JSONParser, FormParser
from rest_framework.response import Response

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from authentication.models import User
from authentication.permissions import IsAdmin, IsExamManager, IsExaminer
from .models import (
    Exam, 
    ExamSection, 
    Question, 
    Option, 
    ExamAttempt, 
    StudentAnswer, 
    SectionScore
)
from .serializers import (
    QuestionSerializer,
    OptionSerializer,
    ExamSerializer,
    ExamSectionSerializer,
    ExamAttemptSerializer,
    StudentAnswerSerializer,
    ExamSubmissionSerializer,
    ExamSubmissionResponseSerializer
)


# ---- Questions / Options / Exams / Sections (Exam Managers) ----
class QuestionViewSet(viewsets.ModelViewSet):
    queryset = Question.objects.all().prefetch_related("options")
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticated, IsExamManager]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context



class OptionViewSet(viewsets.ModelViewSet):
    queryset = Option.objects.all()
    serializer_class = OptionSerializer
    permission_classes = [permissions.IsAuthenticated, IsExamManager]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update({"request": self.request})
        return context



class ExamViewSet(viewsets.ModelViewSet):
    queryset = Exam.objects.all().prefetch_related("sections")
    serializer_class = ExamSerializer
    permission_classes = [permissions.IsAuthenticated, IsExamManager]

    @action(detail=True, methods=["get"], permission_classes=[permissions.IsAuthenticated, IsExamManager], url_path="results-table")
    def results_table(self, request, pk=None):
        """
        Returns results for all students for this exam:
        name, reg number (username), level, exam id, exam title, exam date, score for each section, and total score.
        """
        exam = self.get_object()
        attempts = exam.attempts.select_related("student").prefetch_related("section_scores__section")
        results = []
        sections = list(exam.sections.order_by("order"))
        for attempt in attempts:
            # build per-section scores dict
            per_section = {s.id: 0 for s in sections}
            section_scores = attempt.section_scores.all()
            for ss in section_scores:
                per_section[ss.section.id] = float(ss.score)
            total = float(attempt.total_score or 0)
            row = {
                "student_name": attempt.student.get_full_name(),
                "reg_number": attempt.student.username,
                "level": attempt.student.level,
                "exam_id": exam.id,
                "exam_title": exam.title,
                "exam_date": exam.scheduled_date,
                "per_section_scores": {s.name: per_section.get(s.id, 0) for s in sections},
                "total_score": total,
            }
            results.append(row)
        return Response({"results": results})


class ExamSectionViewSet(viewsets.ModelViewSet):
    queryset = ExamSection.objects.all().prefetch_related("questions")
    serializer_class = ExamSectionSerializer
    permission_classes = [permissions.IsAuthenticated, IsExamManager]
    parser_classes = (JSONParser,)

    @action(detail=True, methods=["post"], url_path="add-questions")
    def add_questions(self, request, pk=None):
        """
        Add questions to a section.
        Payload: {"question_ids": [1, 2, 3, 4]}
        """
        section = self.get_object()
        question_ids = request.data.get("question_ids", [])
        
        if not question_ids:
            return Response({"detail": "question_ids list is required"}, status=400)
        
        # Validate all questions exist
        questions = Question.objects.filter(id__in=question_ids)
        if questions.count() != len(question_ids):
            found_ids = list(questions.values_list('id', flat=True))
            missing_ids = [qid for qid in question_ids if qid not in found_ids]
            return Response({
                "detail": f"Questions not found: {missing_ids}"
            }, status=400)
        
        # Add questions to section
        section.questions.add(*questions)
        
        serializer = self.get_serializer(section)
        return Response({
            "detail": "Questions added successfully",
            "section": serializer.data
        })
    
    @action(detail=True, methods=["post"], url_path="remove-questions")
    def remove_questions(self, request, pk=None):
        """
        Remove questions from a section.
        Payload: {"question_ids": [1, 2]}
        """
        section = self.get_object()
        question_ids = request.data.get("question_ids", [])
        
        if not question_ids:
            return Response({"detail": "question_ids list is required"}, status=400)
        
        section.questions.remove(*question_ids)
        
        serializer = self.get_serializer(section)
        return Response({
            "detail": "Questions removed successfully",
            "section": serializer.data
        })
    
    @action(detail=True, methods=["post"], url_path="set-questions")
    def set_questions(self, request, pk=None):
        """
        Replace all questions in a section.
        Payload: {"question_ids": [1, 2, 3]}
        """
        section = self.get_object()
        question_ids = request.data.get("question_ids", [])
        
        # Clear existing questions
        section.questions.clear()
        
        if question_ids:
            # Validate all questions exist
            questions = Question.objects.filter(id__in=question_ids)
            if questions.count() != len(question_ids):
                found_ids = list(questions.values_list('id', flat=True))
                missing_ids = [qid for qid in question_ids if qid not in found_ids]
                return Response({
                    "detail": f"Questions not found: {missing_ids}"
                }, status=400)
            
            # Set new questions
            section.questions.set(questions)
        
        serializer = self.get_serializer(section)
        return Response({
            "detail": "Questions updated successfully",
            "section": serializer.data
        })




class StudentExamViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ExamSerializer
    queryset = Exam.objects.none()

    @action(detail=False, methods=["get"])
    def available(self, request):
        """List available exams for the student"""
        user = request.user
        qs = Exam.objects.filter(is_published=True).filter(
            Q(target_level=user.level) | Q(target_level__isnull=True)
        )
        serializer = ExamSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @extend_schema(
        summary="Start an exam attempt",
        description="Creates a new exam attempt for the authenticated student. Returns existing IN_PROGRESS attempt if one exists.",
        responses={
            200: ExamAttemptSerializer,
            201: ExamAttemptSerializer,
            403: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        }
    )
    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        """Start a new exam attempt"""
        try:
            exam = Exam.objects.get(pk=pk, is_published=True)
        except Exam.DoesNotExist:
            return Response({"detail": "Exam not found or not published."}, status=404)

        user = request.user
        if not user.is_student:
            return Response({"detail": "Only students can start exam attempts."}, status=403)

        if exam.target_level and exam.target_level != user.level:
            return Response({"detail": "This exam is not available for your level."}, status=403)

        existing = ExamAttempt.objects.filter(exam=exam, student=user, status="IN_PROGRESS").first()
        if existing:
            serializer = ExamAttemptSerializer(existing, context={"request": request})
            return Response(serializer.data, status=200)

        attempt = ExamAttempt.objects.create(exam=exam, student=user)
        serializer = ExamAttemptSerializer(attempt, context={"request": request})
        return Response(serializer.data, status=201)

    @extend_schema(
        summary="Get exam questions",
        description="Retrieves all questions for an exam. Student must have an active IN_PROGRESS attempt.",
        responses={
            200: OpenApiTypes.OBJECT,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
        }
    )
    @action(detail=True, methods=["get"], url_path="questions")
    def get_exam_questions(self, request, pk=None):
        """Get all questions for an exam (for taking the exam)"""
        try:
            exam = Exam.objects.prefetch_related(
                'sections__questions__options'
            ).get(pk=pk, is_published=True)
        except Exam.DoesNotExist:
            return Response({"detail": "Exam not found"}, status=404)
        
        attempt = ExamAttempt.objects.filter(
            exam=exam, 
            student=request.user, 
            status="IN_PROGRESS"
        ).first()
        
        if not attempt:
            return Response({"detail": "No active attempt found. Start exam first."}, status=400)
        
        sections_data = []
        for section in exam.sections.all().order_by('order'):
            questions_data = []
            for question in section.questions.all():
                q_data = {
                    'id': question.id,
                    'question_type': question.question_type,
                    'text_question': question.text_question,
                    'image_question': request.build_absolute_uri(question.image_question.url) if question.image_question else None,
                    'maximum_mark': float(question.maximum_mark),
                }
                
                if question.question_type == Question.OBJECTIVE:
                    q_data['options'] = [
                        {
                            'id': opt.id,
                            'text_option': opt.text_option,
                            'image_option': request.build_absolute_uri(opt.image_option.url) if opt.image_option else None,
                        }
                        for opt in question.options.all()
                    ]
                
                questions_data.append(q_data)
            
            sections_data.append({
                'id': section.id,
                'name': section.name,
                'section_type': section.section_type,
                'time_lapse_seconds': section.time_lapse_seconds,
                'questions': questions_data
            })
        
        return Response({
            'exam_id': exam.id,
            'exam_title': exam.title,
            'attempt_id': attempt.id,
            'sections': sections_data
        })

    @extend_schema(
        summary="Submit exam attempt",
        description="Submit all answers for an exam attempt. All questions must be answered. Objective questions are auto-graded.",
        request=ExamSubmissionSerializer,
        responses={
            200: ExamSubmissionResponseSerializer,
            400: OpenApiTypes.OBJECT,
            404: OpenApiTypes.OBJECT,
            500: OpenApiTypes.OBJECT,
        },
        examples=[
            OpenApiExample(
                'Submit Exam Example',
                value={
                    "attempt_id": 5,
                    "answers": [
                        {
                            "section": 1,
                            "question": 10,
                            "selected_option": 25
                        },
                        {
                            "section": 1,
                            "question": 11,
                            "selected_option": 28
                        },
                        {
                            "section": 2,
                            "question": 15,
                            "essay_answer": "This is my detailed essay answer explaining the concept..."
                        }
                    ]
                },
                request_only=True,
            ),
        ]
    )
    @action(detail=False, methods=["post"], url_path="submit")
    def submit(self, request):
        """
        Submit an exam attempt
        URL: POST /api/cbt/student-exams/submit/
        """
        # Validate input using serializer
        serializer = ExamSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        attempt_id = serializer.validated_data['attempt_id']
        answers = serializer.validated_data['answers']
        
        try:
            with transaction.atomic():
                # Lock the attempt to prevent concurrent submissions
                attempt = ExamAttempt.objects.select_for_update().select_related('exam').get(
                    pk=attempt_id,
                    student=request.user,
                    status="IN_PROGRESS"
                )
                
                # Validate all questions are answered
                all_sections = attempt.exam.sections.prefetch_related('questions').all()
                all_question_ids = set()
                for section in all_sections:
                    all_question_ids.update(section.questions.values_list('id', flat=True))
                
                if not all_question_ids:
                    return Response({"detail": "This exam has no questions"}, status=400)
                
                submitted_question_ids = {a['question'] for a in answers}
                missing_questions = all_question_ids - submitted_question_ids
                
                if missing_questions:
                    return Response({
                        "detail": "Not all questions have been answered",
                        "missing_question_ids": list(missing_questions)
                    }, status=400)
                
                # Pre-fetch all questions and sections to avoid N+1 queries
                question_ids = list(submitted_question_ids)
                section_ids = list({a['section'] for a in answers})
                
                questions_map = {q.id: q for q in Question.objects.prefetch_related('options').filter(id__in=question_ids)}
                sections_map = {s.id: s for s in ExamSection.objects.prefetch_related('questions').filter(id__in=section_ids)}
                
                # Validate sections belong to exam
                for section in sections_map.values():
                    if section.exam_id != attempt.exam_id:
                        return Response({
                            "detail": f"Section {section.id} does not belong to this exam"
                        }, status=400)
                
                # Process each answer
                for a in answers:
                    section_id = a['section']
                    qid = a['question']
                    selected_option_id = a.get('selected_option')
                    essay_answer = a.get('essay_answer', '').strip()
                    
                    question = questions_map.get(qid)
                    section = sections_map.get(section_id)
                    
                    if not question:
                        return Response({"detail": f"Question {qid} not found"}, status=400)
                    if not section:
                        return Response({"detail": f"Section {section_id} not found"}, status=400)
                    
                    # Validate question belongs to section
                    if not section.questions.filter(pk=question.pk).exists():
                        return Response({
                            "detail": f"Question {qid} does not belong to section {section_id}"
                        }, status=400)
                    
                    # Create or update student answer
                    sa, created = StudentAnswer.objects.get_or_create(
                        attempt=attempt,
                        question=question,
                        defaults={'section': section}
                    )
                    sa.section = section
                    sa.selected_option_id = selected_option_id
                    sa.essay_answer = essay_answer if essay_answer else None
                    
                    # Auto-grade objective questions
                    if question.question_type == Question.OBJECTIVE:
                        if selected_option_id:
                            try:
                                opt = Option.objects.get(pk=selected_option_id, question=question)
                            except Option.DoesNotExist:
                                return Response({
                                    "detail": f"Option {selected_option_id} is invalid for question {qid}"
                                }, status=400)
                            
                            sa.mark_gained = question.maximum_mark if opt.is_correct else 0
                        else:
                            # No option selected = wrong answer
                            sa.mark_gained = 0
                        
                        sa.graded_at = timezone.now()
                        sa.graded_by = None
                    else:
                        # Theory/OSCE - leave for examiner
                        sa.mark_gained = None
                        sa.graded_at = None
                        sa.graded_by = None
                    
                    sa.save()
                
                # Calculate scores for ALL sections
                for section in all_sections:
                    section_total = StudentAnswer.objects.filter(
                        attempt=attempt,
                        section=section,
                        mark_gained__isnull=False
                    ).aggregate(total=Sum('mark_gained'))['total'] or 0
                    
                    SectionScore.objects.update_or_create(
                        attempt=attempt,
                        section=section,
                        defaults={'score': section_total}
                    )
                
                # Calculate total score
                total = StudentAnswer.objects.filter(
                    attempt=attempt,
                    mark_gained__isnull=False
                ).aggregate(total=Sum('mark_gained'))['total'] or 0
                
                # Update attempt
                attempt.submitted_at = timezone.now()
                attempt.status = "SUBMITTED"
                attempt.total_score = total
                attempt.save()
                
                graded_count = StudentAnswer.objects.filter(
                    attempt=attempt,
                    mark_gained__isnull=False
                ).count()
                
                pending_count = StudentAnswer.objects.filter(
                    attempt=attempt,
                    mark_gained__isnull=True
                ).count()
                
                return Response({
                    "detail": "Exam submitted successfully",
                    "attempt_id": attempt.id,
                    "exam_id": attempt.exam_id,
                    "exam_title": attempt.exam.title,
                    "total_score": float(attempt.total_score),
                    "graded_questions": graded_count,
                    "pending_grading": pending_count
                })
                
        except ExamAttempt.DoesNotExist:
            return Response({"detail": "Attempt not found or already submitted"}, status=404)
        except Exception as e:
            return Response({"detail": f"Submission failed: {str(e)}"}, status=500)

    @extend_schema(
        summary="Get student's exam attempts",
        description="Retrieves all exam attempts for the authenticated student",
        responses={200: ExamAttemptSerializer(many=True)}
    )
    @action(detail=False, methods=["get"], url_path="my-attempts")
    def my_attempts(self, request):
        """Get all attempts for the current student"""
        attempts = ExamAttempt.objects.filter(
            student=request.user
        ).select_related('exam').order_by('-started_at')
        
        serializer = ExamAttemptSerializer(attempts, many=True, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        summary="Get specific attempt details",
        description="Retrieves detailed information about a specific exam attempt",
        responses={
            200: ExamAttemptSerializer,
            404: OpenApiTypes.OBJECT
        }
    )
    @action(detail=True, methods=["get"], url_path="attempt/(?P<attempt_id>[^/.]+)")
    def get_attempt(self, request, pk=None, attempt_id=None):
        """Get details of a specific attempt"""
        try:
            attempt = ExamAttempt.objects.select_related('exam', 'student').prefetch_related(
                'answers__question',
                'answers__selected_option',
                'answers__section',
                'section_scores__section'
            ).get(pk=attempt_id, exam_id=pk, student=request.user)
        except ExamAttempt.DoesNotExist:
            return Response({"detail": "Attempt not found"}, status=404)
        
        serializer = ExamAttemptSerializer(attempt, context={'request': request})
        return Response(serializer.data)


# ---- Examiner endpoints: grade essay / OSCE answers ----
class ExaminerViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated, IsExaminer]

    # changed to a Better approach
    @action(detail=False, methods=["post"], url_path="grade-answer")
    def grade_answer(self, request):
        answer_id = request.data.get("answer_id")
        mark = request.data.get("mark_gained")
        
        if mark is None:
            return Response({"detail": "mark_gained is required"}, status=400)
        
        try:
            sa = StudentAnswer.objects.select_related('attempt', 'section', 'question').get(pk=answer_id)
        except StudentAnswer.DoesNotExist:
            return Response({"detail": "Answer not found"}, status=404)
        
        # Validate mark doesn't exceed maximum
        if float(mark) > float(sa.question.maximum_mark):
            return Response({
                "detail": f"Mark cannot exceed maximum ({sa.question.maximum_mark})"
            }, status=400)
        
        with transaction.atomic():
            sa.mark_gained = mark
            sa.graded_by = request.user
            sa.graded_at = timezone.now()
            sa.save()

            # Recalculate section score
            section_total = StudentAnswer.objects.filter(
                attempt=sa.attempt,
                section=sa.section,
                mark_gained__isnull=False
            ).aggregate(total=Sum('mark_gained'))['total'] or 0
            
            SectionScore.objects.update_or_create(
                attempt=sa.attempt,
                section=sa.section,
                defaults={'score': section_total}
            )

            # Recalculate attempt total
            attempt_total = StudentAnswer.objects.filter(
                attempt=sa.attempt,
                mark_gained__isnull=False
            ).aggregate(total=Sum('mark_gained'))['total'] or 0
            
            sa.attempt.total_score = attempt_total
            
            # Check if all answers are graded
            ungraded_count = StudentAnswer.objects.filter(
                attempt=sa.attempt,
                mark_gained__isnull=True
            ).count()
            
            if ungraded_count == 0:
                sa.attempt.status = "GRADED"
            
            sa.attempt.save()

        return Response({
            "detail": "Graded successfully",
            "answer_id": sa.id,
            "mark_gained": float(sa.mark_gained),
            "section_total": float(section_total),
            "attempt_total": float(sa.attempt.total_score),
            "attempt_status": sa.attempt.status
        })