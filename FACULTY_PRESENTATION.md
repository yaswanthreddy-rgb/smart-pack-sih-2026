# Smart Pack: Faculty Presentation

## 1. Title

**Smart Pack**  
AI-assisted packaged commodity compliance for Legal Metrology

Team: SIH 2026

## 2. Problem

Packaged-product inspections are time-consuming and error-prone when declarations are read manually. Inspectors need a faster way to capture label evidence, identify missing declarations, and route uncertain cases for human review.

## 3. Solution

Smart Pack turns a package-label image into an evidence-backed preliminary assessment:

`Camera/upload -> OCR -> field extraction -> category detection -> configurable checks -> score -> human review -> PDF report`

## 4. Key Features

- Live camera or image upload
- English, Hindi, Tamil, and Telugu OCR options
- OCR text and confidence score
- Extracted manufacturer, address, quantity, MRP, date/expiry, consumer care, country, and calories
- OCR bounding-box evidence image
- Configurable compliance checks
- PASS or LOW CONFIDENCE review status
- Inspection history and PDF report download
- Authenticated inspector access

## 5. Technical Architecture

- React + Vite frontend
- FastAPI backend
- PaddleOCR and OpenCV image preprocessing
- SQLAlchemy with SQLite locally and PostgreSQL for deployment
- Docker multi-stage build
- Render Blueprint for one web service plus PostgreSQL

## 6. Live Demonstration

1. Open the deployed URL.
2. Sign in as the inspector.
3. Open **Scan Product**.
4. Capture or upload a package label.
5. Select the OCR language.
6. Click **Analyze Product**.
7. Show the evidence image and OCR text.
8. Show extracted declarations and the score.
9. Open History and download the PDF report.

## 7. Demonstration Credentials

Username: `inspector`  
Password: `Inspector@123`

## 8. Important Interpretation

The output is an **AI-assisted preliminary compliance assessment**, not a final legal verdict. Missing or uncertain declarations are routed to human verification before enforcement action.

## 9. Deployment

The repository includes `render.yaml` and a Dockerfile. Deployment steps:

1. Push the repository to GitHub.
2. In Render, choose **New > Blueprint**.
3. Select the repository.
4. Approve the web service and PostgreSQL database.
5. Wait for the Docker build to finish.
6. Open the generated Render URL.
7. Verify `/health`, login, and one sample scan.

## 10. Future Improvements

- Versioned legal-rule repository with effective dates
- Durable object storage for images
- Role-based inspector, auditor, and administrator permissions
- Manual-review workflow and audit logs
- Automated test and CI/CD pipeline
- HTTPS camera access for remote devices

## 11. Closing

Smart Pack reduces repetitive label inspection work while preserving the evidence and human review required for responsible Legal Metrology decisions.
