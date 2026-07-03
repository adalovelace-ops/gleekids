from pathlib import Path

from django.core.exceptions import ValidationError


MAX_DOCUMENT_SIZE = 5 * 1024 * 1024
MAX_VIDEO_SIZE = 250 * 1024 * 1024

UPLOAD_RULES = {
    'resume': {
        'extensions': {'.pdf', '.doc', '.docx'},
        'content_types': {
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        },
        'max_size': MAX_DOCUMENT_SIZE,
        'label': 'Resume/CV',
    },
    'tefl_certificate': {
        'extensions': {'.pdf', '.jpg', '.jpeg', '.png'},
        'content_types': {'application/pdf', 'image/jpeg', 'image/png'},
        'max_size': MAX_DOCUMENT_SIZE,
        'label': 'Certificate / TEFL',
    },
    'video': {
        'extensions': {'.mp4', '.mov', '.webm'},
        'content_types': {'video/mp4', 'video/quicktime', 'video/webm'},
        'max_size': MAX_VIDEO_SIZE,
        'label': 'Video Introduction',
    },
    'video_2': {
        'extensions': {'.mp4', '.mov', '.webm'},
        'content_types': {'video/mp4', 'video/quicktime', 'video/webm'},
        'max_size': MAX_VIDEO_SIZE,
        'label': 'Second Video',
    },
}


def validate_applicant_upload(field_name, uploaded_file):
    rule = UPLOAD_RULES.get(field_name)
    if not rule:
        raise ValidationError('Invalid upload field.')
    if not uploaded_file:
        return

    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix not in rule['extensions']:
        allowed = ', '.join(sorted(rule['extensions']))
        raise ValidationError(f"{rule['label']} must use one of these file types: {allowed}.")

    content_type = getattr(uploaded_file, 'content_type', '')
    if content_type and content_type not in rule['content_types']:
        raise ValidationError(f"{rule['label']} has an invalid file content type.")

    if uploaded_file.size > rule['max_size']:
        max_mb = rule['max_size'] // (1024 * 1024)
        raise ValidationError(f"{rule['label']} must be {max_mb} MB or smaller.")
