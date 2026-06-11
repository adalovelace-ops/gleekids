# Render Deployment

Use the `render.yaml` blueprint from the repository root, or create a Render Web Service manually with these settings.

## Manual Web Service Settings

- Root Directory: `backend`
- Runtime: Python
- Build Command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Start Command: `python manage.py migrate && daphne -b 0.0.0.0 -p $PORT core.asgi:application`

## Environment Variables

Set these in Render. Do not commit real values.

- `DEBUG=False`
- `SECRET_KEY`: generate a long random value, or let the blueprint generate it
- `DATABASE_URL`: your Supabase/Postgres connection URL
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`
- `SUPABASE_URL`
- `SUPABASE_KEY`

For uploaded resumes/videos, keep the blueprint disk mounted at `/var/data` and set:

- `MEDIA_ROOT=/var/data`

Render automatically provides `RENDER_EXTERNAL_HOSTNAME`; the Django settings use it for `ALLOWED_HOSTS` and CSRF trusted origins.
