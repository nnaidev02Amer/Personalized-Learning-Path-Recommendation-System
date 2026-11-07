import { useState } from 'react'
import { Check, Inbox, X } from 'lucide-react'
import { api } from '../../api/client'
import { useApi, useDebounced } from '../../hooks/useApi'
import { useToast } from '../../context/ToastContext'
import PageHeader from '../../components/ui/PageHeader'
import Tabs from '../../components/ui/Tabs'
import { Card } from '../../components/ui/Card'
import Badge from '../../components/ui/Badge'
import Button from '../../components/ui/Button'
import Modal from '../../components/ui/Modal'
import { Textarea } from '../../components/ui/Form'
import { EmptyState, ErrorState, Skeleton } from '../../components/ui/States'
import { formatDate } from '../../utils/format'

const TONE = { pending: 'warning', approved: 'good', rejected: 'critical', cancelled: 'neutral' }
const LABEL = { pending: 'Pending', approved: 'Approved', rejected: 'Rejected', cancelled: 'Withdrawn' }

export default function AdminRequests() {
  const toast = useToast()
  const [status, setStatus] = useState('pending')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(null)
  const [rejecting, setRejecting] = useState(null)
  const [note, setNote] = useState('')
  const q = useDebounced(search)
  const overview = useApi(() => api.admin.overview(), [])
  const list = useApi(() => api.admin.requests({ status: status === 'all' ? undefined : status, search: q, limit: 100 }),
    [status, q])
  const counts = overview.data?.requests

  const refresh = () => { list.reload(); overview.reload() }

  const approve = async (r) => {
    setBusy(r.id)
    try {
      await api.admin.approveRequest(r.id)
      toast.success('Approved', `${r.student_name} can now study ${r.course.title}.`)
      refresh()
    } catch (e) {
      toast.error('Could not approve', e.message)
      refresh()
    } finally {
      setBusy(null)
    }
  }

  const reject = async () => {
    setBusy(rejecting.id)
    try {
      await api.admin.rejectRequest(rejecting.id, note)
      toast.success('Rejected', `${rejecting.student_name}'s request for ${rejecting.course.title} was declined.`)
      setRejecting(null)
      setNote('')
      refresh()
    } catch (e) {
      toast.error('Could not reject', e.message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div>
      <PageHeader title="Enrollment requests" description="Students ask to join courses; approve or reject each request." />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs label="Request status" value={status} onChange={setStatus}
              tabs={[{ value: 'pending', label: 'Pending', count: counts?.pending ?? null },
                { value: 'approved', label: 'Approved', count: counts?.approved ?? null },
                { value: 'rejected', label: 'Rejected', count: counts?.rejected ?? null },
                { value: 'all', label: 'All' }]} />
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search student or course…"
               aria-label="Search requests"
               className="h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-3 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/25 sm:w-72" />
      </div>

      <div className="mt-6">
        {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
        {list.loading && !list.data && <Skeleton className="h-40 rounded-2xl" />}
        {list.data && list.data.items.length === 0 && (
          <Card><EmptyState icon={Inbox} title="No requests here"
                            message={status === 'pending' ? 'Nothing is waiting for a decision.' : 'No requests match.'} /></Card>
        )}
        {list.data && list.data.items.length > 0 && (
          <Card bodyClassName="divide-y divide-line p-0">
            {list.data.items.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-sm">
                <div className="min-w-0">
                  <p className="font-medium text-ink">{r.student_name}
                    <span className="ml-2 text-xs font-normal text-ink-3">{r.student_email}</span></p>
                  <p className="text-ink-2">{r.course.code} · {r.course.title}</p>
                  <p className="text-xs text-ink-3">Requested {formatDate(r.requested_at)}
                    {r.decided_at ? ` · decided ${formatDate(r.decided_at)}` : ''}{r.note ? ` · “${r.note}”` : ''}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={TONE[r.status]}>{LABEL[r.status]}</Badge>
                  {r.status === 'pending' && (
                    <>
                      <Button size="sm" icon={Check} loading={busy === r.id} onClick={() => approve(r)}>Approve</Button>
                      <Button size="sm" variant="secondary" icon={X} disabled={busy === r.id} onClick={() => setRejecting(r)}>Reject</Button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </Card>
        )}
      </div>

      <Modal open={Boolean(rejecting)} onClose={() => setRejecting(null)} title="Reject request"
             footer={<><Button variant="secondary" onClick={() => setRejecting(null)}>Cancel</Button>
               <Button icon={X} loading={Boolean(rejecting) && busy === rejecting.id} onClick={reject}>Reject request</Button></>}>
        {rejecting && (
          <div className="space-y-3">
            <p className="text-sm text-ink-2">{rejecting.student_name} · {rejecting.course.code} {rejecting.course.title}</p>
            <Textarea label="Reason (optional, shown to the student)" rows={3} maxLength={500} value={note}
                      onChange={(e) => setNote(e.target.value)} />
          </div>
        )}
      </Modal>
    </div>
  )
}
