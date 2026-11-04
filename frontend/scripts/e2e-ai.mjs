// AI/ML integration test through the real UI (Phase 6), plus UI states and responsiveness.
//
//   npm run e2e:ai                                   # against http://127.0.0.1:5173
//   $env:E2E_SCREENSHOTS="C:\tmp\shots"; npm run e2e:ai   # also save responsive screenshots
//   $env:E2E_OFFLINE="1"; npm run e2e:ai             # frontend running WITHOUT a reachable backend
//
// Creates its own student (never touches seeded students) and deletes it at the end.

import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { DIALOG, launch, reporter, sleep, text } from './lib/browser.mjs'

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
  await goto('/')
  step('Offline: app explains the backend is not reachable', await waitFor(text('Backend not reachable'), 15000))
  step('Offline: top bar shows API offline', await waitFor(text('API offline'), 15000))
  step('Offline: start command is shown to the user', await waitFor(text('uvicorn backend.app.main:app'), 5000))
}

async function online() {
  const health = await api('/health').catch(() => null)
  step('Backend reachable', health?.status === 'ok')
  if (!health) throw new Error('Backend not reachable - start it first (or set E2E_OFFLINE=1)')

  const email = `ai.e2e.${Date.now()}@example.edu`
  const student = await api('/students', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'AI Flow Tester', email, age: 27, preferred_content: 'Videos', learning_style: 'Visual' }) })
  const sid = student.id
  try {
    await goto('/')
    await evaluate(`localStorage.setItem('currentStudentId', '${sid}')`)
    await goto('/learning')
    step('Viewing the new test student', await waitFor(`document.querySelector('[aria-haspopup=listbox]')?.innerText.includes('Student #${sid}')`))

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
      await click(tab)
      step(`Method tab "${tab}" loads its ranking`, await waitFor(`${text(phrase)} && document.querySelector('main ol li')`, 15000))
    }

    // ---- enrol in PY101 through the catalog UI
    const obsBefore = await beginnerObservations()
    await goto('/courses')
    await waitFor(text('Python Fundamentals'))
    await click('Python Fundamentals')
    await waitFor(text('Lessons (5)'))
    await click('Enroll', DIALOG)
    step('Enrolled in Python Fundamentals via the UI', await waitFor(text('You are now enrolled in Python Fundamentals')))

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
    await goto('/')
    step('Dashboard "Recommended for you" lists model recommendations',
      await waitFor(`${text('Recommended for you')} && [...document.querySelectorAll('main ol')].some((ol) => ol.children.length >= 1)`, 20000))
    await goto('/roadmap')
    step('Roadmap next steps are ML-ranked', await waitFor(text('ML ranked'), 20000))

    // ---- model evaluation: protocol switch + retrain includes the new real student
    await goto('/models')
    await waitFor(text('candidates on average'), 20000)
    const candBefore = (await bodyText()).match(/([\d.]+) candidates on average/)?.[1]
    await click('All untaken courses')
    await sleep(300)
    const candAfter = (await bodyText()).match(/([\d.]+) candidates on average/)?.[1]
    step('Evaluation protocol tab switches the table', candBefore && candAfter && candBefore !== candAfter, `${candBefore} -> ${candAfter}`)
    await click('Retrain on current data')
    step('Retrain button retrains the models', await waitFor(text('Models retrained'), 60000))
    const real = Number((await bodyText()).match(/(\d+) of \d+ students were created in this app/)?.[1] ?? 0)
    step('Retrained models count real (app-created) students', real >= 1, `${real} real`)

    // ---- loading state under a slow network
    await b.send('Network.emulateNetworkConditions', { offline: false, latency: 1500, downloadThroughput: -1, uploadThroughput: -1 })
    await b.send('Page.navigate', { url: `${BASE}/analytics` })
    step('Loading skeleton is shown while data loads', await waitFor('document.querySelector(".skeleton")', 8000))
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
    await api(`/students/${sid}`, { method: 'DELETE' }).catch(() => {})
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
