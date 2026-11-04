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
    api: (path, init) => fetch(`${base}/api${path}`, init).then((r) => (r.status === 204 ? null : r.json())),
    async close() {
      ws.close()
      proc.kill()
      await sleep(500)
      try { rmSync(profileDir, { recursive: true, force: true }) } catch { /* browser may hold files */ }
    },
  }
  return b
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
