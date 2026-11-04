// End-to-end smoke test: drives a real headless browser through the main user
// workflow against the running app (frontend + backend), clicking real buttons.
//
// Usage (backend on :8000 and frontend on :5173 or :4173 must be running):
//   npm run e2e                        # default http://127.0.0.1:5173
//   $env:E2E_URL="http://127.0.0.1:4173"; npm run e2e
// The test creates its own student and deletes it at the end.

import { DIALOG, launch, reporter, sleep, text } from './lib/browser.mjs'

const BASE = (process.env.E2E_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const { step, finish } = reporter()
const b = await launch({ base: BASE })
const { goto, click, fill, waitFor, evaluate, api } = b

let createdId = null
const email = `e2e.${Date.now()}@example.edu`
try {
  const health = await api('/health').catch(() => null)
  step('Backend reachable through the frontend proxy', health?.status === 'ok')
  if (!health) throw new Error(`API not reachable at ${BASE}/api — start the backend first`)

  await goto('/')
  step('Dashboard loads with a student', await waitFor(text('Courses completed')))

  // Create a student through the Profile page form.
  await goto('/profile')
  await waitFor(text('New student'))
  await click('New student')
  await waitFor(text('Create a new student'))
  await click('Create student', DIALOG)
  step('Create form shows validation errors for empty fields', await waitFor(text('Name is required')))
  await fill('Full name', 'E2E Test Learner', DIALOG)
  await fill('Email', email, DIALOG)
  await fill('Age', 23, DIALOG)
  await fill('Learning style', 'Visual', DIALOG)
  await fill('Preferred content format', 'Videos', DIALOG)
  await click('Create student', DIALOG)
  step('New student created and selected', await waitFor(text('Now viewing E2E Test Learner'), 10000))
  createdId = (await api(`/students?search=${encodeURIComponent(email)}`)).items[0]?.id
  // Safety: never modify seeded students. Stop unless the new student is the one selected.
  const selected = await waitFor(`document.querySelector('[aria-haspopup=listbox]')?.innerText.includes('Student #${createdId}')`)
  if (!createdId || !selected) throw new Error('Test student was not created/selected; aborting before any changes')

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
  await click('Enroll', DIALOG)
  step('Enroll button enrolls the student', await waitFor(text('You are now enrolled in Python Fundamentals')))

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
  await goto('/')
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
  await fill('Email', email)
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
  await goto('/models')
  step('Model evaluation page shows baseline comparisons', await waitFor(`${text('NDCG Δ vs popularity')} && (${text('No significant difference from')} || ${text('Significantly')})`, 20000))

  // Delete the test student via the UI.
  await goto('/profile')
  await waitFor(text('Delete student'))
  await click('Delete student')
  await waitFor(text('Delete permanently'))
  await click('Delete permanently')
  const gone = await waitFor(text('Student deleted'))
  const check = await fetch(`${BASE}/api/students/${createdId}`)
  step('Delete removes the student', gone && check.status === 404)
  if (check.status === 404) createdId = null
} catch (e) {
  step(`Unexpected error: ${e.message}`, false)
} finally {
  if (createdId) await api(`/students/${createdId}`, { method: 'DELETE' }).catch(() => {})
  step('No uncaught errors in the browser console', b.consoleErrors.length === 0, b.consoleErrors.slice(0, 3).join(' | '))
  await b.close()
  process.exit(finish())
}
