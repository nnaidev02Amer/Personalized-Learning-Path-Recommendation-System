import { useId } from 'react'

const control = `w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-3
  focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25 disabled:opacity-60`

export function Field({ label, error, hint, children, id }) {
  return (
    <div>
      {label && <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink-2">{label}</label>}
      {children}
      {error ? <p className="mt-1 text-xs text-critical" role="alert">{error}</p>
        : hint && <p className="mt-1 text-xs text-ink-3">{hint}</p>}
    </div>
  )
}

export function TextInput({ label, error, hint, className = '', ...props }) {
  const id = useId()
  return (
    <Field label={label} error={error} hint={hint} id={id}>
      <input id={id} aria-invalid={Boolean(error)} className={`${control} h-10 ${error ? 'border-critical' : ''} ${className}`} {...props} />
    </Field>
  )
}

export function Select({ label, error, hint, options, placeholder, className = '', ...props }) {
  const id = useId()
  return (
    <Field label={label} error={error} hint={hint} id={id}>
      <select id={id} aria-invalid={Boolean(error)} className={`${control} h-10 pr-8 ${error ? 'border-critical' : ''} ${className}`} {...props}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => {
          const { value, label: text } = typeof o === 'object' ? o : { value: o, label: o }
          return <option key={value} value={value}>{text}</option>
        })}
      </select>
    </Field>
  )
}

export function Textarea({ label, error, hint, className = '', rows = 4, ...props }) {
  const id = useId()
  return (
    <Field label={label} error={error} hint={hint} id={id}>
      <textarea id={id} rows={rows} aria-invalid={Boolean(error)}
                className={`${control} py-2 ${error ? 'border-critical' : ''} ${className}`} {...props} />
    </Field>
  )
}
