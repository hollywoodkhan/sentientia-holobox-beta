# Sentientia AI Learning Advisor

A shareable Sentientia prototype featuring a Three.js-enhanced male AI learning
advisor, microphone input, browser speech, a FastAPI/Gemini backend on Google
Cloud Run, and a static frontend on Firebase Hosting.

The backend includes a lightweight in-container retrieval layer that ranks verified
knowledge passages for each question and returns source labels without requiring a
managed vector database.

Live demo: https://sentientia-holobox-beta.web.app/

## Project structure

```text
backend/
  main.py
  retrieval.py
  event_knowledge.json
  requirements.txt
  Dockerfile
frontend/
  assets/
  index.html
  admin.html
  config.js
firebase.json
```

## Upload avatar knowledge

The deployed administrator page is:

```text
https://sentientia-holobox-beta.web.app/admin.html
```

Sign in with the approved Google account (`projects@sentientia.com`). The
browser sends a short-lived Firebase ID token to the backend, where Firebase
Admin verifies the token, verified email address, and administrator allowlist.

It accepts text-based PDF, TXT, and Markdown files up to 10 MB. Originals and
extracted passage indexes are stored privately in the bucket configured by
`KNOWLEDGE_BUCKET`.

The `ADMIN_API_KEY` Secret Manager value remains an emergency CLI/API fallback;
it is no longer entered into the dashboard. Retrieve it only when emergency
access is needed:

```powershell
gcloud secrets versions access latest `
  --secret=avatar-admin-api-key `
  --project=gen-lang-client-0089371977
```

Do not share the emergency key with public demo users. Scanned/image-only PDFs
must be OCR-processed before upload. Google sign-in must be enabled once in
Firebase Console under **Authentication > Sign-in method > Google**, with an
appropriate project support email.

## White-label clients without redeployment

The same Firebase frontend and Cloud Run backend serve multiple isolated client
demos. Open the admin dashboard, sign in with the administrator account, and use
**Add client**. Branding, persona, TTS preferences, logo, avatar, and knowledge
documents are saved in Cloud Storage under the client's namespace.

```text
tenants/{client-id}/config.json
tenants/{client-id}/assets/
tenants/{client-id}/originals/
tenants/{client-id}/indexes/
```

Each client receives a link in this form:

```text
https://sentientia-holobox-beta.web.app/?client={client-id}
```

Changes saved in the dashboard are available immediately and do not require a
Firebase or Cloud Run deployment. The `sentientia` client remains the default
when the `client` query parameter is omitted. Deleting a non-default client from
the dashboard permanently removes its configuration, uploaded assets, original
documents, and extracted indexes.

## Run locally

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GEMINI_API_KEY="YOUR_KEY"
uvicorn main:app --reload --port 8080
```

Set `API_BASE_URL` in `frontend/config.js` to `http://localhost:8080`, then serve
the repository root with `firebase emulators:start --only hosting` or serve the
`frontend` directory with any static file server.

## Deploy the backend to Cloud Run

Prerequisites: install and authenticate the Google Cloud CLI, create/select a
Google Cloud project, enable billing, and create a Gemini API key in Google AI
Studio.

```powershell
gcloud auth login
gcloud config set project YOUR_GOOGLE_CLOUD_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
cd backend
gcloud run deploy avatar-api --source . --region asia-south1 --allow-unauthenticated --set-env-vars "ALLOWED_ORIGINS=https://YOUR_FIREBASE_PROJECT_ID.web.app"
gcloud run services describe avatar-api --region asia-south1 --format="value(status.url)"
```

For production, prefer Secret Manager rather than shell history for the API key:

```powershell
gcloud services enable secretmanager.googleapis.com
"YOUR_GEMINI_API_KEY" | gcloud secrets create gemini-api-key --data-file=-
gcloud secrets add-iam-policy-binding gemini-api-key --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud run services update avatar-api --region asia-south1 --set-secrets="GEMINI_API_KEY=gemini-api-key:latest"
```

## Deploy the frontend to Firebase Hosting

Copy the Cloud Run URL returned above into `frontend/config.js`, then:

```powershell
npm install --global firebase-tools
firebase login
firebase use --add
firebase init hosting
```

During initialization, select the existing Google/Firebase project, set the public
directory to `frontend`, choose **No** for single-page app rewrites, and do not
overwrite `frontend/index.html`. Then deploy:

```powershell
firebase deploy --only hosting
```

After Firebase gives you the final hosting domain, update Cloud Run's CORS setting
if it differs from the domain used during the first deployment:

```powershell
gcloud run services update avatar-api --region asia-south1 --set-env-vars "ALLOWED_ORIGINS=https://YOUR_FIREBASE_PROJECT_ID.web.app"
```

Do not put `GEMINI_API_KEY` in the frontend; browsers cannot keep secrets.
