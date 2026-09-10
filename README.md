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

## 4. What's unique about this, versus other EdTech platforms

Most Indian EdTech platforms — BYJU'S, Vedantu, Unacademy and similar — are
**consumer-facing content platforms**: their core product is video lessons,
live tutoring, and test prep, sold directly to students and parents who
already have a device, a connection, and the ability to pay. This system is
a different category of product entirely: it's **government-facing
infrastructure for keeping already-enrolled students from disappearing from
the system**, aimed at the students those platforms don't reach — the ones
without a reliable device or connection in the first place.

Concretely, what that difference produces in the code:

- **It predicts *before* the problem, instead of selling a solution *after* it.**
  A tutoring app helps a student who's already struggling and already has a
  parent willing to pay for extra help. This system's whole job is upstream
  of that: flagging, before a dropout happens, which specific student is at
  risk and *why* (`ml/dropout_risk_model.py::explain_prediction`) — attendance,
  test scores, digital access — so a school can intervene while the student
  is still enrolled, not after they're already gone.

- **It's built for the lowest-bandwidth channel that exists, not the newest one.**
  Consumer EdTech competes on app polish and video quality, which assumes a
  smartphone and real data. This system's question-answering channel is
  **WhatsApp** (`integrations/whatsapp_client.py`) — text-only, works on a
  basic connection, and answers in the asker's own Indian language rather
  than requiring English or an app download.

- **Data governance is a first-class feature, not an afterthought.**
  A consumer app's core incentive is to keep and monetize as much user data
  as possible. This system does the opposite by design: a JWT scoped to one
  state's education department can *only* ever query that state's
  students (enforced on every route, not just at login), there's a working
  right-to-deletion endpoint, and the research-export path pseudonymizes
  student IDs with a keyed HMAC rather than storing or selling raw student
  profiles.

- **It's designed to be operated by a state government, not a single company.**
  Multi-tenant by state from the ground up (one deployment, many state
  education departments, strict data isolation between them), with
  infrastructure-as-code (Terraform + Kubernetes) so a state's IT team can
  audit and redeploy the entire system rather than depending on a vendor's
  black-box SaaS.

- **The AI answers are grounded, not generative.** The Q&A assistant doesn't
  freely generate answers about policy — it retrieves the actual relevant
  passage from official documents first (RAG) and is instructed to answer
  only from what's retrieved, which matters a great deal more for "what does
  the government's education policy say" than for a tutoring chatbot helping
  with algebra homework.

In short: consumer EdTech platforms optimize for engagement and content
quality for students who can already access them. This system optimizes for
reach and retention for the students most platforms structurally can't
reach — with privacy and state-level data control built in as requirements,
not features bolted on later.
