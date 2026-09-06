# India EdTech Data Engineering Pipeline

A backend system for **Tech & Education in India** — it watches for students
who might drop out of school, and answers education-policy questions in
plain language, in the asker's own language, over WhatsApp or an API.

---

## 1. What this is, in plain English

Think of this system as two things bolted together:

**A) An early-warning system for students.**
Every night, it looks at each student's attendance, test scores, and whether
they have internet/a computer at home or at school. From that, it calculates
a "risk score" — a number between 0 and 1 — that estimates how likely that
student is to drop out. A school administrator can then ask the system
"who are my highest-risk students right now?" and get a ranked list, along
with a plain explanation of *why* each student was flagged (e.g. "mostly
because attendance is low and there's no internet at home").

**B) A question-answering assistant for education policy.**
A parent or teacher can ask a question — in English, Hindi, Tamil, or several
other Indian languages — either through a phone app or directly on
**WhatsApp**, e.g. *"What is the government doing about internet access in
village schools?"*. The system searches through official policy documents,
finds the relevant parts, and writes a plain-language answer in the same
language the question was asked in — without making anything up beyond what
the documents actually say.

Everything else in this project — the databases, the cloud setup, the
security — exists to make those two things reliable, fast, and safe to run
with real student data.

---

## 2. How it works, step by step

Imagine a school year going by. Here's what happens, in order:

**Step 1 — Data comes in.**
Each state's education department (or, in this demo, a synthetic
generator standing in for one) provides raw records: which schools exist,
which students attend them, their attendance and test scores. The system
cleans this data with pandas/NumPy, checks it against a strict schema (bad
or malformed records are rejected here, not silently loaded), and computes
a "digital access index" for each student — a simple score for how much
technology access they have.

**Step 2 — Data is stored in two databases, for two different jobs.**
- **PostgreSQL** holds the structured stuff: schools, students, computed
  risk scores. It also holds the "vector embeddings" the AI Q&A feature
  uses to search documents (via the `pgvector` extension) — think of an
  embedding as a document's fingerprint that lets the computer find similar
  meaning, not just matching keywords.
- **MongoDB** holds the messier, free-text stuff: the actual text of policy
  documents, and feedback comments from teachers/parents.

**Step 3 — Every night, a batch job scores every student.**
An automated job (an AKS "CronJob," basically a scheduled task) loads the
trained machine-learning model, scores every student, and saves the results
to Postgres. If any student newly crosses a "high risk" threshold, the
system automatically emails an alert to configured school administrators.
This means the API never has to do the heavy calculation live — it just
reads the pre-computed answer, which is fast.

**Step 4 — People ask questions, two ways.**
- Through the **API** (`/v1/ask`), typically from a mobile/web app.
- Through **WhatsApp** — someone messages the bot's WhatsApp number, and
  the same underlying logic answers them.

  Either way: the system detects what language the question is in,
  translates it to English internally (because the policy documents are
  mostly in English) to search for the best-matching passages, re-ranks
  those passages for relevance, and then asks an AI model to write an
  answer **grounded only in those passages**, in the original language
  the question was asked in.

**Step 5 — Every action is authenticated, logged, and rate-limited.**
Callers identify themselves either with a shared admin API key, or with a
personal login token (JWT) that's tied to one specific state — meaning a
login issued to, say, the Bihar education department can only ever see
Bihar's student data, never another state's. All requests are counted,
timed, and rate-limited so no single caller can overload the system.

**Step 6 — Everything is stored and deployed securely.**
No password, API key, or secret is ever written into the code or checked
into version control. They all live in **Azure Key Vault**, and the
application retrieves them at startup using an Azure identity — not a
password. The whole thing runs in containers on **Azure Kubernetes Service
(AKS)**, described entirely as code (Terraform + Kubernetes YAML) so the
whole environment can be rebuilt from scratch if needed.

---

## 3. Architecture

```
Raw data (UDISE+-style extract)
        │  pandas / numpy cleaning + pandera schema validation
        ▼
┌──────────────────────────┐        ┌──────────────────────┐
│       PostgreSQL          │        │       MongoDB         │
│ schools/students          │        │ policy docs, feedback │
│ + precomputed risk scores │        │ RAG answer feedback   │
│ + pgvector (RAG embeddings)│       └──────────┬────────────┘
└────────┬──────────────────┘                   │
         │                              Azure OpenAI embeddings
   nightly batch scoring job            + translation + generation
   (AKS CronJob) → email alerts                  │
         │                                       │
         └────────────────┬──────────────────────┘
                           ▼
                Sanic service (app.py) — /v1/* API
             JWT (per-state) + API-key auth, rate limiting
                  ↕ Redis (cache + rate limit)
                           │
              ┌────────────┴─────────────┐
              ▼                          ▼
      Web/mobile client            WhatsApp (Meta Cloud API)
                           │
                  containerized (Docker)
                           ▼
                Azure Kubernetes Service (AKS)
     Deployment/CronJob + Service + HPA + Secrets (Key Vault)
```

---

## 4. Everything currently implemented

| Area | What it does | Where |
|---|---|---|
| Ingestion | Cleans raw data, computes features, validates schema with `pandera` before loading | `ingestion/ingest_pipeline.py` |
| Structured storage | Schools/students/risk-scores in Postgres | `db_connectors/postgres_client.py` |
| Unstructured storage | Policy docs, RAG feedback in Mongo | `db_connectors/mongo_client.py` |
| Vector search | RAG embeddings stored/queried via `pgvector` (no per-pod FAISS) | `db_connectors/postgres_client.py`, `genai/rag_pipeline.py` |
| ML model | RandomForest dropout-risk classifier | `ml/dropout_risk_model.py` |
| Explainability | SHAP feature contributions per student | `ml/dropout_risk_model.py::explain_prediction`, `GET /v1/students/<id>/explain` |
| Model versioning | Lightweight local registry (timestamped versions + JSON manifest) | `ml/model_registry.py` |
| Nightly batch scoring | Precomputes every student's score, emails alerts on new high-risk students | `scripts/batch_score.py`, `deployment/batch-score-cronjob.yaml` |
| Multilingual RAG | Detects question language; translates for retrieval, answers in the original language | `genai/language_utils.py`, `genai/rag_pipeline.py` |
| Retrieval quality | Lexical-overlap re-ranking on top of pgvector's cosine search | `genai/rag_pipeline.py::_rerank` |
| RAG feedback loop | Thumbs up/down + comment on any answer | `POST /v1/ask/feedback` |
| WhatsApp bot | Same Q&A, reachable over WhatsApp, with signed-webhook verification | `integrations/whatsapp_client.py`, `/webhook/whatsapp` |
| Per-client auth | Shared admin API key OR per-client JWT, with rotating refresh tokens | `auth/jwt_auth.py`, `POST /v1/auth/token`, `POST /v1/auth/refresh` |
| Request validation | Pydantic models reject malformed requests with a clean 400 instead of a raw error | `schemas.py` |
| Tiered rate limiting | `/v1/ask` and `/v1/auth/*` get their own (tighter) per-minute caps, separate from the default | `app.py::RATE_LIMIT_TIERS` |
| Model version control via API | List registered model versions and roll back the live model without a redeploy | `GET /v1/models/versions`, `POST /v1/models/rollback` |
| Row-level isolation | A JWT scoped to one state can only ever see that state's data | enforced in every `/v1/students`, `/v1/schools`, `/v1/districts`, `/v1/export` route |
| Right-to-deletion | Deletes a student's record + cached score on request | `DELETE /v1/students/<id>` |
| Anonymized export | Research/reporting export with student IDs hashed | `GET /v1/export/anonymized` |
| Aggregated dashboards | School- and district-level risk rollups | `GET /v1/schools/<id>/risk-summary`, `GET /v1/districts/<state>/<district>/risk-summary` |
| Caching + rate limiting | Redis-backed response cache and per-client rate limits | `cache/redis_client.py` |
| Observability | Request metrics (`/metrics`) + OpenTelemetry tracing (console or OTLP export) | `tracing/otel_setup.py` |
| API versioning | All product endpoints under `/v1/`, infra endpoints unversioned | `app.py` |
| Secrets management | All secrets in Azure Key Vault, zero hardcoded credentials, Workload Identity | `terraform/`, `deployment/secret-provider-class.yaml` |
| CI/CD | Lint → test → `terraform plan` → build → deploy, on every PR/merge | `.github/workflows/ci-cd.yml` |
| Cost-aware scaling | Nightly batch job runs on a cheaper Spot node pool | `terraform/spot_node_pool.tf`, `deployment/batch-score-cronjob.yaml` |
| Safer rollouts | Example canary deployment (Argo Rollouts) alongside the default rolling-update Deployment | `deployment/argo-rollout.yaml` |

---

## 5. What is intentionally NOT built here (and why)

Being upfront: a few frequently-suggested features are genuinely separate
systems, not a few functions in this repo, and building throwaway versions
of them would do more harm than good. They're listed here as roadmap items
rather than faked:

- **Admin dashboard** — a real one is a separate frontend app (React/Next.js)
  consuming this API; out of scope for a backend repository.
- **Azure Purview data lineage** — a platform-level integration you turn on
  against your actual Azure resources, not application code.
- **Two-way sync with state SMIS systems** — depends entirely on each
  state's specific existing system and its own integration API, which
  doesn't exist in a generic form to build against.
- **Voice/IVR channel** — a legitimate high-value idea (reaches people
  WhatsApp/apps can't) but a genuinely separate telephony integration
  (Azure Communication Services Call Automation + Speech SDK) that deserves
  its own project rather than a bolt-on.
- **Argo Rollouts canary controller** — the manifest is provided
  (`deployment/argo-rollout.yaml`), but it requires installing the Argo
  Rollouts controller on your cluster first; it's not auto-installed by
  anything in this repo.

## 6. Known simplifications (still functional, just not the fanciest version)

- **Re-ranking** uses lexical keyword overlap, not a cross-encoder ML model
  — this avoids a heavy extra dependency, at some cost to ranking quality.
- **Model registry** is a local JSON manifest + copied files, not a full
  MLflow tracking server — good enough for versioning/rollback, not for
  multi-user experiment comparison.
- **PII protection** is field-level hashing on export, not encryption-at-rest
  for the live database — for that, use Postgres Transparent Data Encryption
  (enabled by default on Azure Database for PostgreSQL) plus Azure Disk
  Encryption on the underlying storage.

---

## 7. Setup

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest/flake8/black

# .env — see terraform/terraform.tfvars.example for the full list of values
PG_HOST=localhost
PG_PASSWORD=postgres
MONGO_URI=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379/0
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<key>
API_KEY=<shared-admin-api-key>
AZURE_LANGUAGE_ENDPOINT=https://<resource>.cognitiveservices.azure.com/
AZURE_LANGUAGE_KEY=<key>
WHATSAPP_VERIFY_TOKEN=<any string, set in the Meta App dashboard too>
WHATSAPP_ACCESS_TOKEN=<meta system-user token>
WHATSAPP_PHONE_NUMBER_ID=<from the Meta App dashboard>
WHATSAPP_APP_SECRET=<meta app secret, for webhook signature verification>
JWT_SECRET=<random long string>
REFRESH_TOKEN_EXPIRY_DAYS=30
CLIENT_CREDENTIALS_JSON={"bihar-dept": {"secret": "change-me", "state": "Bihar"}}
SMTP_HOST=smtp.example.com
SMTP_USER=alerts@example.org
SMTP_PASSWORD=<password>
ALERT_FROM_EMAIL=alerts@example.org
ALERT_TO_EMAILS=admin1@example.org,admin2@example.org
HIGH_RISK_THRESHOLD=0.7
OTEL_ENABLED=false

python main.py          # bootstrap: ingest -> train -> index (pgvector)
python scripts/batch_score.py   # precompute risk scores once, for local testing
sanic app:app --host=0.0.0.0 --port=8000 --workers=2 --dev
```

Run tests locally: `pytest tests/ -v`

### Getting a scoped login token (and refreshing it)

```bash
curl -X POST http://localhost:8000/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "bihar-dept", "client_secret": "change-me"}'
# -> {"access_token": "...", "refresh_token": "...", "state_scope": "Bihar", ...}

curl http://localhost:8000/v1/students/at-risk \
  -H "Authorization: Bearer <access_token>"
# only ever returns Bihar's students

# When the access token expires (default 60 min), exchange the refresh
# token for a new pair instead of sending client_secret again:
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
# -> a new access_token AND a new refresh_token (the old refresh token is now revoked)
```

Or use the shared admin key for unrestricted access:
```bash
curl http://localhost:8000/v1/students/at-risk -H "X-API-Key: <API_KEY>"
```

---

## 8. Deploying to AKS

```bash
az acr build --registry <acr-name> --image edtech-india-api:latest -f deployment/Dockerfile .
kubectl apply -f deployment/secret-provider-class.yaml
kubectl apply -f deployment/aks-deployment.yaml
kubectl apply -f deployment/batch-score-cronjob.yaml
```

On your managed Postgres (Azure Database for PostgreSQL Flexible Server),
enable pgvector first:
```bash
az postgres flexible-server parameter set --name azure.extensions --value VECTOR ...
```

## 9. Secrets management (Terraform + Azure Key Vault)

Every secret above is provisioned into Azure Key Vault by Terraform, never
hardcoded. Pods read them at runtime via Workload Identity + the Secrets
Store CSI driver — no password is ever stored in the cluster.

```bash
cd terraform
terraform init -backend-config=backend.hcl
terraform plan  -var-file=terraform.tfvars   # or rely on TF_VAR_* env vars
terraform apply -var-file=terraform.tfvars

terraform output -raw workload_identity_client_id
terraform output -raw key_vault_name
terraform output -raw workload_identity_tenant_id
```

Feed those three output values into `deployment/secret-provider-class.yaml`.
`terraform.tfvars`, `backend.hcl`, and `.tfstate` are all gitignored.

## 10. CI/CD (`.github/workflows/ci-cd.yml`)

| Stage | Trigger | What it does |
|---|---|---|
| Lint + test | every PR | `flake8`, `black --check`, `pytest tests/` |
| Terraform plan | every PR (after lint passes) | `terraform fmt -check`, `validate`, `plan` |
| Build + deploy | push to `main` | `terraform apply` → `az acr build` → `kubectl apply` + rollout |

Requires an Azure AD app registration with a federated credential trusting
GitHub's OIDC issuer (separate from the AKS Workload Identity federation in
`terraform/workload_identity.tf`). Repository variables: `ACR_NAME`,
`RESOURCE_GROUP`, `AKS_CLUSTER_NAME`. Repository secrets: `AZURE_CLIENT_ID`,
`AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `TFSTATE_RG`, `TFSTATE_SA`, plus
one secret per `TF_VAR_*` referenced in the workflow file.

---

## 11. API reference (quick summary)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | liveness/readiness |
| GET | `/metrics` | none | request/error counts, cache hits |
| POST | `/v1/auth/token` | none (IP rate-limited) | exchange client credentials for an access + refresh token pair |
| POST | `/v1/auth/refresh` | none (IP rate-limited) | exchange a refresh token for a new access + refresh pair (old refresh token is revoked) |
| GET | `/v1/models/versions` | API key or JWT | list registered model versions with metrics |
| POST | `/v1/models/rollback` | API key only | promote a previous model version back to live, without a redeploy |
| GET | `/v1/students/at-risk` | API key or JWT | ranked dropout-risk list (state-filtered for JWT) |
| GET | `/v1/students/<id>/explain` | API key or JWT | SHAP explanation for one student's score |
| DELETE | `/v1/students/<id>` | API key or JWT | right-to-deletion |
| GET | `/v1/schools/<id>/risk-summary` | API key or JWT | school-level rollup |
| GET | `/v1/districts/<state>/<district>/risk-summary` | API key or JWT | district-level rollup |
| GET | `/v1/export/anonymized` | API key or JWT | research export, IDs hashed |
| POST | `/v1/ask` | API key or JWT | multilingual RAG Q&A |
| POST | `/v1/ask/feedback` | API key or JWT | thumbs up/down on an answer |
| WS | `/v1/ask/stream` | API key or JWT | streamed RAG answer |
| GET/POST | `/webhook/whatsapp` | Meta signature | WhatsApp bot |

---

## 12. Notes / production hardening

- Sample data in `ingestion/ingest_pipeline.py` is synthetic; swap in a real
  UDISE+/state extract via `pd.read_csv` or Azure Blob Storage.
- For production Mongo, use **Azure Cosmos DB for MongoDB API**.
- For production Postgres, use **Azure Database for PostgreSQL Flexible
  Server** with the `VECTOR` extension and Transparent Data Encryption on.
- For production Redis, use **Azure Cache for Redis**.
- Rotate the shared `API_KEY` and `JWT_SECRET` regularly.
