from rest_framework import permissions


class IsAdmin(permissions.IsAdminUser):
    """Admins only (default Django admin staff/superuser behaviour)."""
    pass


class IsExamManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_exam_manager)


class IsExaminer(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_examiner)
