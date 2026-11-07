import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from './context/ThemeContext'
import { AuthProvider, useAuth } from './context/AuthContext'
import { StudentProvider } from './context/StudentContext'
import { ToastProvider } from './context/ToastContext'
import Layout from './components/layout/Layout'
import RequireAuth from './components/auth/RequireAuth'
import { PageSkeleton } from './components/ui/States'

// Each page is its own chunk, so the first load stays small.
const Login = lazy(() => import('./pages/Login'))
const Register = lazy(() => import('./pages/Register'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const MyLearning = lazy(() => import('./pages/MyLearning'))
const CourseInsights = lazy(() => import('./pages/CourseInsights'))
const CourseCatalog = lazy(() => import('./pages/CourseCatalog'))
const Roadmap = lazy(() => import('./pages/Roadmap'))
const Recommendations = lazy(() => import('./pages/Recommendations'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Profile = lazy(() => import('./pages/Profile'))
const Quiz = lazy(() => import('./pages/Quiz'))
const ModelEvaluation = lazy(() => import('./pages/ModelEvaluation'))
const AdminDashboard = lazy(() => import('./pages/admin/AdminDashboard'))
const AdminStudents = lazy(() => import('./pages/admin/AdminStudents'))
const AdminCourses = lazy(() => import('./pages/admin/AdminCourses'))
const AdminAccounts = lazy(() => import('./pages/admin/AdminAccounts'))
const AdminRequests = lazy(() => import('./pages/admin/AdminRequests'))
const NotFound = lazy(() => import('./pages/NotFound'))

const page = (Component) => (
  <Suspense fallback={<PageSkeleton />}><Component /></Suspense>
)
const adminPage = (Component) => <RequireAuth role="admin">{page(Component)}</RequireAuth>
const studentPage = (Component) => <RequireAuth role="student">{page(Component)}</RequireAuth>

/** "/" is the administrator's overview, or a student's own dashboard. */
function Home() {
  const { isAdmin } = useAuth()
  return isAdmin ? adminPage(AdminDashboard) : studentPage(Dashboard)
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <StudentProvider>
            <BrowserRouter>
              <Routes>
                <Route path="login" element={page(Login)} />
                <Route path="admin/login" element={page(Login)} />
                <Route path="register" element={page(Register)} />
                <Route element={<RequireAuth><Layout /></RequireAuth>}>
                  <Route index element={<Home />} />
                  <Route path="dashboard" element={studentPage(Dashboard)} />
                  <Route path="learning" element={studentPage(MyLearning)} />
                  <Route path="learning/:courseId" element={studentPage(CourseInsights)} />
                  <Route path="courses" element={studentPage(CourseCatalog)} />
                  <Route path="roadmap" element={studentPage(Roadmap)} />
                  <Route path="recommendations" element={studentPage(Recommendations)} />
                  <Route path="analytics" element={studentPage(Analytics)} />
                  <Route path="profile" element={studentPage(Profile)} />
                  <Route path="quiz/:quizId" element={studentPage(Quiz)} />
                  <Route path="models" element={adminPage(ModelEvaluation)} />
                  <Route path="admin/students" element={adminPage(AdminStudents)} />
                  <Route path="admin/courses" element={adminPage(AdminCourses)} />
                  <Route path="admin/requests" element={adminPage(AdminRequests)} />
                  <Route path="admin/accounts" element={adminPage(AdminAccounts)} />
                  <Route path="*" element={page(NotFound)} />
                </Route>
              </Routes>
            </BrowserRouter>
          </StudentProvider>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}
