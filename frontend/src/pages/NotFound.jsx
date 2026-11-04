import { Compass } from 'lucide-react'
import Button from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/States'

export default function NotFound() {
  return (
    <Card>
      <EmptyState icon={Compass} title="Page not found" message="The page you are looking for does not exist."
                  action={<Button to="/">Back to dashboard</Button>} />
    </Card>
  )
}
