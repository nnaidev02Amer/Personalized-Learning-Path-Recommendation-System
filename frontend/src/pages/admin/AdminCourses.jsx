import { useState } from 'react'
import { Eye, EyeOff, Lock, LockOpen, Plus, Search, Trash2 } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useToast } from '../../context/ToastContext'
import PageHeader from '../../components/ui/PageHeader'
import { Card } from '../../components/ui/Card'
import Badge, { DIFFICULTY_TONE } from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import { Select, TextInput, Textarea } from '../../components/ui/Form'
import { EmptyState, ErrorState, Notice, Skeleton } from '../../components/ui/States'

const BLANK = {
  code: '', title: '', description: '', topic: '', difficulty: 'Beginner', content_format: 'Videos', duration_hours: 4,
  skills: '', lessons: '', quizTitle: '', quizQuestions: '', access: 'open',
}

/** "Title | minutes" per line. */
function parseLessons(text) {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).map((line) => {
    const [title, minutes] = line.split('|').map((p) => p.trim())
    return { title, duration_min: Number(minutes) }
  })
}

/** "Question | option | option | ... | number of the correct option | skill" per line. */
function parseQuestions(text) {
  return text.split('\n').map((l) => l.trim()).filter(Boolean).map((line) => {
    const parts = line.split('|').map((p) => p.trim())
    const skill = parts.pop()
    const correct = Number(parts.pop()) - 1
    const [prompt, ...options] = parts
    return { prompt, options, correct_option: correct, skill }
  })
}

function CreateCourseModal({ open, onClose, onCreated }) {
  const toast = useToast()
  const meta = useApi(() => api.meta(), [])
  const [v, setV] = useState(BLANK)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setV((x) => ({ ...x, [k]: e.target.value }))

  const submit = async () => {
    setError(null)
    const lessons = parseLessons(v.lessons)
    if (!v.code.trim() || !v.title.trim() || !v.description.trim() || !v.topic.trim()) return setError('Code, title, topic and description are required.')
    if (!lessons.length || lessons.some((l) => !l.title || !(l.duration_min > 0))) return setError('Add at least one lesson per line as "Title | minutes".')
    const payload = {
      code: v.code.trim(), title: v.title.trim(), description: v.description.trim(), topic: v.topic.trim(),
      difficulty: v.difficulty, content_format: v.content_format, duration_hours: Number(v.duration_hours),
      skills: v.skills.split(',').map((s) => s.trim()).filter(Boolean), lessons, is_locked: v.access === 'locked',
    }
    if (v.quizQuestions.trim()) {
      const questions = parseQuestions(v.quizQuestions)
      const bad = questions.find((q) => !q.prompt || q.options.length < 2 || !(q.correct_option >= 0 && q.correct_option < q.options.length) || !q.skill)
      if (bad) return setError('Each question: "Question | option 1 | option 2 | … | number of the correct option | skill".')
      payload.quiz = { title: v.quizTitle.trim() || `${v.title.trim()} quiz`, questions }
    }
    setBusy(true)
    try {
      const created = await api.courses.create(payload)
      toast.success('Course created', `${created.code} is now in the catalogue.`)
      setV(BLANK)
      onCreated()
    } catch (e) {
      setError(e.code === 'course_code_taken' ? e.message : Object.values(e.fieldErrors || {})[0] || e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="New course" size="lg"
           footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button>
             <Button icon={Plus} loading={busy} onClick={submit}>Create course</Button></>}>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextInput label="Code" value={v.code} onChange={set('code')} placeholder="PY301" />
        <TextInput label="Title" value={v.title} onChange={set('title')} />
        <TextInput label="Topic" value={v.topic} onChange={set('topic')} list="topics" />
        <datalist id="topics">{(meta.data?.topics || []).map((t) => <option key={t} value={t} />)}</datalist>
        <TextInput label="Duration (hours)" type="number" min={1} value={v.duration_hours} onChange={set('duration_hours')} />
        <Select label="Difficulty" value={v.difficulty} onChange={set('difficulty')} options={meta.data?.difficulties || ['Beginner']} />
        <Select label="Format" value={v.content_format} onChange={set('content_format')} options={meta.data?.content_types || ['Videos']} />
        <Select label="Access" value={v.access} onChange={set('access')}
                options={[{ value: 'open', label: 'Open (students enrol directly)' }, { value: 'locked', label: 'Locked (admin approval needed)' }]} />
        <div className="sm:col-span-2"><TextInput label="Skills (comma separated)" value={v.skills} onChange={set('skills')} placeholder="loops, functions" /></div>
        <div className="sm:col-span-2"><Textarea label="Description" rows={3} value={v.description} onChange={set('description')} /></div>
        <div className="sm:col-span-2"><Textarea label="Lessons — one per line: Title | minutes" rows={4} value={v.lessons} onChange={set('lessons')}
          placeholder={'Introduction | 15\nCore ideas | 25'} /></div>
        <div className="sm:col-span-2"><TextInput label="Quiz title (optional)" value={v.quizTitle} onChange={set('quizTitle')} /></div>
        <div className="sm:col-span-2"><Textarea label="Quiz questions (optional) — Question | option 1 | option 2 | … | correct option number | skill"
          rows={4} value={v.quizQuestions} onChange={set('quizQuestions')} placeholder="What is 2+2? | 3 | 4 | 5 | 2 | arithmetic" /></div>
      </div>
      {error && <p role="alert" className="mt-4 rounded-lg bg-critical-soft px-3 py-2 text-sm text-critical">{error}</p>}
    </Modal>
  )
}

export default function AdminCourses() {
  const toast = useToast()
  const [query, setQuery] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteFor, setDeleteFor] = useState(null)
  const search = useDebounced(query)
  const list = useApi(() => api.courses.list({ search, include_archived: true }), [search])

  const setLocked = async (course, locked) => {
    try {
      await api.courses.update(course.id, { is_locked: locked })
      toast.success(locked ? 'Course locked' : 'Course unlocked',
        locked ? `${course.code} now needs your approval.` : `${course.code} can be joined directly by students.`)
      list.reload()
    } catch (e) {
      toast.error('Action failed', e.message)
    }
  }
  const setActive = async (course, active) => {
    try {
      await api.courses.update(course.id, { is_active: active })
      toast.success(active ? 'Course visible' : 'Course hidden',
        active ? `${course.code} is back in the student catalogue.` : `${course.code} is hidden from the student catalogue; existing enrolments are kept.`)
      list.reload()
    } catch (e) {
      toast.error('Action failed', e.message)
    }
  }
  const remove = async () => {
    try {
      await api.courses.remove(deleteFor.id)
      toast.success('Course deleted', deleteFor.code)
      setDeleteFor(null)
      list.reload()
    } catch (e) {
      toast.error('Could not delete', e.code === 'course_in_use' ? 'This course has enrolments or attempts — hide it instead.' : e.message)
      setDeleteFor(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Courses" description="Create and manage the course catalogue."
                  actions={<Button icon={Plus} onClick={() => setCreateOpen(true)}>New course</Button>} />
      <Notice title="Models and new courses">The recommendation models are trained on the courses that existed at training time.
        A course you add here can be enrolled in immediately, but is only recommended after the models are retrained (Model Evaluation page).</Notice>
      <Card>
        <label className="mb-4 flex items-center gap-2 rounded-lg border border-line px-2.5">
          <Search className="size-4 text-ink-3" aria-hidden />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search courses…" aria-label="Search courses"
                 className="h-9 w-full bg-transparent text-sm text-ink outline-none placeholder:text-ink-3" />
        </label>
        {list.error ? <ErrorState compact error={list.error} onRetry={list.reload} /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-ink-3">
                <tr><th className="py-2 pr-3">Course</th><th className="px-3">Level</th><th className="px-3">Lessons</th>
                  <th className="px-3">Enrolled</th><th className="px-3">Status</th><th className="pl-3 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {list.loading && !list.data && Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td colSpan={6} className="py-3"><Skeleton className="h-6 w-full" /></td></tr>))}
                {list.data?.items.map((c) => (
                  <tr key={c.id} className={c.is_active ? '' : 'opacity-70'}>
                    <td className="py-2.5 pr-3"><p className="font-medium text-ink">{c.title}</p>
                      <p className="text-xs text-ink-3">{c.code} · {c.topic} · {c.content_format}</p></td>
                    <td className="px-3"><Badge tone={DIFFICULTY_TONE[c.difficulty]}>{c.difficulty}</Badge></td>
                    <td className="px-3 tabular-nums text-ink-2">{c.lesson_count}</td>
                    <td className="px-3 tabular-nums text-ink-2">{c.enrolled_count}</td>
                    <td className="px-3"><div className="flex flex-wrap gap-1">
                      {c.is_active ? <Badge tone="good">visible</Badge> : <Badge>hidden</Badge>}
                      {c.is_locked ? <Badge tone="warning" icon={Lock}>locked</Badge> : <Badge tone="brand" icon={LockOpen}>open</Badge>}
                    </div></td>
                    <td className="pl-3">
                      <div className="flex justify-end gap-1.5">
                        {c.is_locked
                          ? <Button size="sm" variant="secondary" icon={LockOpen} onClick={() => setLocked(c, false)}>Unlock</Button>
                          : <Button size="sm" variant="secondary" icon={Lock} onClick={() => setLocked(c, true)}>Lock</Button>}
                        {c.is_active
                          ? <Button size="sm" variant="secondary" icon={EyeOff} onClick={() => setActive(c, false)}>Hide</Button>
                          : <Button size="sm" variant="secondary" icon={Eye} onClick={() => setActive(c, true)}>Unhide</Button>}
                        <Button size="sm" variant="danger-outline" icon={Trash2} onClick={() => setDeleteFor(c)} aria-label={`Delete ${c.code}`}>Delete</Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {list.data?.items.length === 0 && <tr><td colSpan={6}><EmptyState title="No courses match" /></td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <CreateCourseModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => { setCreateOpen(false); list.reload() }} />
      <Modal open={Boolean(deleteFor)} onClose={() => setDeleteFor(null)} title={deleteFor?.enrolled_count ? 'This course is in use' : 'Delete course?'}
             footer={deleteFor?.enrolled_count
               ? <><Button variant="secondary" onClick={() => setDeleteFor(null)}>Close</Button>
                 {deleteFor.is_active && <Button icon={EyeOff} onClick={() => { setActive(deleteFor, false); setDeleteFor(null) }}>Hide it instead</Button>}</>
               : <><Button variant="secondary" onClick={() => setDeleteFor(null)}>Cancel</Button>
                 <Button variant="danger" icon={Trash2} onClick={remove}>Delete</Button></>}>
        {deleteFor?.enrolled_count ? (
          <p className="text-sm text-ink-2"><strong className="text-ink">{deleteFor.title}</strong> has {deleteFor.enrolled_count} enrolled student(s).
            Deleting it would erase their progress and quiz history, so it is protected. Hide it to remove it from the student catalogue
            while keeping everyone's progress.</p>
        ) : (
          <p className="text-sm text-ink-2">Delete <strong className="text-ink">{deleteFor?.title}</strong> permanently? Nobody has used it, so no student data is affected.</p>
        )}
      </Modal>
    </div>
  )
}
