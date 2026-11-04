import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { useApi } from '../../hooks/useApi'
import { Select, TextInput } from '../ui/Form'

const EMPTY = { name: '', email: '', age: '', learning_style: '', preferred_content: 'Videos', daily_goal_minutes: 60 }

/** Client-side checks mirror the API's validation; the API remains the source of truth. */
export function validateStudent(v) {
  const errors = {}
  if (!v.name.trim()) errors.name = 'Name is required'
  if (!/^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(v.email.trim())) errors.email = 'Enter a valid email address'
  const age = Number(v.age)
  if (!Number.isInteger(age) || age < 10 || age > 100) errors.age = 'Age must be a whole number from 10 to 100'
  const goal = Number(v.daily_goal_minutes)
  if (!(goal > 0 && goal <= 1440)) errors.daily_goal_minutes = 'Daily goal must be between 1 and 1440 minutes'
  return errors
}

export function toPayload(v) {
  return {
    name: v.name.trim(),
    email: v.email.trim(),
    age: Number(v.age),
    learning_style: v.learning_style || null,
    preferred_content: v.preferred_content,
    daily_goal_minutes: Number(v.daily_goal_minutes),
  }
}

export default function StudentForm({ initial, errors, onChange, disabled }) {
  const meta = useApi(() => api.meta(), [])
  const [values, setValues] = useState({ ...EMPTY, ...initial })

  useEffect(() => { setValues({ ...EMPTY, ...initial }) }, [initial])
  useEffect(() => { onChange(values) }, [values, onChange])

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e.target.value }))
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <TextInput label="Full name" value={values.name} onChange={set('name')} error={errors.name} disabled={disabled} autoComplete="name" />
      <TextInput label="Email" type="email" value={values.email} onChange={set('email')} error={errors.email} disabled={disabled} autoComplete="email" />
      <TextInput label="Age" type="number" min={10} max={100} value={values.age} onChange={set('age')} error={errors.age} disabled={disabled} />
      <TextInput label="Daily study goal (minutes)" type="number" min={1} max={1440} value={values.daily_goal_minutes}
                 onChange={set('daily_goal_minutes')} error={errors.daily_goal_minutes} disabled={disabled} />
      <Select label="Learning style" value={values.learning_style || ''} onChange={set('learning_style')} placeholder="Not set"
              options={meta.data?.learning_styles || []} error={errors.learning_style} disabled={disabled}
              hint="Self-reported. An ML-predicted style is added in Phase 5." />
      <Select label="Preferred content format" value={values.preferred_content} onChange={set('preferred_content')}
              options={meta.data?.content_types || ['Videos']} error={errors.preferred_content} disabled={disabled} />
    </div>
  )
}
