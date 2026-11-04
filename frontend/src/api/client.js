// Thin wrapper around fetch for the FastAPI backend.
// In development, Vite proxies /api to http://127.0.0.1:8000 (see vite.config.js).
// For a separately hosted backend, set VITE_API_BASE_URL (e.g. https://api.example.com).

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(status, code, message, details = []) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }

  /** Map of field name -> message, for 422 validation errors. */
  get fieldErrors() {
    return Object.fromEntries(
      (this.details || []).filter((d) => d.field).map((d) => [d.field.split('.').pop(), d.message]),
    )
  }
}

function buildQuery(params) {
  if (!params) return ''
  const q = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') q.set(k, v)
  })
  const s = q.toString()
  return s ? `?${s}` : ''
}

export async function request(path, { method = 'GET', body, params } = {}) {
  let response
  try {
    response = await fetch(`${BASE_URL}/api${path}${buildQuery(params)}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'network_error',
      'Cannot reach the API server. Make sure the backend is running on http://127.0.0.1:8000.')
  }
  if (response.status === 204) return null

  let payload = null
  try {
    payload = await response.json()
  } catch {
    // non-JSON response (e.g. proxy error page)
  }
  if (!response.ok) {
    const err = payload?.error
    if (!err && response.status >= 500) {
      throw new ApiError(response.status, 'network_error',
        'The API server is not responding. Start the backend and try again.')
    }
    throw new ApiError(response.status, err?.code || 'http_error',
      err?.message || `Request failed (${response.status})`, err?.details || [])
  }
  return payload
}

export const api = {
  health: () => request('/health'),
  meta: () => request('/meta'),

  students: {
    list: (params) => request('/students', { params }),
    get: (id) => request(`/students/${id}`),
    create: (data) => request('/students', { method: 'POST', body: data }),
    update: (id, data) => request(`/students/${id}`, { method: 'PATCH', body: data }),
    remove: (id) => request(`/students/${id}`, { method: 'DELETE' }),
    summary: (id) => request(`/students/${id}/summary`),
    progress: (id, weeks = 12) => request(`/students/${id}/progress`, { params: { weeks } }),
    attempts: (id, limit = 50) => request(`/students/${id}/quiz-attempts`, { params: { limit } }),
    activity: (id, limit = 100) => request(`/students/${id}/activity`, { params: { limit } }),
    logActivity: (id, data) => request(`/students/${id}/activity`, { method: 'POST', body: data }),
  },

  courses: {
    list: (params) => request('/courses', { params: { limit: 100, ...params } }),
    get: (id) => request(`/courses/${id}`),
  },

  enrollments: {
    list: (studentId, status) => request(`/students/${studentId}/enrollments`, { params: { status } }),
    create: (studentId, courseId) =>
      request(`/students/${studentId}/enrollments`, { method: 'POST', body: { course_id: courseId } }),
    update: (id, data) => request(`/enrollments/${id}`, { method: 'PATCH', body: data }),
    completeLesson: (id, lessonId) =>
      request(`/enrollments/${id}/lessons/${lessonId}/complete`, { method: 'POST' }),
  },

  ai: {
    status: () => request('/ml/status'),
    evaluation: () => request('/ml/evaluation'),
    retrain: () => request('/ml/retrain', { method: 'POST' }),
    recommendations: (id, method = 'hybrid', limit = 5) =>
      request(`/students/${id}/recommendations`, { params: { method, limit } }),
    learningStyle: (id) => request(`/students/${id}/learning-style`),
    skills: (id) => request(`/students/${id}/skills`),
    difficulty: (id) => request(`/students/${id}/adaptive-difficulty`),
    predictions: (id) => request(`/students/${id}/predictions`),
    ask: (id, message) => request(`/students/${id}/assistant`, { method: 'POST', body: { message } }),
  },

  quizzes: {
    get: (id) => request(`/quizzes/${id}`),
    submit: (studentId, quizId, data) =>
      request(`/students/${studentId}/quizzes/${quizId}/attempts`, { method: 'POST', body: data }),
  },
}
