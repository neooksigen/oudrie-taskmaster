# Deployment Guide: Pipeline Runner Web UI on Google Cloud Run

This guide describes how to run and test the Task Pipeline Web UI locally, and how to deploy it to **Google Cloud Run** so that your business and product teams can trigger executions with a single click.

---

## 1. Local Testing and Verification (OPTIONAL, NOT REQUIRED)

Before deploying to the cloud, you can run the FastAPI web application locally to verify the interface and log streaming.

### Step 1: Run the Web Server
Launch the application using Uvicorn:
```bash
uvicorn app:app --host 127.0.0.1 --port 8080
```

### Step 2: Access the UI
Open your web browser and navigate to:
```
http://127.0.0.1:8080/
```

### Step 3: Run the Pipeline
1. You will see the prefilled defaults for the Task List and Archive Google Sheets.
2. Click the **"Run Pipeline"** button.
3. Observe the scrolling **live console logs** at the bottom of the page in real-time as the Python subprocess executes `run_tasks.py`.

---

## 2. Deploying to Google Cloud Run (REQUIRED)

Cloud Run is a fully-managed serverless platform. It automatically builds, registers, and scales your application container.

### Step 1: Set Your GCP Project, in Workbench Terminal
Ensure your active `gcloud` configuration points to your Google Cloud Project:
```bash
gcloud config set project <YOUR_GCP_PROJECT_ID>
```

### Step 2: Deploy from Source, in Workbench Terminal
Run the following single command in the project directory. The `--source` flag instructs GCP to package your code, build it into a container image using **Cloud Build**, register it in **Artifact Registry**, and deploy it as a serverless service:

```bash
gcloud run deploy task-pipeline-web \
    --source . \
    --region us-central1 \
    --timeout=30m \
    --allow-unauthenticated
```

alternatively 
```bash
gcloud run deploy task-pipeline-web \
      --source . \
      --region us-central1 \
      --timeout=30m \
      --no-cpu-throttling \
      --min-instances=1 \
      --allow-unauthenticated
```

*Note: If prompted to enable the Artifact Registry API, Cloud Build API, or Cloud Run API, type `y` (Yes) to proceed.*

Then run this in Cloud Run's Cloud Shell : 
```bash
gcloud beta run services add-iam-policy-binding --region=us-central1 --member=allUsers --role=roles/run.invoker task-pipeline-web
```
To allow all user run the web app. Then in the Cloud Run's Security Page, ensure Authentication = Allow Public Access, then ok/save.

### Step 3: Access Your Web App
Once the command finishes, Cloud Run will output a public service URL:
```
Service [task-pipeline-web] revision [task-pipeline-web-00001] has been deployed and is serving 100% of traffic.
Service URL: https://task-pipeline-web-xxxxxxx-uc.a.run.app
```
You can share this URL directly with your business/product teams so they can run pipelines from their browsers!

---

## 3. Production Security & IAM Best Practices

While the `Dockerfile` automatically copies `kzxy_credentials.json` for easy setup, hardcoding credential files inside container images is **not recommended for production**.

### Recommended Production Setup (No Credentials File):
1. **Create a Custom Service Account** or use the default Cloud Run runtime service account (`[PROJECT_NUMBER]-compute@developer.gserviceaccount.com`).
2. **Grant IAM Permissions:** Give this service account the **BigQuery Admin** role (or the specific roles required by your BigQuery tools).
3. **Share Google Sheets:** Share your Task List and Archive Google Sheets with the service account's email address (granting them **Editor** access).
4. **Deploy with Service Account:** Tell Cloud Run to run using this service account:
   ```bash
   gcloud run deploy task-pipeline-web \
       --source . \
       --service-account <SERVICE_ACCOUNT_EMAIL> \
       --region us-central1 \
       --allow-unauthenticated
   ```
5. **No File Required:** Google's client libraries (`gspread` and `google-cloud-bigquery`) will automatically pick up the credentials from the Cloud Run environment.
