// AI/ML integration test through the real UI (Phase 6), plus UI states and responsiveness.
//
//   npm run e2e:ai                                   # against http://127.0.0.1:5173
//   $env:E2E_SCREENSHOTS="C:\tmp\shots"; npm run e2e:ai   # also save responsive screenshots
//   $env:E2E_OFFLINE="1"; npm run e2e:ai             # frontend running WITHOUT a reachable backend
//
// Creates its own student (never touches seeded students) and deletes it at the end.

import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { DIALOG, approveRequests, createStudentAccount, launch, removeStudent, reporter, sleep, text } from './lib/browser.mjs'

const BASE = (process.env.E2E_URL || 'http://127.0.0.1:5173').replace(/\/$/, '')
const SHOTS = process.env.E2E_SCREENSHOTS
const { step, finish } = reporter()
const b = await launch({ base: BASE })
const { goto, click, waitFor, evaluate, api } = b

const bodyText = () => evaluate('document.body.innerText')
// Top-level recommendation items only (each card also contains a nested <ul> of reasons).
const recList = () => evaluate(`[...(document.querySelector('main ol')?.querySelectorAll(':scope > li') || [])]
  .map((li) => ({ title: li.querySelector('span.font-medium')?.textContent || '', text: li.innerText }))`)
const beginnerObservations = async () => Number((await bodyText()).match(/learned from (\d+) attempts/)?.[1] ?? -1)

async function offline() {
  await goto('/login')
  step('Offline: app explains the backend is not reachable', await waitFor(text('Backend not reachable'), 15000))
  step('Offline: start command is shown to the user', await waitFor(text('uvicorn backend.app.main:app'), 5000))
}

async function online() {
  const health = await api('/health').catch(() => null)
  step('Backend reachable', health?.status === 'ok')
  if (!health) throw new Error('Backend not reachable - start it first (or set E2E_OFFLINE=1)')
  if (!process.env.E2E_EMAIL || !process.env.E2E_PASSWORD) throw new Error('Set E2E_EMAIL and E2E_PASSWORD (an administrator of a disposable database)')
  const { E2E_EMAIL, E2E_PASSWORD } = process.env
  const account = await createStudentAccount(BASE, E2E_EMAIL, E2E_PASSWORD, 'AI Flow Tester')
  const sid = account.studentId
  try {
    await b.login(account.email, account.password)
    const viewing = (await api('/auth/me')).user.student_id === sid
    step('Signed in as the new test student', viewing)
    if (!viewing) throw new Error('Not signed in as the test student; aborting before any changes')
    await goto('/learning')

    // ---- empty states for a brand-new student
    step('Empty state: My Learning has no active courses', await waitFor(text('No active courses')))
    await goto('/analytics')
    step('Empty state: analytics has no quiz attempts', await waitFor(`${text('No quiz attempts yet')} && ${text('No activity in this period')}`))

    // ---- cold-start AI outputs
    await goto('/recommendations')
    await waitFor(`document.querySelector('main ol li')`, 30000)
    const cold = await recList()
    step('Cold start: recommends only Beginner courses', cold.length > 0 && cold.every((r) => r.text.includes('Beginner')), `${cold.length} items`)
    step('Cold start: skills and predictions show empty states',
      await waitFor(`${text('No skills assessed yet')} && ${text('Nothing to predict yet')}`, 15000))
    step('Learning-style card warns that the model is not reliable (data-driven)',
      await waitFor(`${text('Model prediction')} && (${text('does not beat the majority-class baseline')} || ${text('Cross-validated accuracy')})`))

    // ---- switching recommendation methods re-queries the API
    for (const [tab, phrase] of [['Collaborative', 'Item-to-item similarity'], ['Content-based', 'your topic interests'],
      ['Popular (baseline)', 'the baseline the models are compared with'], ['Hybrid', 'Blend of collaborative']]) {
      // Click the tab itself: recommendation cards also contain words like "Collaborative" in their score text.
      await b.evaluate(`[...document.querySelectorAll('[role=tab]')].find((t) => t.innerText.trim() === ${JSON.stringify(tab)})?.click()`)
      step(`Method tab "${tab}" loads its ranking`, await waitFor(`${text(phrase)} && document.querySelector('main ol li')`, 15000))
    }

    // ---- enrol in PY101 through the catalog UI
    const obsBefore = await beginnerObservations()
    await goto('/courses')
    await waitFor(text('Python Fundamentals'))
    await click('Python Fundamentals')
    await waitFor(text('Lessons (5)'))
    await click('Request access', DIALOG)
    step('Requested Python Fundamentals via the UI', await waitFor(text('Request sent')))
    step('Administrator approves the request', (await approveRequests(BASE, E2E_EMAIL, E2E_PASSWORD, account.studentId)) === 1)

    await goto('/recommendations')
    step('After enrolling: prediction appears for the new course',
      await waitFor(`${text('Python Fundamentals')} && ${text('0 previous attempts')}`, 20000))
    await waitFor(`document.querySelector('main ol li')`, 15000)
    step('After enrolling: the course is no longer recommended', !(await recList()).some((r) => r.title === 'Python Fundamentals'))

    // ---- complete lessons and take the quiz in the UI (one wrong answer -> 75%)
    await goto('/learning')
    await waitFor(text('Complete next lesson'))
    for (let i = 0; i < 5; i++) {
      await click('Complete next lesson')
      await waitFor(`!document.querySelector('button[disabled] .animate-spin')`, 5000)
      await sleep(400)
    }
    await waitFor(text('Course completed!'), 8000)
    const course = (await api(`/students/${sid}/enrollments`))[0].course
    const quizId = (await api(`/courses/${course.id}`)).quizzes[0].id
    await goto(`/quiz/${quizId}`)
    await waitFor(text('Submit answers'))
    for (const [q, option] of [[0, 1], [1, 2], [2, 1], [3, 0]]) {
      await evaluate(`document.querySelectorAll('fieldset')[${q}].querySelectorAll('input[type=radio]')[${option}].click()`)
    }
    await click('Submit answers')
    step('Quiz graded 75% in the UI', await waitFor(text('3 of 4 correct'), 8000))

    // ---- AI outputs reflect the new data
    await goto('/recommendations')
    step('After quiz: BKT skill mastery is shown for Python skills',
      await waitFor(`${text('Python Programming (')} && ${text('answers,')}`, 20000))
    step('After quiz: prediction counts the attempt', await waitFor(text('1 previous attempt'), 15000))
    await waitFor(text('learned from'), 15000)
    const obsAfter = await beginnerObservations()
    step('After quiz: the bandit learned online (Beginner observations +1)', obsAfter === obsBefore + 1, `${obsBefore} -> ${obsAfter}`)
    const apiRecs = (await api(`/students/${sid}/recommendations?limit=20`)).items.map((i) => i.code)
    step('After quiz: PY102 unlocked and recommended, PY101 excluded', apiRecs.includes('PY102') && !apiRecs.includes('PY101'))

    // ---- assistant grounded on the same outputs
    await click('Which skills are weak?')
    step('Assistant answers the skills question', await waitFor(`${text('Skills to strengthen')} || ${text('All skills assessed so far')} || ${text('Answered by')}`, 30000))
    await click('What score will I get?')
    step('Assistant answers with the predicted score', await waitFor(`${text('Predicted quiz scores')} || document.body.innerText.split('Answered by').length > 2`, 30000))

    // ---- dashboard + roadmap use model outputs
    await goto('/dashboard')
    step('Dashboard "Recommended for you" lists model recommendations',
      await waitFor(`${text('Recommended for you')} && [...document.querySelectorAll('main ol')].some((ol) => ol.children.length >= 1)`, 20000))
    await goto('/roadmap')
    step('Roadmap next steps are ML-ranked', await waitFor(text('ML ranked'), 20000))

    // ---- model evaluation (administrator only): sign out and in as the administrator, then back
    await b.logout()
    await b.login(E2E_EMAIL, E2E_PASSWORD)
    await goto('/models')
    await waitFor(text('candidates on average'), 20000)
    const candBefore = (await bodyText()).match(/([\d.]+) candidates on average/)?.[1]
    await click('All untaken courses')
    await sleep(300)
    const candAfter = (await bodyText()).match(/([\d.]+) candidates on average/)?.[1]
    step('Evaluation protocol tab switches the table', candBefore && candAfter && candBefore !== candAfter, `${candBefore} -> ${candAfter}`)
    await click('Retrain on current data')
    step('Retrain button retrains the models', await waitFor(text('Models retrained'), Number(process.env.E2E_RETRAIN_TIMEOUT_MS) || 60000))
    const real = Number((await bodyText()).match(/(\d+) of \d+ students were created in this app/)?.[1] ?? 0)
    step('Retrained models count real (app-created) students', real >= 1, `${real} real`)

    await b.logout()
    await b.login(account.email, account.password)

    // ---- loading state under a slow network
    await b.send('Network.emulateNetworkConditions', { offline: false, latency: 1500, downloadThroughput: -1, uploadThroughput: -1 })
    await b.send('Page.navigate', { url: `${BASE}/analytics` })
    step('Loading skeleton is shown while data loads', await waitFor('document.querySelector(".skeleton")', 25000))
    await b.send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 })
    await waitFor(text('Progress & Analytics'), 15000)

    // ---- error states
    await goto('/quiz/999999')
    step('Error state: unknown quiz shows the API message', await waitFor(text('Quiz 999999 not found'), 10000))
    await goto('/no-such-page')
    step('Error state: unknown route shows 404 page', await waitFor(text('Page not found')))

    // ---- responsive layout (no horizontal overflow) at phone / tablet / desktop
    if (SHOTS) mkdirSync(SHOTS, { recursive: true })
    const pages = ['/', '/learning', '/courses', '/roadmap', '/recommendations', '/analytics', '/models', '/profile']
    for (const width of [375, 768, 1280]) {
      await b.setViewport(width)
      const overflowing = []
      for (const path of pages) {
        await goto(path)
        await waitFor('!document.querySelector(".skeleton")', 20000)
        await sleep(300)
        const over = await evaluate('document.documentElement.scrollWidth - window.innerWidth')
        if (over > 1) overflowing.push(`${path} (+${over}px)`)
        if (SHOTS && ['/', '/recommendations', '/models'].includes(path)) {
          await b.screenshot(join(SHOTS, `w${width}${path.replace(/\//g, '_') || '_home'}.png`))
        }
      }
      step(`No horizontal overflow at ${width}px on ${pages.length} pages`, overflowing.length === 0, overflowing.join(', '))
      // offsetParent is always null for position:fixed elements, so use the computed display.
      const nav = await evaluate(`['[aria-label="Open menu"]', 'aside'].map((sel) => {
        const el = document.querySelector(sel)
        return !!el && getComputedStyle(el).display !== 'none'
      })`)
      step(`Navigation adapts at ${width}px`, width < 1024 ? nav[0] && !nav[1] : !nav[0] && nav[1])
    }
    await b.send('Emulation.clearDeviceMetricsOverride')
  } finally {
    await removeStudent(BASE, process.env.E2E_EMAIL, process.env.E2E_PASSWORD, sid).catch(() => {})
  }
}

try {
  if (process.env.E2E_OFFLINE) await offline()
  else await online()
} catch (e) {
  step(`Unexpected error: ${e.message}`, false)
} finally {
  const errors = b.consoleErrors.filter((m) => !(process.env.E2E_OFFLINE && /Failed to load resource|50[0-9]/.test(m)))
  step('No uncaught errors in the browser console', errors.length === 0, errors.slice(0, 3).join(' | '))
  await b.close()
  process.exit(finish())
}
