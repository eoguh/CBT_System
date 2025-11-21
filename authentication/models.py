from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from rest_framework_simplejwt.tokens import RefreshToken


class UserManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required")
        
        username = username.strip()
        
        # Normalize email if provided
        if 'email' in extra_fields and extra_fields['email']:
            extra_fields['email'] = self.normalize_email(extra_fields['email'])
        
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, password=None, **extra_fields):
        if not password:
            raise ValueError("Password is required")
        
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=255, unique=True, db_index=True, blank=True, null=True)
    username = models.CharField(max_length=255, unique=True, db_index=True)
    first_name = models.CharField(max_length=255)
    middle_name = models.CharField(max_length=255, blank=True)
    last_name = models.CharField(max_length=255)
    
    is_student = models.BooleanField(default=False)
    is_examiner = models.BooleanField(default=False)
    is_exam_manager = models.BooleanField(default=False)
    
    # Levels
    ND1 = "ND1"
    ND2 = "ND2"
    HND1 = "HND1"
    HND2 = "HND2"
    PRE_COUNCIL = "Pre-Council"
    
    LEVEL_CHOICES = [
        (ND1, ND1),
        (ND2, ND2),
        (HND1, HND1),
        (HND2, HND2),
        (PRE_COUNCIL, PRE_COUNCIL),
    ]
    
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []  # Empty - no additional required fields
    
    objects = UserManager()
    
    def __str__(self):
        return self.username
    
    def get_full_name(self):
        parts = [self.first_name]
        if getattr(self, "middle_name", ""):
            parts.append(self.middle_name)
        parts.append(self.last_name)
        return " ".join(filter(None, parts))

    
    def tokens(self):
        refresh = RefreshToken.for_user(self)
        return {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'username': self.username,
                'fullname': f"{self.first_name} {self.middle_name + ' ' if self.middle_name else ''}{self.last_name}".strip()
            }
        }