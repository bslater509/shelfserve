from urllib.parse import urlparse

from django.urls import get_script_prefix, set_script_prefix


class IngressPathMiddleware:
    """Teach Django about Home Assistant Ingress subpaths."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        original_prefix = get_script_prefix()
        self._set_external_url_metadata(request)

        ingress_path = request.META.get("HTTP_X_INGRESS_PATH", "").rstrip("/")
        if ingress_path:
            request.META["SCRIPT_NAME"] = ingress_path
            set_script_prefix(f"{ingress_path}/")

        try:
            return self.get_response(request)
        finally:
            set_script_prefix(original_prefix)

    def _set_external_url_metadata(self, request):
        source_url = request.META.get("HTTP_ORIGIN") or request.META.get("HTTP_REFERER")
        if not source_url:
            return

        parsed_url = urlparse(source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            return

        request.META["HTTP_X_FORWARDED_HOST"] = parsed_url.netloc
        request.META["HTTP_X_FORWARDED_PROTO"] = parsed_url.scheme
        request.META["wsgi.url_scheme"] = parsed_url.scheme
