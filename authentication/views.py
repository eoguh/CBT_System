from django.shortcuts import render
from .serializers import UserSerializer, CreateUserByAdminSerializer
from authentication.permissions import IsAdmin, IsExamManager, IsExaminer
from rest_framework.parsers import MultiPartParser, JSONParser, FormParser
import csv, io
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from .models import User
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import LoginSerializer
from rest_framework.generics import GenericAPIView


# ---- Admin create users / bulk upload ----
class AdminUserViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CreateUserByAdminSerializer
    queryset = User.objects.all()
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    @action(detail=False, methods=["post"], url_path="bulk-upload-csv")
    def bulk_upload_csv(self, request):
        """
        Expect CSV with columns: username, first_name, last_name, email, is_student, is_exam_manager, is_examiner, level
        Password will be set to username by default.
        """
        file = request.FILES.get("file")
        if not file:
            return Response({"detail": "CSV file required in 'file' field."}, status=400)

        data = file.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(data))
        created = []
        errors = []
        for i, row in enumerate(reader, start=1):
            try:
                username = row.get("username")
                if not username:
                    raise ValueError("username required")

                user = User(
                    username=username,
                    first_name=row.get("first_name", ""),
                    last_name=row.get("last_name", ""),
                    email=row.get("email", "")
                )
                # roles
                user.is_student = row.get("is_student", "").strip().lower() in ("1", "true", "yes", "y")
                user.is_exam_manager = row.get("is_exam_manager", "").strip().lower() in ("1", "true", "yes", "y")
                user.is_examiner = row.get("is_examiner", "").strip().lower() in ("1", "true", "yes", "y")
                lvl = row.get("level") or None
                if lvl:
                    user.level = lvl
                user.set_password(username)  # password = username
                user.save()
                created.append(user.username)
            except Exception as ex:
                errors.append({"row": i, "error": str(ex)})
        return Response({"created": created, "errors": errors})




class LoginView(GenericAPIView):
    permission_classes = []
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email
            }
        })
