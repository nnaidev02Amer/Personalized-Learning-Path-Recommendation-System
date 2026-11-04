# Frontend (Phase 4)

React 19 + Vite 8 + Tailwind CSS 4 + Recharts 3 + Lucide icons + React Router 7.
No other runtime dependencies.

## Run (Windows PowerShell)

```powershell
# terminal 1 – backend (repository root)
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload

# terminal 2 – frontend
cd frontend
npm install          # first time only
npm run dev          # http://localhost:5173
```

Vite proxies `/api/*` to `http://127.0.0.1:8000`, so the browser uses one origin and
no CORS setup is needed. Change the target with `VITE_API_PROXY_TARGET`
(see `frontend/.env.example`).

| Command | Purpose |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npm run build` | Production build into `frontend/dist` |
| `npm run preview` | Serve the production build on http://localhost:4173 (also proxies `/api`) |
| `npm run e2e` | Browser smoke test of the whole workflow (needs backend + dev/preview server running; uses installed Edge/Chrome) |

## Structure

```
frontend/
├── index.html                 # theme applied before first paint
├── vite.config.js             # React + Tailwind plugins, /api proxy
├── scripts/e2e-smoke.mjs      # DevTools-protocol smoke test (18 checks)
└── src/
    ├── main.jsx, App.jsx      # providers + routes (each page lazy-loaded)
    ├── index.css              # Tailwind + light/dark design tokens
    ├── api/client.js          # fetch wrapper, ApiError, every endpoint
    ├── hooks/useApi.js        # {data, error, loading, reload}, debounce
    ├── context/               # Theme, current Student, Toasts
    ├── utils/                 # formatting, course status (locked/available/…)
    ├── components/
    │   ├── layout/            # Layout, Sidebar, StudentSwitcher, navigation
    │   ├── ui/                # Button, Card/StatCard, Badge, ProgressBar, Modal,
    │   │                      # Form fields, Tabs, StarRating, PageHeader, States
    │   ├── charts/            # ChartCard (+table view), WeeklyActivity,
    │   │                      # ScoreTimeline, TopicScores
    │   ├── course/            # CourseCard, CourseDetailModal (enrol)
    │   ├── learning/          # EnrollmentCard (lessons, quiz, pause, rate)
    │   └── profile/           # StudentForm (+ client validation)
    └── pages/                 # Dashboard, MyLearning, CourseCatalog, Roadmap,
                               # Recommendations, Analytics, Profile, Quiz, NotFound
```

## Pages → API endpoints

| Page | Data | Actions |
|---|---|---|
| Dashboard | `/students/{id}/summary`, `/progress?weeks=8`, `/enrollments` | Mark next lesson done |
| My Learning | `/enrollments`, `/courses/{id}` (lessons) | Complete lesson, take quiz, pause/resume, rate |
| Course Catalog | `/courses` (search + filters), `/meta`, `/enrollments` | Open details, enrol (prerequisite errors shown) |
| Learning Roadmap | `/courses`, `/enrollments` | Open course, enrol |
| AI Recommendations | `/progress`, `/courses`, `/enrollments` | Open course, enrol |
| Progress & Analytics | `/progress?weeks=4..26`, `/quiz-attempts` | Change range, chart ↔ table |
| Profile | `/students/{id}`, `/meta`, `/enrollments?status=active` | Edit, log study time, create, delete student |
| Quiz | `/quizzes/{id}` | Submit answers → graded feedback |
| AI Recommendations (Phase 5) | `/recommendations`, `/skills`, `/adaptive-difficulty`, `/predictions`, `/learning-style`, `/ml/status` | Switch method, open/enrol, chat with the assistant |
| Model Evaluation (Phase 5) | `/ml/evaluation` | Switch protocol, retrain |

## What is real vs. not yet connected

Every number and list comes from the API — there is no hard-coded dashboard data.
The **Roadmap** is computed from prerequisites and the student's enrolments (not AI),
and the **AI Recommendations** page states that model output arrives in Phase 5; the
sections it shows now are explicitly labelled *rule-based* or *descriptive statistics*.
There is no login yet: the top-bar switcher selects which student is viewed.

## Design notes
* Light/dark themes from CSS tokens (`src/index.css`); toggle persists in `localStorage`.
* Charts use the validated data-viz palette slot 1 (blue, stepped per theme), single series
  per chart (no legend needed), 4px rounded bar ends, 2px lines, ≥8px markers, hover
  tooltips, and a Table toggle for accessibility. Animations are disabled for
  deterministic rendering.
* Loading skeletons, error states (with a "backend not reachable" hint), empty states
  and toasts on every page/action. Verified at 375 px, 750 px and 1440 px widths.
