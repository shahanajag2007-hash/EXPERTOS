# AWS S3 Setup Guide

This guide explains how to create and configure the S3 bucket that ExpertOS uses for document storage when `STORAGE_BACKEND=s3`.

For local development without AWS, leave `STORAGE_BACKEND=local` (the default) — no AWS account is needed.

## Prerequisites

- An AWS account ([aws.amazon.com](https://aws.amazon.com/))
- AWS CLI installed (optional, for CLI steps) — [Installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- IAM permissions to create S3 buckets and IAM users/roles

## 1. Create the S3 Bucket

Recommended region: **ap-south-1** (Mumbai) — choose the region closest to your users.

### AWS Console

1. Go to **S3** in the AWS Console.
2. Click **Create bucket**.
3. Bucket name: `expertos-uploads-<random-suffix>` (e.g. `expertos-uploads-a1b2c3`). Bucket names are globally unique.
4. Region: **Asia Pacific (Mumbai) ap-south-1**.
5. **Block all public access**: leave all four checkboxes **enabled** (default). ExpertOS never serves files publicly.
6. **Default encryption**: select **Server-side encryption with Amazon S3 managed keys (SSE-S3)**. This is free.
7. **Bucket Versioning**: leave **Disabled** (optional for demos; versioning adds storage cost).
8. Click **Create bucket**.

### AWS CLI (one command)

```bash
aws s3api create-bucket \
  --bucket expertos-uploads-YOURSUFFIX \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1
```

Then enable SSE-S3 encryption:

```bash
aws s3api put-bucket-encryption \
  --bucket expertos-uploads-YOURSUFFIX \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'
```

## 2. IAM Configuration

ExpertOS needs three S3 permissions: `PutObject`, `GetObject`, `DeleteObject`.

### Minimum IAM policy

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "ExpertOSFileStorage",
    "Effect": "Allow",
    "Action": [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject"
    ],
    "Resource": "arn:aws:s3:::YOUR-BUCKET-NAME/*"
  }]
}
```

Replace `YOUR-BUCKET-NAME` with your actual bucket name.

### For local development: IAM user with programmatic access

1. Go to **IAM → Users → Create user**.
2. Name: `expertos-local-dev` (or similar).
3. **Permissions**: attach the policy above (create a new inline or managed policy).
4. Go to the user → **Security credentials → Create access key** → choose **Local code**.
5. Copy the **Access Key ID** and **Secret Access Key** — they are shown only once.
6. Add them to `backend/.env` (see Environment Configuration below).

### For production (EC2 / Elastic Beanstalk): IAM role

1. Go to **IAM → Roles → Create role**.
2. Trusted entity: **AWS service → EC2** (or the service you deploy on).
3. Attach the same policy above.
4. Attach the role to your EC2 instance or Elastic Beanstalk environment.
5. Leave `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` **empty** in the environment — boto3 automatically reads credentials from the instance metadata service.

**IAM roles are strongly preferred for production** — no long-lived credentials to rotate or accidentally expose.

## 3. Environment Configuration

| Variable | Required | Example | Notes |
|---|---|---|---|
| `STORAGE_BACKEND` | Yes (to use S3) | `s3` | Set to `local` to use local storage (default) |
| `S3_BUCKET_NAME` | Yes (when S3) | `expertos-uploads-a1b2c3` | Exact bucket name |
| `AWS_REGION` | Yes (when S3) | `ap-south-1` | Must match bucket region |
| `AWS_ACCESS_KEY_ID` | Dev only | `AKIAIOSFODNN7EXAMPLE` | Leave empty on EC2/EB (use IAM role) |
| `AWS_SECRET_ACCESS_KEY` | Dev only | `wJalrXUtnFEMI/K7MDENG/...` | Leave empty on EC2/EB (use IAM role) |

## 4. Local Development Configuration

Add to `backend/.env`:

```env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=expertos-uploads-YOURSUFFIX
AWS_REGION=ap-south-1
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

To revert to local storage, set `STORAGE_BACKEND=local` (or remove the line).

## 5. Production Configuration (IAM role)

On EC2 or Elastic Beanstalk with an attached IAM role:

```env
STORAGE_BACKEND=s3
S3_BUCKET_NAME=expertos-uploads-YOURSUFFIX
AWS_REGION=ap-south-1
# AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are intentionally absent
```

boto3 resolves credentials in this order:
1. `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars
2. `~/.aws/credentials` file
3. EC2 instance metadata (IAM role) ← recommended for production

## 6. Verify the Connection

After configuring `backend/.env`, test with a quick Python one-liner (from `backend/`):

```bash
python -c "
import boto3, os
from dotenv import load_dotenv
load_dotenv()
s3 = boto3.client('s3', region_name=os.getenv('AWS_REGION','us-east-1'))
bucket = os.getenv('S3_BUCKET_NAME')
print(s3.head_bucket(Bucket=bucket))
print('S3 connection OK — bucket:', bucket)
"
```

Expected output: `S3 connection OK — bucket: expertos-uploads-YOURSUFFIX`

## 7. Troubleshooting

| Error | Likely cause | Fix |
|---|---|---|
| `AccessDenied` | IAM policy missing or wrong bucket name | Check the policy's `Resource` ARN matches your bucket |
| `NoSuchBucket` | Wrong bucket name or wrong region | Verify `S3_BUCKET_NAME` and `AWS_REGION` match the bucket |
| `NoCredentialsError` | Credentials not configured | Check `AWS_ACCESS_KEY_ID`/`SECRET` in `.env`, or verify IAM role is attached |
| `EndpointResolutionError` | Wrong region | Set `AWS_REGION` to match the bucket's actual region |
| `RuntimeError: STORAGE_BACKEND=s3 requires S3_BUCKET_NAME` | `S3_BUCKET_NAME` empty | Set the bucket name in `.env` |

For upload failures in production: errors are returned to the user as HTTP 500 — ExpertOS never silently falls back to local storage when S3 is configured.
