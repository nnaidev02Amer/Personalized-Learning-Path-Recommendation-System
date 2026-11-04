import { BarChart3, BookOpen, LayoutDashboard, Library, Map, Sparkles, UserRound } from 'lucide-react'

export const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/learning', label: 'My Learning', icon: BookOpen },
  { to: '/courses', label: 'Course Catalog', icon: Library },
  { to: '/roadmap', label: 'Learning Roadmap', icon: Map },
  { to: '/recommendations', label: 'AI Recommendations', icon: Sparkles },
  { to: '/analytics', label: 'Progress & Analytics', icon: BarChart3 },
  { to: '/profile', label: 'Profile', icon: UserRound },
]
