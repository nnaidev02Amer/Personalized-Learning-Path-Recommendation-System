// Minimal headless-browser driver over the Chrome DevTools Protocol.
// Uses an installed Edge/Chrome and Node's built-in WebSocket - no npm packages.

import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const CANDIDATES = [
  process.env.E2E_BROWSER,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean)

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
export const text = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`
export const DIALOG = 'document.querySelector("[role=dialog]")'

export async function launch({ base, port = 9333 }) {
  const browserPath = CANDIDATES.find((p) => existsSync(p))
  if (!browserPath) throw new Error('No Edge/Chrome found. Set E2E_BROWSER to a Chromium-based browser executable.')
  const profileDir = mkdtempSync(join(tmpdir(), 'pathwise-e2e-'))
  const proc = spawn(browserPath, ['--headless=new', '--disable-gpu', '--no-first-run', `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`, '--window-size=1366,900', 'about:blank'], { stdio: 'ignore' })

  let wsUrl
  for (let i = 0; i < 50 && !wsUrl; i++) {
    try {
      const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json()
      wsUrl = targets.find((t) => t.type === 'page')?.webSocketDebuggerUrl
    } catch { /* still starting */ }
    if (!wsUrl) await sleep(200)
  }
  if (!wsUrl) throw new Error('Browser did not expose a debuggable page')

  const ws = new WebSocket(wsUrl)
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  let nextId = 1
  const pending = new Map()
  const consoleErrors = []
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
  await send('Network.enable')

  const b = {
    base, send, consoleErrors,
    async evaluate(expression) {
      const res = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
      if (res.result?.exceptionDetails) throw new Error(res.result.exceptionDetails.exception?.description || 'evaluate failed')
      return res.result?.result?.value
    },
    async waitFor(expression, timeout = 10000) {
      const end = Date.now() + timeout
      while (Date.now() < end) {
        if (await b.evaluate(`(() => { try { return Boolean(${expression}) } catch { return false } })()`)) return true
        await sleep(150)
      }
      return false
    },
    async goto(path) {
      await send('Page.navigate', { url: base + path })
      await b.waitFor('document.querySelector("main")', 15000)
    },
    // Click the first visible, enabled button/link/label whose text contains `label`.
    click(label, scope = 'document') {
      return b.evaluate(`(() => {
        const els = [...${scope}.querySelectorAll('button, a, label, [role=tab]')]
          .filter((e) => e.offsetParent !== null && !e.disabled && e.innerText.trim().includes(${JSON.stringify(label)}))
        if (!els.length) return false
        els[0].click()
        return true
      })()`)
    },
    // Set a React-controlled input/select by its <label> text.
    fill(labelText, value, scope = 'document') {
      return b.evaluate(`(() => {
        const label = [...${scope}.querySelectorAll('label')].find((l) => l.innerText.trim() === ${JSON.stringify(labelText)})
        const el = label && document.getElementById(label.htmlFor)
        if (!el) return false
        const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(String(value))})
        el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
        return true
      })()`)
    },
    async setViewport(width, height = 900) {
      await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 768 })
    },
    async screenshot(file) {
      const res = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
      writeFileSync(file, Buffer.from(res.result.data, 'base64'))
    },
    // Node-side API calls carry the session cookie and CSRF token obtained by login().
    session: null,
    api: (path, init = {}) => {
      const headers = { ...(init.headers || {}) }
      if (b.session) {
        headers.Cookie = b.session.cookie
        if ((init.method || 'GET') !== 'GET') headers['X-CSRF-Token'] = b.session.csrf
      }
      return fetch(`${base}/api${path}`, { ...init, headers }).then((r) => (r.status === 204 ? null : r.json()))
    },
    // Sign in twice: once for Node-side api() calls, once through the real login form in the browser.
    async login(email, password) {
      const res = await fetch(`${base}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }) })
      if (!res.ok) throw new Error(`login failed (${res.status}) - set E2E_EMAIL / E2E_PASSWORD to a valid account`)
      const body = await res.json()
      const admin = body.user.role === 'admin'                    // administrators use the separate Admin Login page
      b.session = { cookie: res.headers.get('set-cookie').split(';')[0], csrf: body.csrf_token }
      await send('Page.navigate', { url: `${base}${admin ? '/admin/login' : '/login'}` })
      await b.waitFor('document.querySelector("main") && document.querySelector("input[type=password]")', 15000)
      await b.fill('E-mail', email)
      await b.fill('Password', password)
      await b.click(admin ? 'Sign in as administrator' : 'Sign in')
      await b.waitFor('!location.pathname.includes("/login") && document.querySelector("header")', 15000)
    },
    async logout() {
      await b.click('Sign out')
      await b.waitFor('location.pathname === "/login"', 10000)
      b.session = null
    },
    async close() {
      ws.close()
      proc.kill()
      await sleep(500)
      try { rmSync(profileDir, { recursive: true, force: true }) } catch { /* browser may hold files */ }
    },
  }
  return b
}

// Create a disposable STUDENT account through the admin API (Node side) and remove it again afterwards.
const jsonPost = (base, path, body, session) => fetch(`${base}/api${path}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json', Cookie: session.cookie, 'X-CSRF-Token': session.csrf },
  body: JSON.stringify(body) })
async function adminSession(base, email, password) {
  const res = await fetch(`${base}/api/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }) })
  if (!res.ok) throw new Error(`admin login failed (${res.status}) - set E2E_EMAIL / E2E_PASSWORD to an administrator of a disposable database`)
  return { cookie: res.headers.get('set-cookie').split(';')[0], csrf: (await res.json()).csrf_token }
}
export async function createStudentAccount(base, adminEmail, adminPassword, name = 'E2E Test Learner') {
  const session = await adminSession(base, adminEmail, adminPassword)
  const email = `e2e.${Date.now()}.${Math.floor(Math.random() * 1e4)}@example.edu`
  const password = 'Violet-Anchor-Meadow-17'
  const res = await jsonPost(base, '/admin/users', { name, email, age: 25, preferred_content: 'Videos', learning_style: 'Visual', password }, session)
  if (res.status !== 201) throw new Error(`could not create the test student (${res.status})`)
  return { email, password, studentId: (await res.json()).student_id }
}
/** Approve every pending enrolment request of a student (as the administrator, through the API). */
export async function approveRequests(base, adminEmail, adminPassword, studentId) {
  const session = await adminSession(base, adminEmail, adminPassword)
  const headers = { Cookie: session.cookie, 'X-CSRF-Token': session.csrf }
  const list = await (await fetch(`${base}/api/admin/enrollment-requests?status=pending&limit=100`, { headers })).json()
  let approved = 0
  for (const r of list.items.filter((x) => x.student_id === studentId)) {
    const res = await fetch(`${base}/api/admin/enrollment-requests/${r.id}/approve`, { method: 'POST', headers })
    if (res.ok) approved += 1
  }
  return approved
}
export async function removeStudent(base, adminEmail, adminPassword, studentId) {
  const session = await adminSession(base, adminEmail, adminPassword)
  const res = await fetch(`${base}/api/students/${studentId}`, { method: 'DELETE', headers: { Cookie: session.cookie, 'X-CSRF-Token': session.csrf } })
  return res.status
}

export function reporter() {
  const results = []
  return {
    step(name, ok, detail = '') {
      results.push({ name, ok })
      console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  (${detail})` : ''}`)
    },
    finish() {
      const failed = results.filter((r) => !r.ok).length
      console.log(`\n${results.length - failed}/${results.length} checks passed`)
      return failed ? 1 : 0
    },
  }
}
