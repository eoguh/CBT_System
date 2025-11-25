from rest_framework import serializers
from authentication.models import User
from .models import (
    Question, Option, Exam, ExamSection, ExamAttempt, StudentAnswer, SectionScore, OSCEMark
)

class OptionSerializer(serializers.ModelSerializer):
    image_option = serializers.ImageField(
        required=False,
        allow_null=True,
    )
    
    image_option_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Option
        fields = ("id", "question", "text_option", "image_option", "image_option_url", "is_correct")
        read_only_fields = ("id", "image_option_url")
    
    def get_image_option_url(self, obj):
        request = self.context.get('request')
        if obj.image_option and request:
            return request.build_absolute_uri(obj.image_option.url)
        return None


class QuestionSerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True, required=False, read_only=True)
    
    image_question = serializers.ImageField(
        required=False,
        allow_null=True,
    )
    
    image_question_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Question
        fields = (
            "id", "question_type", "text_question", 
            "image_question", "image_question_url",
            "maximum_mark", "options", "created_by"
        )
        read_only_fields = ("id", "created_by", "image_question_url")
    
    def get_image_question_url(self, obj):
        request = self.context.get('request')
        if obj.image_question and request:
            return request.build_absolute_uri(obj.image_question.url)
        return None

    def create(self, validated_data):
        user = self.context["request"].user
        q = Question.objects.create(created_by=user, **validated_data)
        return q
    

class QuestionNestedSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    image_question_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Question
        fields = (
            "id", "question_type", "text_question", 
            "image_question_url", "maximum_mark", "options"
        )
        read_only_fields = fields
    
    def get_options(self, obj):
        # Check if we should hide correct answers
        hide_answers = self.context.get('hide_answers', False)
        
        if obj.question_type != Question.OBJECTIVE:
            return []
        
        options = obj.options.all()
        data = []
        
        for opt in options:
            option_data = {
                'id': opt.id,
                'text_option': opt.text_option,
                'image_option_url': self.get_image_url(opt.image_option)
            }
            
            # Only include is_correct for exam managers/examiners
            if not hide_answers:
                option_data['is_correct'] = opt.is_correct
            
            data.append(option_data)
        
        return data
    
    def get_image_url(self, image_field):
        request = self.context.get('request')
        if image_field and request:
            return request.build_absolute_uri(image_field.url)
        return None
    
    def get_image_question_url(self, obj):
        return self.get_image_url(obj.image_question)
    


class ExamSectionSerializer(serializers.ModelSerializer):
    # For write operations (create/update), accept question IDs
    questions_ids = serializers.PrimaryKeyRelatedField(
        queryset=Question.objects.all(), 
        many=True, 
        required=False,
        allow_empty=True,
        source='questions',
        write_only=True
    )
    
    # For read operations (list/retrieve), return full question objects
    questions = QuestionNestedSerializer(many=True, read_only=True)

    class Meta:
        model = ExamSection
        fields = (
            "id", "exam", "name", "section_type", 
            "time_lapse_seconds", "questions", "questions_ids", "order"
        )
    
    def to_representation(self, instance):
        """
        Customize representation based on context
        """
        representation = super().to_representation(instance)
        
        # Remove questions_ids from response (it's write_only but just to be sure)
        representation.pop('questions_ids', None)
        
        return representation


class ExamSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = (
            "id", "title", "description", "target_level", 
            "created_by", "scheduled_date", "is_published", "sections"
        )
        read_only_fields = ("created_by",)

    def get_sections(self, obj):
        request = self.context.get('request')
        user = request.user if request else None
        
        # Check if user is a student viewing available exams
        hide_answers = user and user.is_student and not user.is_exam_manager
        
        sections = obj.sections.all()
        serializer = ExamSectionSerializer(
            sections, 
            many=True, 
            context={
                'request': request,
                'hide_answers': hide_answers
            }
        )
        return serializer.data

    def create(self, validated_data):
        user = self.context["request"].user
        exam = Exam.objects.create(created_by=user, **validated_data)
        return exam
    

class StudentAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAnswer
        fields = (
            "id", "attempt", "section", "question", 
            "selected_option", "essay_answer", "mark_gained", 
            "graded_by", "graded_at"
        )
        read_only_fields = ("graded_by", "graded_at", "mark_gained")


class ExamAttemptSerializer(serializers.ModelSerializer):
    answers = StudentAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = ExamAttempt
        fields = (
            "id", "exam", "student", "started_at", 
            "submitted_at", "status", "total_score", "answers"
        )
        read_only_fields = ("student", "started_at", "submitted_at", "status", "total_score")



class SubmitAnswerSerializer(serializers.Serializer):
    """Serializer for individual answer submission"""
    section = serializers.IntegerField(
        required=True,
        help_text="Section ID that contains this question"
    )
    question = serializers.IntegerField(
        required=True,
        help_text="Question ID being answered"
    )
    selected_option = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Option ID for objective questions (required for MCQ)"
    )
    essay_answer = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Text answer for theory/essay questions"
    )


class ExamSubmissionSerializer(serializers.Serializer):
    """Serializer for exam submission request"""
    attempt_id = serializers.IntegerField(
        required=True,
        help_text="The ID of the exam attempt being submitted"
    )
    answers = SubmitAnswerSerializer(
        many=True,
        required=True,
        help_text="List of all answers for the exam"
    )

    def validate_answers(self, value):
        """Ensure answers list is not empty"""
        if not value:
            raise serializers.ValidationError("At least one answer is required")
        return value


class ExamSubmissionResponseSerializer(serializers.Serializer):
    """Serializer for exam submission response"""
    detail = serializers.CharField()
    attempt_id = serializers.IntegerField()
    exam_id = serializers.IntegerField()
    exam_title = serializers.CharField()
    total_score = serializers.DecimalField(max_digits=8, decimal_places=2)
    graded_questions = serializers.IntegerField()
    pending_grading = serializers.IntegerField()


class OptionCreateSerializer(serializers.ModelSerializer):
    """Writable serializer for creating options"""
    image_option = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Option
        fields = ("text_option", "image_option", "is_correct")


class QuestionCreateSerializer(serializers.ModelSerializer):
    """Writable serializer for creating questions with options"""
    options = OptionCreateSerializer(many=True, required=False)
    image_question = serializers.ImageField(required=False, allow_null=True)
    
    class Meta:
        model = Question
        fields = ("question_type", "text_question", "image_question", "maximum_mark", "options")
    
    def validate(self, data):
        """
        Validate the entire question object including options
        """
        question_type = data.get('question_type')
        options = data.get('options', [])
        
        if question_type == Question.OBJECTIVE:
            if not options:
                raise serializers.ValidationError({
                    "options": "Objective questions must have at least 2 options"
                })
            if len(options) < 2:
                raise serializers.ValidationError({
                    "options": "Objective questions must have at least 2 options"
                })
            
            # Check that exactly one option is marked as correct
            correct_count = sum(1 for opt in options if opt.get('is_correct', False))
            if correct_count == 0:
                raise serializers.ValidationError({
                    "options": "At least one option must be marked as correct"
                })
            if correct_count > 1:
                raise serializers.ValidationError({
                    "options": "Only one option can be marked as correct"
                })
        
        return data


class SectionBulkCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a complete section with questions and options"""
    questions = QuestionCreateSerializer(many=True, required=False)
    
    class Meta:
        model = ExamSection
        fields = ("exam", "name", "section_type", "time_lapse_seconds", "order", "questions")
    
    def validate(self, data):
        """Cross-field validation"""
        section_type = data.get('section_type')
        questions = data.get('questions', [])
        
        # Validate that all questions match the section type
        for idx, question in enumerate(questions):
            if question.get('question_type') != section_type:
                raise serializers.ValidationError({
                    'questions': f"Question at index {idx} has type '{question.get('question_type')}' "
                                f"but section type is '{section_type}'. They must match."
                })
        
        return data
    
    def create(self, validated_data):
        questions_data = validated_data.pop('questions', [])
        
        # Get the user from context
        user = self.context['request'].user
        
        # Create the section
        section = ExamSection.objects.create(**validated_data)
        
        # Create questions and their options
        for question_data in questions_data:
            options_data = question_data.pop('options', [])
            
            # Create question
            question = Question.objects.create(
                created_by=user,
                **question_data
            )
            
            # Create options for the question
            for option_data in options_data:
                Option.objects.create(
                    question=question,
                    **option_data
                )
            
            # Add question to section
            section.questions.add(question)
        
        return section


class SectionBulkUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating a section with new questions and options"""
    questions = QuestionCreateSerializer(many=True, required=False)
    
    class Meta:
        model = ExamSection
        fields = ("name", "section_type", "time_lapse_seconds", "order", "questions")
    
    def validate(self, data):
        """Cross-field validation"""
        section_type = data.get('section_type')
        questions = data.get('questions', [])
        
        # Validate that all questions match the section type
        for idx, question in enumerate(questions):
            if question.get('question_type') != section_type:
                raise serializers.ValidationError({
                    'questions': f"Question at index {idx} has type '{question.get('question_type')}' "
                                f"but section type is '{section_type}'. They must match."
                })
        
        return data
    
    def update(self, instance, validated_data):
        """Update section and replace all questions"""
        questions_data = validated_data.pop('questions', [])
        user = self.context['request'].user
        
        # Update section fields
        instance.name = validated_data.get('name', instance.name)
        instance.section_type = validated_data.get('section_type', instance.section_type)
        instance.time_lapse_seconds = validated_data.get('time_lapse_seconds', instance.time_lapse_seconds)
        instance.order = validated_data.get('order', instance.order)
        instance.save()
        
        # Clear existing questions
        instance.questions.clear()
        
        # Create new questions and their options
        for question_data in questions_data:
            options_data = question_data.pop('options', [])
            
            # Create question
            question = Question.objects.create(
                created_by=user,
                **question_data
            )
            
            # Create options for the question
            for option_data in options_data:
                Option.objects.create(
                    question=question,
                    **option_data
                )
            
            # Add question to section
            instance.questions.add(question)
        
        return instance