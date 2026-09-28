# GCP Integration Guide – Job Application Tracker

## Architecture
Browser -> **Cloud Run** (Flask in Docker) -> **Cloud Storage** (profile photos)
                                          -> **Secret Manager** (API keys, SMTP password)
**Cloud Scheduler** -> POST /internal/run-reminders (hourly) -> Gmail SMTP reminders
Groq / Gmail APIs stay as external services.

## 0. Before anything: rotate your secrets
Your zip contained a real `.env` (Groq key, Google client secret, Gmail app password).
Revoke and regenerate them, and never commit `.env` (it's in .gitignore + .dockerignore).

## 1. One-time setup
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  storage.googleapis.com cloudscheduler.googleapis.com
```

## 2. Cloud Storage bucket
```bash
export REGION=asia-south1
gsutil mb -l $REGION gs://YOUR_PROJECT_ID-jobtracker-uploads
```

## 3. Secrets
```bash
for s in SECRET_KEY GROQ_API_KEY GOOGLE_CLIENT_SECRET MAIL_PASSWORD CRON_SECRET; do
  printf "value-for-$s" | gcloud secrets create $s --data-file=-
done
# (use real values; generate CRON_SECRET with: openssl rand -hex 24)
PROJECT_NUM=$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')
SA=$PROJECT_NUM-compute@developer.gserviceaccount.com
for s in SECRET_KEY GROQ_API_KEY GOOGLE_CLIENT_SECRET MAIL_PASSWORD CRON_SECRET; do
  gcloud secrets add-iam-policy-binding $s --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
done
gsutil iam ch serviceAccount:$SA:objectAdmin gs://YOUR_PROJECT_ID-jobtracker-uploads
```

## 4. Deploy to Cloud Run
```bash
gcloud run deploy job-tracker --source . --region $REGION --allow-unauthenticated \
  --max-instances 1 \
  --set-env-vars GCS_BUCKET=YOUR_PROJECT_ID-jobtracker-uploads,DEBUG=False,GROQ_MODEL=openai/gpt-oss-120b,GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com,MAIL_USERNAME=you@gmail.com,DATABASE_PATH=/tmp/tracker.db \
  --set-secrets SECRET_KEY=SECRET_KEY:latest,GROQ_API_KEY=GROQ_API_KEY:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest,MAIL_PASSWORD=MAIL_PASSWORD:latest,CRON_SECRET=CRON_SECRET:latest
```
Then add the printed service URL to your Google OAuth client:
- Authorized JavaScript origin: `https://job-tracker-xxxx.run.app`
- Redirect URI: `https://job-tracker-xxxx.run.app/auth/google/gmail/callback`
and set `GOOGLE_REDIRECT_URI` to the same value (`gcloud run services update job-tracker --update-env-vars GOOGLE_REDIRECT_URI=...`).

## 5. Cloud Scheduler (replaces the background thread)
```bash
gcloud scheduler jobs create http job-tracker-reminders \
  --location $REGION --schedule "0 * * * *" --http-method POST \
  --uri https://job-tracker-xxxx.run.app/internal/run-reminders \
  --headers "X-Cron-Secret=YOUR_CRON_SECRET"
```

## 6. IMPORTANT limitation: SQLite on Cloud Run
Cloud Run's disk is temporary, so data in SQLite is lost when an instance restarts.
`DATABASE_PATH=/tmp/tracker.db` is fine for a demo only. For a real deployment move to
**Cloud SQL (PostgreSQL)**: create an instance, add `psycopg2-binary`, and port
`database/db.py` (~490 lines) from sqlite3 to Postgres. Say the word and I'll do that port.

## What changed in the code
- `Dockerfile`, `.dockerignore`, gunicorn added to requirements
- `services/gcp_storage.py` – Cloud Storage helper (no-op when `GCS_BUCKET` unset)
- `routes/profile.py` – avatars are mirrored to / served from GCS
- `routes/cron.py` + `app.py` – Cloud Scheduler endpoint; thread disabled on Cloud Run
