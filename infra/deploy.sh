#!/usr/bin/env bash
# Provisions and deploys everything Lapse needs to run with nobody watching:
# two DynamoDB tables, the evidence bucket, a least-privilege execution role,
# the packaged lapse-run Lambda, and the daily EventBridge schedule that fires
# it. Safe to run twice. Every step either creates the resource or updates the
# one already there, and nothing here prints a secret.
#
# Bedrock and AgentCore are blocked on this account (AWS India / AISPL), so the
# model call goes to Anthropic directly with a key read from .env at deploy
# time. Lambda Function URLs return 403 on this account, so there is no URL
# here: anything that wants a run invokes the function through the SDK.
set -euo pipefail

export AWS_PROFILE=palimpsest
export AWS_DEFAULT_REGION=us-east-1
unset AWS_BEARER_TOKEN_BEDROCK || true

REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
FUNCTION_NAME=lapse-run
ROLE_NAME=lapse-exec
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
SCHEDULER_ROLE_NAME=lapse-scheduler
SCHEDULER_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${SCHEDULER_ROLE_NAME}"
TABLE_CASES=lapse-cases
TABLE_PERMITS=lapse-permits
BUCKET="lapse-evidence-${ACCOUNT_ID}"
SCHEDULE_NAME=lapse-daily
CONTRACTOR="${LAPSE_CONTRACTOR:-VARSITY PLBG AND HTG INC}"
SENDER="${LAPSE_SENDER:-lapse@getava.xyz}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INFRA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${INFRA_DIR}/build"
ZIP_PATH="${INFRA_DIR}/build.zip"

echo "== account ${ACCOUNT_ID} region ${REGION} =="

echo "== dynamodb tables =="
# lapse-cases holds one row per decision Lapse has made, plus one run summary
# row per pass (docs/RECORD.md is the shape contract).
if ! aws dynamodb describe-table --table-name "${TABLE_CASES}" >/dev/null 2>&1; then
  aws dynamodb create-table \
    --table-name "${TABLE_CASES}" \
    --attribute-definitions AttributeName=contractor,AttributeType=S AttributeName=case_id,AttributeType=S \
    --key-schema AttributeName=contractor,KeyType=HASH AttributeName=case_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST >/dev/null
fi
# lapse-permits holds the last seen state of every permit and violation, keyed
# by item_key, so a pass can tell what changed since yesterday instead of
# re-alarming on everything it can see.
if ! aws dynamodb describe-table --table-name "${TABLE_PERMITS}" >/dev/null 2>&1; then
  aws dynamodb create-table \
    --table-name "${TABLE_PERMITS}" \
    --attribute-definitions AttributeName=contractor,AttributeType=S AttributeName=item_key,AttributeType=S \
    --key-schema AttributeName=contractor,KeyType=HASH AttributeName=item_key,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST >/dev/null
fi
aws dynamodb wait table-exists --table-name "${TABLE_CASES}"
aws dynamodb wait table-exists --table-name "${TABLE_PERMITS}"
echo "${TABLE_CASES}: $(aws dynamodb describe-table --table-name "${TABLE_CASES}" --query 'Table.TableStatus' --output text)"
echo "${TABLE_PERMITS}: $(aws dynamodb describe-table --table-name "${TABLE_PERMITS}" --query 'Table.TableStatus' --output text)"

echo "== evidence bucket ${BUCKET} =="
# us-east-1 is the one region where CreateBucket takes no location constraint.
if ! aws s3api head-bucket --bucket "${BUCKET}" >/dev/null 2>&1; then
  aws s3api create-bucket --bucket "${BUCKET}" >/dev/null
fi
aws s3api put-public-access-block --bucket "${BUCKET}" --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true' >/dev/null

echo "== execution role ${ROLE_NAME} =="
# pullback-exec is not reused: its inline policies name pullback-cases,
# pullback-recalls and pullback-evidence-* by ARN, so it grants Lapse nothing.
if ! aws iam get-role --role-name "${ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role --role-name "${ROLE_NAME}" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }
    ]
  }' >/dev/null
  echo "waiting for new IAM role to propagate..."
  sleep 10
fi
aws iam attach-role-policy --role-name "${ROLE_NAME}" \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name lapse-dynamodb --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LapseTables",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
        "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
        "dynamodb:BatchWriteItem", "dynamodb:BatchGetItem", "dynamodb:DescribeTable"
      ],
      "Resource": [
        "arn:aws:dynamodb:'"${REGION}"':'"${ACCOUNT_ID}"':table/'"${TABLE_CASES}"'",
        "arn:aws:dynamodb:'"${REGION}"':'"${ACCOUNT_ID}"':table/'"${TABLE_PERMITS}"'"
      ]
    }
  ]
}'

aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name lapse-s3-evidence --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LapseEvidenceList",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::'"${BUCKET}"'"
    },
    {
      "Sid": "LapseEvidenceObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::'"${BUCKET}"'/*"
    }
  ]
}'

# ses:SendEmail has no per-recipient resource to scope to; identity/* is the
# tightest ARN pattern SES accepts, and it still means "send as an identity
# this account owns" rather than "any SES action anywhere". The three read
# calls are how a run decides whether it may deliver: an unverified recipient
# on a sandboxed account has to be held, not silently dropped.
aws iam put-role-policy --role-name "${ROLE_NAME}" --policy-name lapse-ses --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "LapseSendAsIdentity",
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "arn:aws:ses:'"${REGION}"':'"${ACCOUNT_ID}"':identity/*"
    },
    {
      "Sid": "LapseReadSendingState",
      "Effect": "Allow",
      "Action": ["ses:GetAccount", "ses:GetEmailIdentity", "ses:ListEmailIdentities"],
      "Resource": "*"
    }
  ]
}'

echo "== scheduler invoke role ${SCHEDULER_ROLE_NAME} =="
if ! aws iam get-role --role-name "${SCHEDULER_ROLE_NAME}" >/dev/null 2>&1; then
  aws iam create-role --role-name "${SCHEDULER_ROLE_NAME}" --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": {"Service": "scheduler.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }
    ]
  }' >/dev/null
  echo "waiting for new IAM role to propagate..."
  sleep 10
fi
aws iam put-role-policy --role-name "${SCHEDULER_ROLE_NAME}" --policy-name lapse-invoke-lambda --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeLapseRun",
      "Effect": "Allow",
      "Action": "lambda:InvokeFunction",
      "Resource": "arn:aws:lambda:'"${REGION}"':'"${ACCOUNT_ID}"':function:'"${FUNCTION_NAME}"'"
    }
  ]
}'

echo "== packaging lambda =="
rm -rf "${BUILD_DIR}" "${ZIP_PATH}"
mkdir -p "${BUILD_DIR}"
# boto3 already ships in the python3.12 runtime. Everything the unattended pass
# needs beyond it has to be vendored, strands and anthropic included: the
# scheduled run is the same agent a person runs locally, so the reading of
# DOB's free text happens on the schedule too, not only when someone watches.
# Built on macOS arm64, run on Amazon Linux x86_64. pydantic-core and friends
# carry compiled extensions, so without these platform pins the function dies
# at import on "No module named pydantic_core._pydantic_core". dist-info stays
# in the zip: anthropic resolves its own dependency versions through
# importlib.metadata, and stripping metadata trades a few MB for a
# PackageNotFoundError at import.
PIP="${REPO_ROOT}/.venv/bin/pip"
[ -x "${PIP}" ] || PIP="$(command -v pip3)"
"${PIP}" install --target "${BUILD_DIR}" \
  --platform manylinux2014_x86_64 --implementation cp --python-version 3.12 \
  --only-binary=:all: --upgrade \
  httpx strands-agents anthropic --quiet --disable-pip-version-check
find "${BUILD_DIR}" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
cp -R "${REPO_ROOT}/agent" "${BUILD_DIR}/agent"
find "${BUILD_DIR}/agent" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
cp "${REPO_ROOT}/infra/lambda_handler.py" "${BUILD_DIR}/lambda_handler.py"
# data/rulebook.json is what agent.engine.rulebook reads to turn a permit type
# or a violation type into the filing that cures it, and decide_permit calls it
# on every live permit, so a zip without it is a function that raises on its
# first item. The captured Socrata responses alongside it are what
# agent.engine.portfolio reads when a run is told to work offline.
if [ ! -f "${REPO_ROOT}/data/rulebook.json" ]; then
  echo "data/rulebook.json is missing; the deadline engine cannot run without it" >&2
  exit 1
fi
mkdir -p "${BUILD_DIR}/data"
cp "${REPO_ROOT}"/data/*.json "${BUILD_DIR}/data/"
( cd "${BUILD_DIR}" && zip -r -q "${ZIP_PATH}" . -x '*.pyc' )
ZIP_BYTES=$(wc -c < "${ZIP_PATH}" | tr -d ' ')
echo "package: ${ZIP_PATH} ($(du -h "${ZIP_PATH}" | cut -f1))"
# Lambda rejects a direct zip upload over 50MB and unpacked code over 250MB.
if [ "${ZIP_BYTES}" -gt 52428800 ]; then
  echo "zip is ${ZIP_BYTES} bytes, past the 50MB direct upload ceiling" >&2
  exit 1
fi

# The Anthropic key is read out of the .env the user placed, written to a
# private temp file, handed to Lambda as a file:// argument, and deleted. It is
# never echoed, never in the process list, never in the repo.
ENV_FILE="$(mktemp -t lapse-env)"
trap 'rm -f "${ENV_FILE}"' EXIT
chmod 600 "${ENV_FILE}"
ANTHROPIC_KEY=""
if [ -f "${REPO_ROOT}/.env" ]; then
  ANTHROPIC_KEY="$(grep -m1 '^ANTHROPIC_API_KEY=' "${REPO_ROOT}/.env" | cut -d= -f2- | tr -d '"'"'"'\r' || true)"
fi
if [ -z "${ANTHROPIC_KEY}" ]; then
  echo "no ANTHROPIC_API_KEY in ${REPO_ROOT}/.env; place it there and re-run" >&2
  exit 1
fi
# The table names live in agent/store.py as constants and the bucket name is
# built in infra/lambda_handler.py:_write_evidence, so they are deliberately not
# repeated here as environment variables: two places to change one name is how
# they drift apart.
ANTHROPIC_KEY="${ANTHROPIC_KEY}" CONTRACTOR="${CONTRACTOR}" SENDER="${SENDER}" \
  python3 -c '
import json, os
print(json.dumps({"Variables": {
    "LAPSE_CONTRACTOR": os.environ["CONTRACTOR"],
    "LAPSE_SENDER": os.environ["SENDER"],
    "ANTHROPIC_API_KEY": os.environ["ANTHROPIC_KEY"],
}}))' > "${ENV_FILE}"

echo "== deploying function ${FUNCTION_NAME} =="
if aws lambda get-function --function-name "${FUNCTION_NAME}" >/dev/null 2>&1; then
  aws lambda update-function-code --function-name "${FUNCTION_NAME}" --zip-file "fileb://${ZIP_PATH}" >/dev/null
  aws lambda wait function-updated --function-name "${FUNCTION_NAME}"
  aws lambda update-function-configuration \
    --function-name "${FUNCTION_NAME}" \
    --role "${ROLE_ARN}" \
    --runtime python3.12 \
    --handler lambda_handler.handler \
    --timeout 900 \
    --memory-size 512 \
    --environment "file://${ENV_FILE}" >/dev/null
  aws lambda wait function-updated --function-name "${FUNCTION_NAME}"
else
  aws lambda create-function \
    --function-name "${FUNCTION_NAME}" \
    --runtime python3.12 \
    --role "${ROLE_ARN}" \
    --handler lambda_handler.handler \
    --timeout 900 \
    --memory-size 512 \
    --environment "file://${ENV_FILE}" \
    --zip-file "fileb://${ZIP_PATH}" >/dev/null
  aws lambda wait function-active --function-name "${FUNCTION_NAME}"
fi
rm -f "${ENV_FILE}"

echo "== schedule ${SCHEDULE_NAME} =="
LAMBDA_ARN=$(aws lambda get-function --function-name "${FUNCTION_NAME}" --query 'Configuration.FunctionArn' --output text)
# The daily payload. `limit` is the one number here that is a real constraint
# rather than a preference: the deadline engine hands roughly 200 actionable
# items to the model on this portfolio, each item is its own agent turn, and
# 900 seconds is the Lambda ceiling. agent.run.triage sorts worst first, FILE
# before DECIDE and then by days remaining, so a capped pass takes the most
# urgent items rather than an arbitrary slice, and tomorrow's pass sees what is
# left plus whatever moved overnight. Raise it only after timing a real run.
SCHEDULE_INPUT='{"source":"lapse-daily","live":true,"with_model":true,"limit":25}'
# Scheduler's default retry policy is 185 attempts over 24 hours, which for a
# pass that fetches a live feed and spends model tokens means a bad morning at
# NYC Open Data turns into 185 paid runs. Two attempts inside an hour, then the
# next day's schedule is the retry.
SCHEDULE_TARGET=$(LAMBDA_ARN="${LAMBDA_ARN}" SCHEDULER_ROLE_ARN="${SCHEDULER_ROLE_ARN}" \
  SCHEDULE_INPUT="${SCHEDULE_INPUT}" python3 -c '
import json, os
print(json.dumps({
    "Arn": os.environ["LAMBDA_ARN"],
    "RoleArn": os.environ["SCHEDULER_ROLE_ARN"],
    "Input": os.environ["SCHEDULE_INPUT"],
    "RetryPolicy": {"MaximumRetryAttempts": 2, "MaximumEventAgeInSeconds": 3600},
}))')
# 11:00 UTC is 07:00 in New York, which is when a contractor reads mail and
# before a DOB counter opens, so a filing drafted overnight can still be sent
# the same morning.
if aws scheduler get-schedule --name "${SCHEDULE_NAME}" >/dev/null 2>&1; then
  aws scheduler update-schedule \
    --name "${SCHEDULE_NAME}" \
    --schedule-expression "cron(0 11 * * ? *)" \
    --schedule-expression-timezone UTC \
    --state ENABLED \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target "${SCHEDULE_TARGET}" >/dev/null
else
  aws scheduler create-schedule \
    --name "${SCHEDULE_NAME}" \
    --schedule-expression "cron(0 11 * * ? *)" \
    --schedule-expression-timezone UTC \
    --state ENABLED \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target "${SCHEDULE_TARGET}" >/dev/null
fi

echo ""
echo "function: $(aws lambda get-function --function-name "${FUNCTION_NAME}" --query 'Configuration.[Runtime,MemorySize,Timeout,Handler]' --output text)"
echo "schedule: $(aws scheduler get-schedule --name "${SCHEDULE_NAME}" --query '[State,ScheduleExpression]' --output text)"
echo "invoke it: aws lambda invoke --function-name ${FUNCTION_NAME} --payload '{}' /tmp/lapse.json"
