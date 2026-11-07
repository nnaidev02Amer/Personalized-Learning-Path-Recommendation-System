import {
  BarChart3, BookOpen, FlaskConical, LayoutDashboard, Library, Map, Settings2, Sparkles, UserRound, Users,
  UserCog, Inbox,
} from 'lucide-react'

/** Pages a student sees. Administrators never see these. */
export const STUDENT_NAV = [
  { to: '/', label: 'Student Dashboard', icon: LayoutDashboard, end: true },
  { to: '/learning', label: 'My Learning', icon: BookOpen },
  { to: '/courses', label: 'Course Catalog', icon: Library },
  { to: '/roadmap', label: 'Learning Roadmap', icon: Map },
  { to: '/recommendations', label: 'AI Recommendations', icon: Sparkles },
  { to: '/analytics', label: 'Progress & Analytics', icon: BarChart3 },
  { to: '/profile', label: 'Profile', icon: UserRound },
]

export const ADMIN_NAV = [
  { to: '/', label: 'Admin dashboard', icon: LayoutDashboard, end: true },
  { to: '/admin/requests', label: 'Enrollment requests', icon: Inbox },
  { to: '/admin/students', label: 'Students', icon: Users },
  { to: '/admin/courses', label: 'Courses', icon: Settings2 },
  { to: '/admin/accounts', label: 'Accounts', icon: UserCog },
  { to: '/models', label: 'Model Evaluation', icon: FlaskConical },
]

