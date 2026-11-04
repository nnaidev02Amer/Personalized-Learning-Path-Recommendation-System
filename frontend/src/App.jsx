import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeContext'
import { StudentProvider } from './context/StudentContext'
import { ToastProvider } from './context/ToastContext'
import Layout from './components/layout/Layout'
import { PageSkeleton } from './components/ui/States'

// Each page is its own chunk, so the first load stays small.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const MyLearning = lazy(() => import('./pages/MyLearning'))
const CourseCatalog = lazy(() => import('./pages/CourseCatalog'))
const Roadmap = lazy(() => import('./pages/Roadmap'))
const Recommendations = lazy(() => import('./pages/Recommendations'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Profile = lazy(() => import('./pages/Profile'))
const Quiz = lazy(() => import('./pages/Quiz'))
const NotFound = lazy(() => import('./pages/NotFound'))

const page = (Component) => (
  <Suspense fallback={<PageSkeleton />}><Component /></Suspense>
)

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <StudentProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Layout />}>
                <Route index element={page(Dashboard)} />
                <Route path="learning" element={page(MyLearning)} />
                <Route path="courses" element={page(CourseCatalog)} />
                <Route path="roadmap" element={page(Roadmap)} />
                <Route path="recommendations" element={page(Recommendations)} />
                <Route path="analytics" element={page(Analytics)} />
                <Route path="profile" element={page(Profile)} />
                <Route path="quiz/:quizId" element={page(Quiz)} />
                <Route path="*" element={page(NotFound)} />
              </Route>
            </Routes>
          </BrowserRouter>
        </StudentProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}
