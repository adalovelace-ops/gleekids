import logging

from django.conf import settings
from django.http import HttpResponseForbidden

logger = logging.getLogger(__name__)


def csrf_failure(request, reason=''):
    origin = request.META.get('HTTP_ORIGIN', '')
    referer = request.META.get('HTTP_REFERER', '')
    host = request.META.get('HTTP_HOST', '')
    forwarded_proto = request.META.get('HTTP_X_FORWARDED_PROTO', '')

    logger.warning(
        'CSRF failure: reason=%s host=%s origin=%s referer=%s forwarded_proto=%s trusted_origins=%s',
        reason,
        host,
        origin,
        referer,
        forwarded_proto,
        settings.CSRF_TRUSTED_ORIGINS,
    )

    return HttpResponseForbidden(
        '<h1>Forbidden (403)</h1>'
        '<p>CSRF verification failed.</p>'
        f'<p><strong>Reason:</strong> {reason}</p>'
        '<p>Please refresh the page and try again. If this continues, check the Render logs for the CSRF failure line.</p>'
    )
