import { useCallback, useMemo, useState } from 'react'
import { Clock, Database, Save, Trash2, UserPlus } from 'lucide-react'
import { api } from '../api/client'
import { useApi } from '../hooks/useApi'
import { useStudent } from '../context/StudentContext'
import { useToast } from '../context/ToastContext'
import PageHeader from '../components/ui/PageHeader'
import { Card } from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Modal from '../components/ui/Modal'
import { Select, TextInput } from '../components/ui/Form'
import { Notice } from '../components/ui/States'
import { Avatar } from '../components/layout/StudentSwitcher'
import StudentForm, { toPayload, validateStudent } from '../components/profile/StudentForm'
import { formatDate, formatMinutes } from '../utils/format'

function useSubmit(action) {
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const submit = async (values) => {
    const local = validateStudent(values)
    setErrors(local)
    if (Object.keys(local).length) return null
    setBusy(true)
    try {
      return await action(toPayload(values))
    } catch (e) {
      setErrors(e.code === 'email_taken' ? { email: e.message } : e.fieldErrors)
      throw e
    } finally {
      setBusy(false)
    }
  }
  return { errors, busy, submit, setErrors }
}

function LogStudyTime({ studentId, onLogged }) {
  const toast = useToast()
  const courses = useApi(() => api.enrollments.list(studentId, 'active'), [studentId])
  const today = new Date().toISOString().slice(0, 10)
  const [minutes, setMinutes] = useState(30)
  const [date, setDate] = useState(today)
  const [courseId, setCourseId] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    const m = Number(minutes)
    if (!(m > 0 && m <= 600)) return setError('Enter between 1 and 600 minutes')
    setBusy(true)
    setError(null)
    try {
      await api.students.logActivity(studentId, { minutes: m, activity_date: date, course_id: courseId ? Number(courseId) : null })
      toast.success('Study time logged', `${formatMinutes(m)} on ${formatDate(date)}`)
      onLogged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Log study time" subtitle="Self-study outside lessons and quizzes">
      <form onSubmit={submit} className="space-y-4">
        <TextInput label="Minutes" type="number" min={1} max={600} value={minutes} onChange={(e) => setMinutes(e.target.value)} error={error} />
        <TextInput label="Date" type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />
        <Select label="Course (optional)" value={courseId} onChange={(e) => setCourseId(e.target.value)} placeholder="General study"
                options={(courses.data || []).map((en) => ({ value: en.course.id, label: en.course.title }))} />
        <Button type="submit" icon={Clock} loading={busy} className="w-full">Log time</Button>
      </form>
    </Card>
  )
}

export default function Profile() {
  const { student, setStudent, setStudentId, refresh } = useStudent()
  const toast = useToast()
  const [values, setValues] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [createValues, setCreateValues] = useState(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const initial = useMemo(() => (student ? { ...student, learning_style: student.learning_style || '' } : null), [student])
  const blank = useMemo(() => ({}), [])
  const onEditChange = useCallback((v) => setValues(v), [])
  const onCreateChange = useCallback((v) => setCreateValues(v), [])

  const edit = useSubmit((payload) => api.students.update(student.id, payload))
  const create = useSubmit((payload) => api.students.create(payload))

  const save = async () => {
    try {
      const updated = await edit.submit(values)
      if (updated) {
        setStudent(updated)
        refresh()
        toast.success('Profile saved')
      }
    } catch (e) {
      toast.error('Could not save profile', e.message)
    }
  }

  const createStudent = async () => {
    try {
      const created = await create.submit(createValues)
      if (created) {
        setCreateOpen(false)
        setStudentId(created.id)
        toast.success('Student created', `Now viewing ${created.name}.`)
      }
    } catch (e) {
      toast.error('Could not create student', e.message)
    }
  }

  const remove = async () => {
    setDeleting(true)
    try {
      await api.students.remove(student.id)
      toast.success('Student deleted', `${student.name} and their history were removed.`)
      setDeleteOpen(false)
      setStudentId(null)
    } catch (e) {
      toast.error('Could not delete student', e.message)
    } finally {
      setDeleting(false)
    }
  }

  const createButton = <Button icon={UserPlus} variant="secondary" onClick={() => { create.setErrors({}); setCreateOpen(true) }}>New student</Button>

  const createModal = (
      <Modal open={createOpen} onClose={() => setCreateOpen(false)} title="Create a new student" size="lg"
             footer={<><Button variant="secondary" onClick={() => setCreateOpen(false)}>Cancel</Button>
               <Button icon={UserPlus} loading={create.busy} onClick={createStudent}>Create student</Button></>}>
        <StudentForm initial={blank} errors={create.errors} onChange={onCreateChange} disabled={create.busy} />
      </Modal>
  )

  if (!student) {
    return (
      <div>
        <PageHeader title="Profile" actions={createButton} />
        <Notice title="No student selected">Create a student to start using the app.</Notice>
        {createModal}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Student Profile" description="Your details and learning preferences." actions={createButton} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <div className="flex flex-wrap items-center gap-4">
              <Avatar name={student.name} size="lg" />
              <div className="min-w-0 flex-1">
                <h2 className="text-lg font-semibold text-ink">{student.name}</h2>
                <p className="text-sm text-ink-3">{student.email} · Student #{student.id} · joined {formatDate(student.created_at)}</p>
              </div>
              {student.is_synthetic && <Badge icon={Database} tone="warning">Synthetic history</Badge>}
            </div>
            {student.is_synthetic && (
              <p className="mt-4 text-xs text-ink-3">
                Profile values come from the original sample_data.csv; the enrolments, quizzes and activity before today were
                generated by the seeded sample-data generator. Anything you do now is stored for real.
              </p>
            )}
          </Card>

          <Card title="Edit profile" action={<Button icon={Save} loading={edit.busy} onClick={save}>Save changes</Button>}>
            <StudentForm initial={initial} errors={edit.errors} onChange={onEditChange} disabled={edit.busy} />
          </Card>

          <Card title="Danger zone">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-ink-2">Delete this student and all of their enrolments, quiz attempts and activity.</p>
              <Button variant="danger-outline" icon={Trash2} onClick={() => setDeleteOpen(true)}>Delete student</Button>
            </div>
          </Card>
        </div>
        <LogStudyTime studentId={student.id} onLogged={refresh} />
      </div>

      {createModal}
      <Modal open={deleteOpen} onClose={() => setDeleteOpen(false)} title="Delete student?"
             footer={<><Button variant="secondary" onClick={() => setDeleteOpen(false)}>Cancel</Button>
               <Button variant="danger" icon={Trash2} loading={deleting} onClick={remove}>Delete permanently</Button></>}>
        <p className="text-sm text-ink-2">This permanently deletes <strong className="text-ink">{student.name}</strong> and their entire learning history. This cannot be undone.</p>
      </Modal>
    </div>
  )
}
