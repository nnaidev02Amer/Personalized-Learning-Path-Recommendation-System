// End-to-end check of sign-in, roles and data isolation through a real headless browser.
//
// Usage (against a DISPOSABLE database - it creates accounts):
//   $env:E2E_URL="http://127.0.0.1:5173"; $env:E2E_EMAIL="admin@..."; $env:E2E_PASSWORD="..."; npm run e2e:auth
// Optional: E2E_REGISTRATION=1 when the backend runs with ALLOW_SELF_REGISTRATION=true.

import { approveRequests, launch, reporter, text } from './lib/browser.mjs'

const BASE = (process.env.E2E_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const { E2E_EMAIL, E2E_PASSWORD } = process.env
if (!E2E_EMAIL || !E2E_PASSWORD) throw new Error('Set E2E_EMAIL and E2E_PASSWORD (an administrator of a disposable database)')
const { step, finish } = reporter()
const b = await launch({ base: BASE, port: 9344 })
const { goto, click, fill, waitFor, evaluate } = b
const stamp = Date.now()
const studentEmail = `auth.e2e.${stamp}@example.edu`
const studentPassword = 'Violet-Anchor-Meadow-17'
const createdIds = []
const DLG = 'document.querySelector("[role=dialog]")'

const apiFromPage = (path) => evaluate(`fetch('/api${path}', { credentials: 'include' }).then(async (r) => ({ status: r.status, body: await r.json().catch(() => null) }))`)
const pathname = () => evaluate('location.pathname')

try {
  // ---- anonymous visitors
  await goto('/login')
  step('Login page renders for an anonymous visitor', await waitFor(`${text('Sign in')} && document.querySelector('input[type=password]')`))
  await goto('/learning')
  step('Protected page redirects to /login', await waitFor('location.pathname === "/login"', 10000))

  // ---- invalid login
  await fill('E-mail', E2E_EMAIL)
  await fill('Password', 'definitely-wrong-password')
  await click('Sign in')
  step('Invalid login shows a generic error', await waitFor(text('Incorrect e-mail or password'), 10000))
  step('Invalid login stays on /login', (await pathname()) === '/login')

  // ---- admin
  await b.login(E2E_EMAIL, E2E_PASSWORD)
  step('Administrator asking for a student page is sent to the admin dashboard', (await pathname()) === '/')
  await goto('/')
  step('Admin lands on the admin dashboard', await waitFor(`${text('Administration')} && ${text('Learners who may need help')}`, 15000))
  const navLabels = () => evaluate(`[...document.querySelectorAll('aside nav a')].filter((a) => a.offsetParent !== null).map((a) => a.innerText.trim())`)
  const adminNav = await navLabels()
  step('Admin sidebar shows exactly the six administration links',
    JSON.stringify(adminNav) === JSON.stringify(['Admin dashboard', 'Enrollment requests', 'Students', 'Courses', 'Accounts', 'Model Evaluation']), adminNav.join(' | '))
  step('Admin sees no Student view section', await evaluate(`!/student view/i.test(document.querySelector('aside')?.innerText || '')`))
  for (const studentPath of ['/dashboard', '/learning', '/courses', '/roadmap', '/recommendations', '/analytics', '/profile']) {
    await goto(studentPath)
    if (!(await waitFor('location.pathname === "/"', 10000))) step(`Admin typing ${studentPath} is redirected`, false)
  }
  step('Admin typing any student URL is redirected to the admin dashboard', (await pathname()) === '/')
  await goto('/')
  step('Session cookie is HttpOnly (not readable by page scripts)', !(await evaluate('document.cookie')).includes('plrs_session'))
  await goto('/models')
  step('Admin can open Model Evaluation', await waitFor(text('NDCG Δ vs popularity'), 25000))
  await goto('/admin/students')
  step('Admin students table lists learners', await waitFor(`${text('Students')} && document.querySelectorAll('tbody tr').length >= 5`, 15000))
  await goto('/admin/courses')
  step('Admin course management lists courses', await waitFor(`${text('New course')} && document.querySelectorAll('tbody tr').length >= 5`, 15000))

  // ---- admin creates a student account through the UI
  await goto('/admin/accounts')
  await waitFor(text('New student account'))
  await click('New student account')
  await waitFor(text('Temporary password'))
  await fill('Full name', 'Auth Browser Student', DLG)
  await fill('Email', studentEmail, DLG)
  await fill('Age', 24, DLG)
  await fill('Temporary password', studentPassword, DLG)
  await click('Create account', DLG)
  step('Admin creates a student account from the UI', await waitFor(text('Account created'), 15000))
  const made = await b.api(`/admin/users?search=${encodeURIComponent(studentEmail)}`)
  createdIds.push(made.items[0]?.student_id)

  // ---- sign out
  await b.logout()
  step('Sign out returns to /login', (await pathname()) === '/login')
  await goto('/admin/students')
  step('After sign-out admin pages require sign-in again', await waitFor('location.pathname === "/login"', 10000))
  const me = await apiFromPage('/auth/me')
  step('Session is revoked server-side after sign-out (401)', me.status === 401)

  // ---- student
  await b.login(studentEmail, studentPassword)
  await goto('/')
  step('Student lands on their own dashboard', await waitFor(text('Courses completed'), 15000))
  const studentNav = await navLabels()
  step('Student sidebar shows exactly the seven student links',
    JSON.stringify(studentNav) === JSON.stringify(['Student Dashboard', 'My Learning', 'Course Catalog', 'Learning Roadmap', 'AI Recommendations', 'Progress & Analytics', 'Profile']), studentNav.join(' | '))
  step('Student sees no administration section', await evaluate(`!/administration|Accounts|Model Evaluation/i.test(document.querySelector('aside')?.innerText || '')`))
  step('Student sees their own name, not a student switcher', await evaluate(`!document.querySelector('[aria-haspopup=listbox]') && document.body.innerText.includes('Auth Browser Student')`))
  for (const adminPath of ['/admin/students', '/admin/courses', '/admin/accounts', '/models']) {
    await goto(adminPath)
    if (!(await waitFor('location.pathname === "/"', 10000))) step(`Student typing ${adminPath} is redirected`, false)
  }
  step('Student typing any admin URL is redirected to their dashboard', (await pathname()) === '/' && await waitFor(text('Courses completed'), 10000))

  // ---- student data isolation (the API refuses even if the UI were bypassed)
  const own = await apiFromPage(`/students/${createdIds[0]}`)
  const other = await apiFromPage('/students/7')
  const list = await apiFromPage('/students')
  const evalApi = await apiFromPage('/ml/evaluation')
  step('Student can read their own record', own.status === 200)
  step('Student cannot read a seeded student (404)', other.status === 404)
  step('Student cannot list all students (403)', list.status === 403)
  step('Student cannot read model evaluation (403)', evalApi.status === 403)
  const del = await evaluate(`fetch('/api/students/${createdIds[0]}', { method: 'DELETE', credentials: 'include' }).then((r) => r.status)`)
  step('Student cannot delete a student (403)', del === 403)

  // ---- student enrols in a course through the UI
  await goto('/courses')
  await waitFor(text('Python Fundamentals'))
  await click('Python Fundamentals')
  await waitFor(DLG)
  await waitFor(text('Lessons ('))
  await click('Request access', DLG)
  step('Student sends an enrolment request', await waitFor(text('Request sent'), 15000))
  await goto('/learning')
  await waitFor(text('Find a course'), 10000)
  await click('Access requests')
  step('My Learning lists the pending request', await waitFor(text('Pending'), 10000))
  step('Student has no enrolment before approval', (await apiFromPage(`/students/${createdIds[0]}/enrollments`)).body.length === 0)
  const denied = await evaluate(`fetch('/api/admin/enrollment-requests', { credentials: 'include' }).then((r) => r.status)`)
  step('Student cannot open the admin request list (403)', denied === 403)
  step('Administrator approves the request', (await approveRequests(BASE, E2E_EMAIL, E2E_PASSWORD, createdIds[0])) === 1)
  await goto('/learning')
  step('My Learning shows only the own enrolment', await waitFor(`${text('Python Fundamentals')} && !${text('Statistics')}`, 10000))
  await click('Insights')
  step('Course insights page shows course-scoped guidance', await waitFor(`${text('What to do next')} && ${text('no separate per-course models')}`, 30000))
  await b.logout()

  // ---- registration page reflects the server setting
  await goto('/register')
  if (process.env.E2E_REGISTRATION === '0') {
    step('Registration is closed when disabled', await waitFor(text('Registration is closed'), 10000))
  } else {
    step('Registration form is offered by default', await waitFor(text('Create a student account'), 10000))
  }
  await goto('/admin/login')
  step('A separate Admin Login page exists', await waitFor(`${text('Admin login')} && ${text('Sign in as administrator')}`, 10000))
  await fill('E-mail', studentEmail)
  await fill('Password', studentPassword)
  await click('Sign in as administrator')
  step('A student cannot sign in through the Admin Login', await waitFor(text('not an administrator account'), 10000))
} catch (e) {
  step(`Unexpected error: ${e.message}`, false)
} finally {
  // Clean up the accounts this test created (as admin, through the API).
  try {
    await b.login(E2E_EMAIL, E2E_PASSWORD)
    for (const id of createdIds.filter(Boolean)) await b.api(`/students/${id}`, { method: 'DELETE' })
  } catch { /* best effort */ }
  step('No uncaught errors in the browser console', b.consoleErrors.filter((e) => !/401|403|404|Failed to load resource/.test(e)).length === 0,
    b.consoleErrors.slice(0, 3).join(' | '))
  await b.close()
  process.exit(finish())
}
