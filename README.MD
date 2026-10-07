# SMIS - School Management Information System

**Paquito S. Yu Memorial National High School**

Web-Based School Management System with Automated Grade Management and Form 137 Generation

---

## Tech Stack

- **Backend:** Django 5.1+
- **Frontend:** Django Templates + HTMX + Alpine.js
- **Styling:** Tailwind CSS 4 (compiled locally)
- **Database:** SQLite (development) / PostgreSQL (production)
- **Offline-first:** No CDN dependencies

---

## Features

- Role-based access control (Admin, Registrar, Teacher, Student) — see [docs/registrar-role.md](docs/registrar-role.md) for the Registrar's end-to-end workflow (student registry, grade validation, Form 137 issuance, reports)
- Student information management
- Grade encoding, submission, and validation workflow
- Automatic Form 137 generation with PDF export
- Dashboard analytics and reports
- At-risk student identification
- Audit trail logging
- Dark mode support
- Mobile-responsive design

---

## Installation Guide

### 1. Clone the repository

```bash
git clone <repository-url>
cd SMIS
```

### 2. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

Or using uv:

```bash
uv sync
uv run pip install -r requirements.txt
```

### 4. Install Node.js dependencies (for Tailwind CSS)

```bash
npm install
```

### 5. Download HTMX and Alpine.js (already included in static/js/)

If not present, download:
```bash
curl -o static/js/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js
curl -o static/js/alpine.min.js https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js
```

### 6. Compile Tailwind CSS

```bash
npx @tailwindcss/cli -i static/src/input.css -o static/css/output.css --watch
```

### 7. Set up environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 8. Run migrations

```bash
uv run python manage.py makemigrations accounts students academics grades form137
uv run python manage.py migrate
```

### 9. Create superuser

```bash
uv run python manage.py createsuperuser
```

### 10. Seed sample data

```bash
uv run python manage.py seed_data            # seed (idempotent, keeps existing data)
uv run python manage.py seed_data --reset    # clear sample data & re-seed (keeps admins)
uv run python manage.py seed_data --fresh    # wipe ALL users & data, re-seed from scratch
```

See [Seed Data](#seed-data) below for what gets created and the login credentials.

### 11. Run development server

```bash
uv run python manage.py runserver
```

Visit: http://127.0.0.1:8000

---

## Default Login Credentials

| Role       | Username   | Password     |
|-----------|-----------|-------------|
| Admin     | admin     | admin123    |
| Registrar | registrar | registrar123|
| Teacher   | reyes     | teacher123  |
| Student   | student1  | student123  |

Full account list in [Seed Data](#seed-data).

---

## Seed Data

The `seed_data` management command (`accounts/management/commands/seed_data.py`) populates the
entire database with realistic sample data covering every role and workflow.

### Commands

```bash
uv run python manage.py seed_data           # safe re-run: upserts, never duplicates
uv run python manage.py seed_data --reset   # deletes sample data + non-admin users, then re-seeds
uv run python manage.py seed_data --fresh   # hard reset: deletes ALL users (incl. admins) and data
```

> ⚠️ `--reset` and `--fresh` are irreversible. `--fresh` also destroys manually created
> accounts — export anything important first. The whole seed runs in a single transaction,
> so a failure mid-way rolls back automatically.

### Seeded Accounts

| Role | Username | Password | Notes |
|------|----------|----------|-------|
| Admin | `admin` | `admin123` | Superuser / system administrator |
| Registrar | `registrar` | `registrar123` | Maria Santos — validates grades, issues Form 137 |
| Teacher | `reyes` | `teacher123` | Ana Reyes |
| Teacher | `lopez` | `teacher123` | Carmen Lopez |
| Teacher | `gonzaga` | `teacher123` | Jose Gonzaga |
| Teacher | `mendoza` | `teacher123` | Elena Mendoza |
| Teacher | `delacruz` | `teacher123` | Antonio Delacruz |
| Teacher | `bautista` | `teacher123` | Sophia Bautista |
| Student | `student1` – `student5` | `student123` | Linked to the first 5 Student records |

### What Gets Created

- **School years:** `2024-2025` (past) and `2025-2026` (current).
- **Grade levels:** Grade 7–12, each with 8 JHS core subjects (Filipino, English,
  Mathematics, Science, AP, EsP, MAPEH, TLE) — 48 subjects total.
- **Sections:** A/B/C per grade level per school year, with randomly assigned advisers.
- **Grading periods:** Quarter 1–4 per school year with month coverage
  (Q1 Aug–Oct, Q2 Nov–Jan, Q3 Feb–Apr, Q4 May–Jul). Only current-year Q1 is
  `is_current` and open for grade submissions.
- **Teacher assignments:** ~96 — each teacher covers 2 of 3 sections per subject.
- **Students:** ~85–90 across Grade 7–12 sections with 12-digit LRNs, mixed statuses
  (active / inactive / transferred / dropped); the first 5 are linked to student logins.
- **Grades:** Full component structure per DepEd class record:
  - Written Work: 5 item scores + per-item highest possible scores (WW weight 20%)
  - Performance Tasks: 3 item scores + maxima (PT weight 50%)
  - Quarterly Assessment: 3 item scores + maxima (QA weight 30%)
  - Raw item scores (WW 1-5, PT 1-3, QA 1-3) are stored as **whole numbers only**
    (`IntegerField`); the model's `clean()` rejects decimal input. Component totals
    and the weighted quarter grade may still carry decimals.
  - ~20% of classes use alternative weights (30/40/30 or 25/50/25); quarter grades
    are computed with the model's `weighted_quarter_grade()` so PS/WS/term-grade
    values are always internally consistent.
  - Current-year workflow statuses by quarter: Q1 validated, Q2 mixed validated/submitted,
    Q3 mixed draft/submitted/validated, Q4 mostly drafts.
  - Active Grade 8–12 students also get a full validated `2024-2025` year for Form 137 history.
- **Submissions & validations:** `GradeSubmission` (pending/approved) and `GradeValidation`
  records mirroring the submitted/validated workflow states.
- **Form 137 records:** Generated for every active student with validated current-year grades.
- **Audit log:** 8 sample entries covering login, grade encode/submit/validate/return,
  and Form 137 generation actions.

### Typical Counts After `--reset`

```
users 13 | students 89 | grades 2816 | submissions 348 | validations 62 |
form137 40 | audit 8 | periods 8 | assignments 96
```

---

## Grade Workflow

1. Admin creates school year, grade levels, sections, subjects
2. Admin assigns teachers to subjects and sections
3. Teacher encodes grades → saves as draft
4. Teacher submits grades for validation
5. Registrar reviews and validates/returns grades
6. Validated grades are locked
7. Registrar generates Form 137 from validated grades
8. Registrar/Admin views reports and analytics

---

## UV Commands

```bash
# Install all dependencies
uv sync

# Run Django management commands
uv run python manage.py migrate
uv run python manage.py runserver
uv run python manage.py seed_data

# Add a dependency
uv add django-cors-headers

# Run tests
uv run pytest
```

---

## Project Structure

```
SMIS/
├── config/              # Django project settings
├── accounts/            # User management & authentication
├── students/            # Student information management
├── academics/           # School year, sections, subjects
├── grades/              # Grade encoding & validation
├── form137/             # Form 137 generation
├── reports/             # Analytics & reports
├── dashboard/           # Main dashboard
├── templates/           # HTML templates
├── static/              # Static files (CSS, JS, icons)
│   ├── css/
│   ├── js/
│   ├── src/
│   └── icons/
├── manage.py
├── pyproject.toml
├── requirements.txt
├── tailwind.config.js
├── package.json
└── README.md
```

---

## License

Educational Use Only - Paquito S. Yu Memorial National High School
