// End-to-end smoke test: drives a real headless browser through the main user
// workflow against the running app (frontend + backend), clicking real buttons.
//
// Usage (backend on :8000 and frontend on :5173 or :4173 must be running):
//   npm run e2e                        # default http://127.0.0.1:5173
//   $env:E2E_URL="http://127.0.0.1:4173"; npm run e2e
// Sign in as an administrator: E2E_EMAIL / E2E_PASSWORD (use a DISPOSABLE database - this test writes data).
// The test creates its own student and deletes it at the end.

import { DIALOG, approveRequests, createStudentAccount, launch, removeStudent, reporter, sleep, text } from './lib/browser.mjs'

const BASE = (process.env.E2E_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const { step, finish } = reporter()
const b = await launch({ base: BASE })
const { goto, click, fill, waitFor, evaluate, api } = b
const { E2E_EMAIL, E2E_PASSWORD } = process.env
if (!E2E_EMAIL || !E2E_PASSWORD) throw new Error('Set E2E_EMAIL and E2E_PASSWORD (an administrator of a disposable database)')

let createdId = null
try {
  const health = await api('/health').catch(() => null)
  step('Backend reachable through the frontend proxy', health?.status === 'ok')
  if (!health) throw new Error(`API not reachable at ${BASE}/api — start the backend first`)

  // The administrator creates a disposable student account; the test then signs in as that student.
  const account = await createStudentAccount(BASE, E2E_EMAIL, E2E_PASSWORD)
  createdId = account.studentId
  await b.login(account.email, account.password)
  await goto('/')
  step('Student signs in and lands on their own dashboard', await waitFor(text('Courses completed')))
  step('Signed in as the new test student', (await api('/auth/me')).user.student_id === createdId)

  // Catalog: locked course explains prerequisites; available course can be enrolled.
  await goto('/courses')
  await waitFor(text('Functions & Data Structures'))
  await click('Functions & Data Structures')
  await waitFor(DIALOG)
  step('Locked course shows its prerequisites', await waitFor(text('Prerequisites required')))
  await click('Close', DIALOG)
  await click('Python Fundamentals')
  await waitFor(DIALOG)
  await waitFor(text('Lessons (5)'))
  await click('Request access', DIALOG)
  step('Request access sends a request for approval', await waitFor(text('Request sent')))
  step('Student is not enrolled before approval', (await api(`/students/${createdId}/enrollments`)).length === 0)
  step('Administrator approves the request', (await approveRequests(BASE, E2E_EMAIL, E2E_PASSWORD, createdId)) === 1)

  // My Learning: complete all lessons.
  await goto('/learning')
  await waitFor(text('Complete next lesson'))
  for (let i = 0; i < 5; i++) {
    await click('Complete next lesson')
    await waitFor(`!document.querySelector('button[disabled] .animate-spin')`, 5000)
    await sleep(400)
  }
  step('Completing every lesson completes the course', await waitFor(text('Course completed!'), 8000))
  const enrollment = (await api(`/students/${createdId}/enrollments`))[0]
  step('Backend recorded 5/5 lessons', enrollment?.completed_lessons === 5 && enrollment.status === 'completed')

  // Take the quiz (answer key for PY101 is 1, 2, 1, 2).
  const course = await api(`/courses/${enrollment.course.id}`)
  await goto(`/quiz/${course.quizzes[0].id}`)
  await waitFor(text('Submit answers'))
  for (const [q, option] of [[0, 1], [1, 2], [2, 1], [3, 2]]) {
    await evaluate(`document.querySelectorAll('fieldset')[${q}].querySelectorAll('input[type=radio]')[${option}].click()`)
  }
  await click('Submit answers')
  step('Quiz is graded by the server (4/4 correct)', await waitFor(text('4 of 4 correct'), 8000))

  // Dashboard and analytics reflect the new activity.
  await goto('/dashboard')
  await waitFor(text('Courses completed'))
  step('Dashboard shows the quiz result', await waitFor(text('Passed · 100%')))
  await goto('/analytics')
  step('Analytics renders charts and quiz history', await waitFor(`${text('Quiz history')} && document.querySelectorAll('.recharts-surface').length >= 2`))

  // Profile edit with client-side validation.
  await goto('/profile')
  await waitFor(text('Edit profile'))
  await fill('Email', 'not-an-email')
  await click('Save changes')
  step('Invalid email is rejected in the form', await waitFor(text('Enter a valid email address')))
  await fill('Email', account.email)
  await fill('Full name', 'E2E Renamed Learner')
  await click('Save changes')
  step('Profile changes are saved', await waitFor(text('Profile saved')) && (await api(`/students/${createdId}`)).name === 'E2E Renamed Learner')

  // Theme toggle.
  const before = await evaluate('document.documentElement.classList.contains("dark")')
  await evaluate('document.querySelector("[aria-label^=\'Switch to\']").click()')
  step('Theme toggle switches light/dark', await waitFor(`document.documentElement.classList.contains("dark") === ${!before}`))

  await goto('/roadmap')
  step('Roadmap renders tracks and model-ranked next steps', await waitFor(`${text('Next steps')} && ${text('ML ranked')}`, 20000))
  await goto('/recommendations')
  step('AI page shows model recommendations', await waitFor(`${text('Real model outputs')} && ${text('ML model output')} && document.querySelectorAll('ol li button').length >= 1`, 30000))
  step('AI page shows BKT, bandit, prediction and style cards',
    await waitFor(`${text('Skill mastery')} && ${text('Suggested next difficulty')} && ${text('Predicted quiz scores')} && ${text('Model prediction')}`, 20000))
  await click('What should I learn next?')
  step('Assistant answers from model outputs', await waitFor(`${text('Top recommended next courses')} || ${text('Answered by')}`, 30000))
  await b.logout()
  await b.login(E2E_EMAIL, E2E_PASSWORD)
  await goto('/models')
  step('Model evaluation page shows baseline comparisons (administrator)', await waitFor(`${text('NDCG Δ vs popularity')} && (${text('No significant difference from')} || ${text('Significantly')})`, 20000))

  // A student cannot delete anyone; the administrator removes the test student.
  const asStudent = await fetch(`${BASE}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: account.email, password: account.password }) })
  const studentCookie = asStudent.headers.get('set-cookie').split(';')[0]
  const denied = await fetch(`${BASE}/api/students/${createdId}`, { method: 'DELETE',
    headers: { Cookie: studentCookie, 'X-CSRF-Token': (await asStudent.json()).csrf_token } })
  step('Student cannot delete their own record (403)', denied.status === 403)
  step('Administrator deletes the test student (204)', (await removeStudent(BASE, E2E_EMAIL, E2E_PASSWORD, createdId)) === 204)
  createdId = null
} catch (e) {
  step(`Unexpected error: ${e.message}`, false)
} finally {
  if (createdId) await removeStudent(BASE, E2E_EMAIL, E2E_PASSWORD, createdId).catch(() => {})
  step('No uncaught errors in the browser console', b.consoleErrors.length === 0, b.consoleErrors.slice(0, 3).join(' | '))
  await b.close()
  process.exit(finish())
}
