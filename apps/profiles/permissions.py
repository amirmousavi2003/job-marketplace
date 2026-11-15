from rest_framework.permissions import BasePermission


class IsJobSeeker(BasePermission):
    message = "A job seeker profile is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "job_seeker_profile"))


class IsEmployer(BasePermission):
    message = "An employer profile is required."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "employer_profile"))
