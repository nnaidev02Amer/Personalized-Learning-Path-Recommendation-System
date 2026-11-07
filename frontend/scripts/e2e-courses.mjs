// End-to-end check of admin course management through a real headless browser:
// create / lock / unlock / hide / unhide / delete a course, and what a student sees in each state.
//
// Usage (against a DISPOSABLE database - it creates and removes a course and a student):
//   $env:E2E_URL="http://127.0.0.1:5173"; $env:E2E_EMAIL="admin@..."; $env:E2E_PASSWORD="..."; npm run e2e:courses

import { createStudentAccount, launch, removeStudent, reporter, text } from './lib/browser.mjs'

const BASE = (process.env.E2E_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const { E2E_EMAIL, E2E_PASSWORD } = process.env
if (!E2E_EMAIL || !E2E_PASSWORD) throw new Error('Set E2E_EMAIL and E2E_PASSWORD (the administrator of a disposable database)')
const { step, finish } = reporter()
const b = await launch({ base: BASE, port: 9366 })
const { goto, click, waitFor, evaluate } = b
const DLG = 'document.querySelector("[role=dialog]")'
const CODE = `E2E${String(Date.now()).slice(-6)}`
const TITLE = `Course management check ${CODE}`
let account = null

const setField = (label, value, scope = DLG) => evaluate(`(() => {
  const l = [...${scope}.querySelectorAll('label')].find((x) => x.innerText.trim() === ${JSON.stringify(label)})
  const el = l && document.getElementById(l.htmlFor)
  if (!el) return false
  const proto = { SELECT: HTMLSelectElement, TEXTAREA: HTMLTextAreaElement }[el.tagName]?.prototype || HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(String(value))})
  el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
  return true
})()`)
const rowText = (code) => evaluate(`[...document.querySelectorAll('tbody tr')].find((t) => t.innerText.includes(${JSON.stringify(code)}))?.innerText || ''`)
const rowClick = (code, label) => evaluate(`(() => {
  const tr = [...document.querySelectorAll('tbody tr')].find((t) => t.innerText.includes(${JSON.stringify(code)}))
  const btn = tr && [...tr.querySelectorAll('button')].find((x) => x.innerText.trim() === ${JSON.stringify(label)})
  if (!btn) return false
  btn.click()
  return true
})()`)
const adminCourses = async () => { await goto('/admin/courses'); await waitFor(text('PY101'), 20000) }
// Wait until the row of `code` shows `pattern` (the table reloads after each action).
const rowShows = (code, pattern) => waitFor(`(() => { const t = [...document.querySelectorAll('tbody tr')].find((x) => x.innerText.includes(${JSON.stringify(code)})); return Boolean(t) && ${pattern}.test(t.innerText) })()`, 10000)
const fromPage = (path) => evaluate(`fetch('/api${path}', { credentials: 'include' }).then(async (r) => ({ status: r.status, body: await r.json().catch(() => null) }))`)
const openAsStudent = async () => {
  await b.login(account.email, account.password)
  await goto('/courses')
  await waitFor(text('Course Catalog'), 15000)
}

try {
  account = await createStudentAccount(BASE, E2E_EMAIL, E2E_PASSWORD, 'Course Check Student')
  await b.login(E2E_EMAIL, E2E_PASSWORD)

  // ---- view every course and its status
  await adminCourses()
  const rows = await evaluate(`[...document.querySelectorAll('tbody tr')].map((t) => t.innerText)`)
  step('Admin sees every course', rows.length >= 24, `${rows.length} rows`)
  step('Every row shows visible/hidden and locked/open status', rows.every((r) => /(visible|hidden)/.test(r) && /(locked|open)/.test(r)))
  const buttons = await evaluate(`[...document.querySelectorAll('tbody tr')].every((t) => ['Delete'].every((l) => [...t.querySelectorAll('button')].some((x) => x.innerText.trim() === l)) && [...t.querySelectorAll('button')].some((x) => /^(Lock|Unlock)$/.test(x.innerText.trim())) && [...t.querySelectorAll('button')].some((x) => /^(Hide|Unhide)$/.test(x.innerText.trim())))`)
  step('Every row offers Lock/Unlock, Hide/Unhide and Delete', buttons)

  // ---- create a LOCKED course through the form
  await click('New course')
  await waitFor(text('Create course'), 10000)
  await setField('Code', CODE)
  await setField('Title', TITLE)
  await setField('Topic', 'Programming')
  await setField('Access', 'locked')
  await setField('Skills (comma separated)', 'testing')
  await setField('Description', 'Created by the course management end-to-end test.')
  await setField('Lessons — one per line: Title | minutes', 'Intro | 10\nNext | 15')
  await click('Create course', DLG)
  step('Admin creates a course', await waitFor(text('Course created'), 15000))
  await waitFor(`${text(CODE)}`, 10000)
  step('New course is visible and locked in the table', await rowShows(CODE, '/visible[\\s\\S]*locked/'))
  await b.logout()

  // ---- student: locked -> Request access
  await openAsStudent()
  await waitFor(text(TITLE), 15000)
  await click(TITLE)
  await waitFor(text('Lessons ('), 15000)
  step('Locked course offers "Request access" (no Enroll)', await waitFor(`${text('Request access')} && !${text('Start learning')}`, 5000))
  await b.logout()

  // ---- admin unlocks -> student can Enroll
  await b.login(E2E_EMAIL, E2E_PASSWORD)
  await adminCourses()
  await waitFor(text(CODE), 10000)
  step('Admin unlocks the course', await rowClick(CODE, 'Unlock') && await waitFor(text('Course unlocked'), 10000))
  step('Table now shows it as open', await rowShows(CODE, '/open/'))
  await b.logout()
  await openAsStudent()
  await waitFor(text(TITLE), 15000)
  await click(TITLE)
  await waitFor(text('Lessons ('), 15000)
  step('Unlocked course offers a direct "Enroll"', await waitFor(`${text('Enroll')} && !${text('Request access')}`, 5000))
  await b.logout()

  // ---- admin locks again, then hides -> gone from the student catalogue
  await b.login(E2E_EMAIL, E2E_PASSWORD)
  await adminCourses()
  step('Admin locks it again', await rowClick(CODE, 'Lock') && await waitFor(text('Course locked'), 10000))
  await rowShows(CODE, '/locked/')
  step('Admin hides it', await rowClick(CODE, 'Hide') && await waitFor(text('Course hidden'), 10000))
  step('Table shows it as hidden', await rowShows(CODE, '/hidden/'))
  await b.logout()
  await openAsStudent()
  step('Hidden course is not in the student catalogue (UI)', await evaluate(`!document.body.innerText.includes(${JSON.stringify(TITLE)})`))
  const list = (await fromPage('/courses?limit=100&search=' + CODE)).body
  step('Hidden course is not in the student catalogue (API)', list.items.length === 0)
  await b.logout()

  // ---- admin unhides, then deletes the unused course; a used course is protected
  await b.login(E2E_EMAIL, E2E_PASSWORD)
  await adminCourses()
  step('Admin unhides it', await rowClick(CODE, 'Unhide') && await waitFor(text('Course visible'), 10000))
  await rowShows(CODE, '/visible/')
  await rowClick(CODE, 'Delete')
  await waitFor(text('Nobody has used it'), 10000)
  await click('Delete', DLG)
  step('Admin deletes the unused course', await waitFor(text('Course deleted'), 15000))
  step('Deleted course is gone from the table', await waitFor(`!${text(CODE)}`, 10000))

  await rowClick('PY101', 'Delete')
  step('A course with enrolled students is protected, with an explanation', await waitFor(text('would erase their progress'), 10000))
  await click('Close', DLG)
  const py = (await fromPage('/courses?search=PY101')).body
  step('Protected course (and its students\' progress) still exists', py.items.length === 1 && py.items[0].enrolled_count > 0)
  await b.logout()

  // ---- only the admin may do any of it
  await b.login(account.email, account.password)
  const forbidden = await evaluate(`Promise.all([
    fetch('/api/courses/1', { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: '{"is_locked": false}' }),
    fetch('/api/courses/1', { method: 'DELETE', credentials: 'include' }),
  ]).then((rs) => rs.map((r) => r.status))`)
  step('Student cannot lock/unlock/hide/delete (blocked)', forbidden.every((s) => s === 403), forbidden.join(','))
  await goto('/admin/courses')
  step('Student cannot open the admin course page', await waitFor('location.pathname === "/"', 10000))
  await b.logout()
} catch (e) {
  step(`Unexpected error: ${e.message}`, false)
} finally {
  try {
    await b.login(E2E_EMAIL, E2E_PASSWORD)
    const left = (await b.api(`/courses?search=${CODE}&include_archived=true`)).items || []
    for (const c of left) await b.api(`/courses/${c.id}`, { method: 'DELETE' })      // leave the disposable data as found
    if (account) await removeStudent(BASE, E2E_EMAIL, E2E_PASSWORD, account.studentId)
  } catch { /* best effort */ }
  step('No uncaught errors in the browser console',
    b.consoleErrors.filter((e) => !/401|403|404|Failed to load resource/.test(e)).length === 0, b.consoleErrors.join(' | ').slice(0, 200))
  await b.close()
  process.exit(finish())
}
