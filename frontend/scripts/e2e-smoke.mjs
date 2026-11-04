// End-to-end smoke test: drives a real headless browser through the main user
// workflow against the running app (frontend + backend), clicking real buttons.
//
// Usage (backend on :8000 and frontend on :5173 or :4173 must be running):
//   npm run e2e                        # default http://127.0.0.1:5173
//   $env:E2E_URL="http://127.0.0.1:4173"; npm run e2e
//
// Uses Microsoft Edge or Google Chrome via the DevTools protocol (no extra npm
// packages). Override the browser with $env:E2E_BROWSER="C:\path\to\chrome.exe".
// The test creates its own student and deletes it at the end.

import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const BASE = (process.env.E2E_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const PORT = 9333
const CANDIDATES = [
  process.env.E2E_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
const consoleErrors = []

function step(name, ok, detail = '') {
  results.push({ name, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
}

// ---------------------------------------------------------------- browser
const browserPath = CANDIDATES.find((p) => existsSync(p))
if (!browserPath) {
  console.error('No Edge/Chrome found. Set E2E_BROWSER to a Chromium-based browser executable.')
  process.exit(2)
}
const profileDir = mkdtempSync(join(tmpdir(), 'pathwise-e2e-'))
const browser = spawn(browserPath, ['--headless=new', '--disable-gpu', '--no-first-run', `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profileDir}`, '--window-size=1366,900', 'about:blank'], { stdio: 'ignore' })

async function pageSocket() {
  for (let i = 0; i < 50; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()
      const page = targets.find((t) => t.type === 'page')
      if (page) return page.webSocketDebuggerUrl
    } catch { /* browser still starting */ }
    await sleep(200)
  }
  throw new Error('Browser did not expose a debuggable page')
}

const ws = new WebSocket(await pageSocket())
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
let nextId = 1
const pending = new Map()
ws.addEventListener('message', (ev) => {
  const msg = JSON.parse(ev.data)
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg)
    pending.delete(msg.id)
  } else if (msg.method === 'Runtime.exceptionThrown') {
    consoleErrors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text)
  } else if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
    consoleErrors.push(msg.params.args.map((a) => a.value ?? a.description).join(' '))
  }
})
const send = (method, params = {}) => new Promise((resolve) => {
  const id = nextId++
  pending.set(id, resolve)
  ws.send(JSON.stringify({ id, method, params }))
})
await send('Runtime.enable')
await send('Page.enable')

async function evaluate(expression) {
  const res = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (res.result?.exceptionDetails) throw new Error(res.result.exceptionDetails.exception?.description || 'evaluate failed')
  return res.result?.result?.value
}

async function waitFor(expression, timeout = 10000) {
  const end = Date.now() + timeout
  while (Date.now() < end) {
    if (await evaluate(`(() => { try { return Boolean(${expression}) } catch { return false } })()`)) return true
    await sleep(150)
  }
  return false
}

const text = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`

async function goto(path) {
  await send('Page.navigate', { url: BASE + path })
  await waitFor('document.querySelector("main")', 15000)
}

// Click the first visible button/link whose text contains `label` (optionally inside `scope`).
async function click(label, scope = 'document') {
  return evaluate(`(() => {
    const els = [...${scope}.querySelectorAll('button, a, label')]
      .filter((e) => e.offsetParent !== null && !e.disabled && e.innerText.trim().includes(${JSON.stringify(label)}))
    if (!els.length) return false
    els[0].click()
    return true
  })()`)
}

// Set a React-controlled input/select by its <label> text.
async function fill(labelText, value, scope = 'document') {
  return evaluate(`(() => {
    const label = [...${scope}.querySelectorAll('label')].find((l) => l.innerText.trim() === ${JSON.stringify(labelText)})
    const el = label && document.getElementById(label.htmlFor)
    if (!el) return false
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(String(value))})
    el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
    return true
  })()`)
}

const DIALOG = 'document.querySelector("[role=dialog]")'
const api = (path, init) => fetch(`${BASE}/api${path}`, init).then((r) => (r.status === 204 ? null : r.json()))

// ------------------------------------------------------------------ flow
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
  await click('Create student', 'document.querySelector("[role=dialog]")')
  step('Create form shows validation errors for empty fields', await waitFor(text('Name is required')))
  await fill('Full name', 'E2E Test Learner', DIALOG)
  await fill('Email', email, DIALOG)
  await fill('Age', 23, DIALOG)
  await fill('Learning style', 'Visual', DIALOG)
  await fill('Preferred content format', 'Videos', DIALOG)
  await click('Create student', 'document.querySelector("[role=dialog]")')
  step('New student created and selected', await waitFor(text('Now viewing E2E Test Learner'), 10000))
  createdId = (await api(`/students?search=${encodeURIComponent(email)}`)).items[0]?.id
  // Safety: never modify seeded students. Stop unless the new student is the one selected.
  const selected = await waitFor(`document.querySelector('[aria-haspopup=listbox]')?.innerText.includes('Student #${createdId}')`)
  if (!createdId || !selected) throw new Error('Test student was not created/selected; aborting before any changes')

  // Catalog: locked course explains prerequisites; available course can be enrolled.
  await goto('/courses')
  await waitFor(text('Functions & Data Structures'))
  await click('Functions & Data Structures')
  await waitFor('document.querySelector("[role=dialog]")')
  step('Locked course shows its prerequisites', await waitFor(text('Prerequisites required')))
  await click('Close', 'document.querySelector("[role=dialog]")')
  await click('Python Fundamentals')
  await waitFor('document.querySelector("[role=dialog]")')
  await waitFor(text('Lessons (5)'))
  await click('Enroll', 'document.querySelector("[role=dialog]")')
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

  // Roadmap + recommendations pages render.
  await goto('/roadmap')
  step('Roadmap renders course tracks', await waitFor(text('Unlocked next')))
  await goto('/recommendations')
  step('Recommendations page labels AI features as Phase 5', await waitFor(text('AI models are connected in Phase 5')))

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
  step('No uncaught errors in the browser console', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '))
  ws.close()
  browser.kill()
  await sleep(500)
  try { rmSync(profileDir, { recursive: true, force: true }) } catch { /* browser may still hold files */ }
  const failed = results.filter((r) => !r.ok).length
  console.log(`\n${results.length - failed}/${results.length} checks passed`)
  process.exit(failed ? 1 : 0)
}
