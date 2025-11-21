from rest_framework import serializers
from authentication.models import User
from django.contrib.auth import authenticate


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "middle_name", "last_name",
                  "is_student", "is_exam_manager", "is_examiner", "level")
        read_only_fields = ("id",)


class CreateUserByAdminSerializer(serializers.ModelSerializer):
    """
    Admin-only serializer to create users. Password defaults to username if not provided.
    """
    class Meta:
        model = User
        fields = ("id", "username", "first_name", "last_name", "email",
                  "is_student", "is_exam_manager", "is_examiner", "level", "password")
        extra_kwargs = {"password": {"write_only": True, "required": False}}

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        username = validated_data.get("username")
        if password is None:
            password = username  # default behaviour requested
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")

        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError("Invalid username or password")
        else:
            raise serializers.ValidationError("Username and password are required")

        attrs["user"] = user
        return attrs
