// End-to-end check of the full workflow through a real headless browser:
// student registers -> browses -> requests a course -> administrator (separate Admin Login) approves ->
// student studies it; admin dashboard numbers follow.
//
// Usage (against a DISPOSABLE database - it creates and removes a student):
//   $env:E2E_URL="http://127.0.0.1:5173"; $env:E2E_EMAIL="admin@..."; $env:E2E_PASSWORD="..."; npm run e2e:workflow

import { launch, reporter, text } from './lib/browser.mjs'

const BASE = (process.env.E2E_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const { E2E_EMAIL, E2E_PASSWORD } = process.env
if (!E2E_EMAIL || !E2E_PASSWORD) throw new Error('Set E2E_EMAIL and E2E_PASSWORD (the administrator of a disposable database)')
const { step, finish } = reporter()
const b = await launch({ base: BASE, port: 9355 })
const { goto, click, fill, waitFor, evaluate } = b
const stamp = Date.now()
const email = `workflow.${stamp}@example.edu`
const password = 'Violet-Anchor-Meadow-17'
let studentId = null
let stats = null
let hidden = null
const pathname = () => evaluate('location.pathname')
const fromPage = (path) => evaluate(`fetch('/api${path}', { credentials: 'include' }).then(async (r) => ({ status: r.status, body: await r.json().catch(() => null) }))`)

try {
  // ---- a new student registers through the form
  await goto('/login')
  step('Login page offers both student registration and the Admin Login',
    await waitFor(`${text('Create an account')} && ${text('Admin login')}`, 15000))
  await goto('/register')
  await waitFor(text('Create a student account'), 15000)
  await fill('Full name', 'Workflow Student')
  await fill('Email', email)
  await fill('Age', 21)
  await fill('Password', password)
  await fill('Repeat password', password)
  await click('Create account')
  step('New student registers and lands on their dashboard', await waitFor(`${text('Courses completed')}`, 20000))
  studentId = (await fromPage('/auth/me')).body.user.student_id
  step('A brand-new profile was created (not a seeded student)', studentId > 100)

  // ---- browse and request
  await goto('/courses')
  await waitFor(text('Python Fundamentals'), 15000)
  await click('Python Fundamentals')
  await waitFor(text('Lessons ('), 15000)
  step('Course page offers "Request access" (no instant enrolment)', await waitFor(text('Request access'), 5000))
  await click('Request access', 'document.querySelector("[role=dialog]")')
  step('Request is sent to the administrator', await waitFor(text('Request sent'), 15000))
  step('Student has no enrolment yet', (await fromPage(`/students/${studentId}/enrollments`)).body.length === 0)
  await goto('/learning')
  await waitFor(text('Find a course'), 10000)
  await click('Access requests')
  step('My Learning shows the pending request', await waitFor(text('Pending'), 10000))
  await b.logout()

  // ---- the administrator uses the separate Admin Login
  await b.login(E2E_EMAIL, E2E_PASSWORD)
  await goto('/')
  step('Admin dashboard shows registered students, requests and per-course counts',
    await waitFor(`${text('Registered students')} && ${text('Pending requests')} && ${text('Students enrolled per course')} && ${text('Student progress and performance')}`, 20000))
  const before = (await b.api('/admin/overview')).requests
  step('Dashboard counts one pending request', before.pending >= 1, JSON.stringify(before))
  await goto('/admin/requests')
  step('Admin sees the student\'s request', await waitFor(`${text('Workflow Student')} && ${text('Python Fundamentals')}`, 15000))
  await evaluate(`[...document.querySelectorAll('button')].find((x) => x.innerText.trim() === 'Approve').click()`)
  step('Admin approves the request', await waitFor(text('Nothing is waiting for a decision') || text('No requests here'), 15000))
  const after = (await b.api('/admin/overview')).requests
  step('Dashboard moves it from pending to approved', after.pending === before.pending - 1 && after.approved === before.approved + 1,
    JSON.stringify(after))

  // ---- the administrator unlocks one course and hides another (through the real course page + API)
  await goto('/admin/courses')
  step('Admin course page offers Lock/Unlock, Hide/Unhide, New course and Delete',
    await waitFor(`${text('Unlock')} && ${text('Hide')} && ${text('New course')} && document.querySelector('button[aria-label^="Delete "]')`, 15000))
  const patch = (id, body) => b.api(`/courses/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  stats = (await b.api('/courses?search=ST101')).items[0]
  hidden = (await b.api('/courses?search=WD101')).items[0]
  step('Admin unlocks a course', (await patch(stats.id, { is_locked: false })).is_locked === false)
  step('Admin hides a course', (await patch(hidden.id, { is_active: false })).is_active === false)
  await b.logout()

  // ---- the student can now study
  await b.login(email, password)
  await goto('/learning')
  step('After approval the course appears in My Learning', await waitFor(`${text('Python Fundamentals')} && ${text('Complete next lesson')}`, 15000))
  await click('Complete next lesson')
  await waitFor(text('1 of 5 lessons') || text('20%'), 8000)
  const enrol = (await fromPage(`/students/${studentId}/enrollments`)).body
  step('Backend recorded the enrolment and lesson progress', enrol.length === 1 && enrol[0].completed_lessons >= 1)
  const catalogue = (await fromPage('/courses?limit=100')).body.items
  step('Hidden course is not in the student catalogue', !catalogue.some((c) => c.id === hidden.id))
  step('Unlocked course is shown without an approval badge', catalogue.some((c) => c.id === stats.id && c.is_locked === false))
  await goto('/courses')
  await waitFor(text(stats.title), 15000)
  await click(stats.title)
  await waitFor(text('Lessons ('), 15000)
  step('Unlocked course offers a direct Enroll button', await waitFor(`${text('Enroll')} && !${text('Request access')}`, 5000))
  await click('Enroll', 'document.querySelector("[role=dialog]")')
  step('Student joins the unlocked course immediately', await waitFor(text('You are now enrolled in'), 15000))
  step('Both courses are now in the student\'s learning list',
    (await fromPage(`/students/${studentId}/enrollments`)).body.length === 2)
  await goto('/recommendations')
  step('AI recommendations still load for the new student', await waitFor('document.querySelector("main")', 15000))
  await b.logout()
} catch (e) {
  step(`Unexpected error: ${e.message}`, false)
} finally {
  try {
    await b.login(E2E_EMAIL, E2E_PASSWORD)
    const patch = (id, body) => b.api(`/courses/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (stats) await patch(stats.id, { is_locked: true })       // put the disposable data back
    if (hidden) await patch(hidden.id, { is_active: true })
    if (studentId) await b.api(`/students/${studentId}`, { method: 'DELETE' })
  } catch { /* best effort */ }
  step('No uncaught errors in the browser console',
    b.consoleErrors.filter((e) => !/401|403|404|Failed to load resource/.test(e)).length === 0, b.consoleErrors.join(' | ').slice(0, 200))
  await b.close()
  process.exit(finish())
}
