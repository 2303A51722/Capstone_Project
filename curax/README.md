# CuraX — Smart Healthcare Management System

A fresh Flask + SQLite academic project with four account roles: Patient, Doctor, Diagnostic Center and Insurance Provider.

## Features

- Registration with role selection; login identifies the role automatically.
- Password hashing, Flask sessions and CSRF protection.
- Separate dashboards and role-protected routes.
- Patient medical document uploads, filtering, download and delete.
- Doctor patient lookup by Patient ID, access list and clinical notes.
- Diagnostic test entries with optional report attachments.
- Insurance policy linking, claim submission, supporting documents and claim review.
- Notifications and profile editing.
- SQLite persistence and responsive HTML/CSS/JavaScript UI.

## Requirements

- Python 3.10+
- VS Code (recommended)

## Run on Windows PowerShell

```powershell
cd curax
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set a long random `FLASK_SECRET_KEY`. Then run:

```powershell
py app.py
```

Open http://127.0.0.1:5000

If PowerShell blocks activation, run this for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.venv\Scripts\Activate.ps1
```

## Functional workflow

1. Register a Patient account. Its Patient ID appears on the patient dashboard.
2. Register a Doctor account. Patient ID lookup currently grants access immediately; patient consent must be implemented before real use.
3. Register a Diagnostic Center account and add a test using the same Patient ID.
4. Register an Insurance Provider account. Link a policy to the patient's Patient ID.
5. As the patient, submit a claim using the linked policy and select supporting records.
6. As the insurer, review the claim and set Under Review, Approved or Rejected (rejection requires remarks).

## Important implementation notes

- This is a student/demo prototype, not a production electronic health record or insurance adjudication service.
- The doctor lookup currently grants access immediately for demonstration. Production use must replace this with a patient consent/approval workflow.
- The forgot-password screen is informational only; an email delivery and secure reset-token flow must be configured before real use.
- Contact form submissions are acknowledged in the interface but are not delivered to an email inbox.
- Uploaded files are stored using random server-side names, checked by extension and file signature, and served only through an authorization route.
- SQLite is suitable for a local demo. Production deployment needs a hardened database, HTTPS, backups, audit logging, malware scanning, retention controls and privacy/legal review.
- Do not upload real patient medical information to this demo deployment.


## Standard login (Demo Mode removed)

- Create an account and choose one of four roles during registration.
- Sign in using the shared login page with your username/email and password.
- CuraX automatically redirects to your registered role's dashboard.
- A session retains login until logout or session expiry. There is no demo login or role switcher.
- No demo database or demo identities are created.

## Running on Windows PowerShell

From the `curax` directory, with `.venv` in the parent directory:

```powershell
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # only on first setup
..\.venv\Scripts\python.exe app.py
```

If `.venv` is activated, simply use `python app.py`. Set a strong random `FLASK_SECRET_KEY` in `.env` and set `FLASK_DEBUG=0` before nonlocal deployments.

**Security limitation:** This is a development build, not an audited production healthcare application. Doctor access is still granted by knowing a patient ID, diagnostic/insurance access controls need tightening, and account verification, secure password reset, audit logs, encryption and deployment hardening are incomplete. Do not store real patient data or deploy for professional clinical use until these issues are resolved and independently tested.

## Switch account (no demo mode)

Sign in normally, then click **Switch account** in the top navigation or sidebar. To add a Patient, Doctor, Diagnostic Center, or Insurance Provider account, enter that account's own username/email and password once. You can then switch between these authenticated accounts without repeatedly entering credentials during the same browser session. Logging out clears all linked accounts. A role cannot be changed on an existing account; each role remains a separate account with its own permissions.

**Security:** Do not use account switching to share credentials or access records without authorization. This student project is not production-ready for real healthcare data.
