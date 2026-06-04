from urllib.parse import urlparse

from django.urls import get_script_prefix, set_script_prefix


class IngressPathMiddleware:
    """Teach Django about Home Assistant Ingress subpaths."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        original_prefix = get_script_prefix()
        ingress_path = request.META.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if ingress_path:
            request.META["SCRIPT_NAME"] = ingress_path
            set_script_prefix(f"{ingress_path}/")
            self._set_missing_forwarded_origin(request)

        try:
            return self.get_response(request)
        finally:
            set_script_prefix(original_prefix)

    def _set_missing_forwarded_origin(self, request):
        origin = request.META.get("HTTP_ORIGIN")
        if not origin:
            return

        parsed_origin = urlparse(origin)
        if parsed_origin.scheme not in {"http", "https"} or not parsed_origin.netloc:
            return

        request.META.setdefault("HTTP_X_FORWARDED_HOST", parsed_origin.netloc)
        request.META.setdefault("HTTP_X_FORWARDED_PROTO", parsed_origin.scheme)
