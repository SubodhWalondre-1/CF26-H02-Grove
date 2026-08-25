import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request Interceptor: Attach Bearer JWT
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response Interceptor: Handle 401 Unauthorized
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      useAuthStore.getState().logout()
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ── Auth ─────────────────────────────────────────────────────────────
export const login = (username, password) =>
  api.post('/auth/login', { username, password })

export const refreshToken = (refresh_token) =>
  api.post('/auth/refresh', { refresh_token })

export const getMe = () =>
  api.get('/auth/me')

// ── Patients ─────────────────────────────────────────────────────────
export const getPatient = (patientId) =>
  api.get(`/patients/${patientId}`)

export const getPatientAcuity = (patientId) =>
  api.get(`/patients/${patientId}/acuity`)

// ── Resources ────────────────────────────────────────────────────────
export const getResources = (params) =>
  api.get('/resources', { params })

export const getResource = (resourceId) =>
  api.get(`/resources/${resourceId}`)

export const getResourceHistory = (resourceId) =>
  api.get(`/resources/${resourceId}/history`)

// ── Transactions ─────────────────────────────────────────────────────
export const createTransaction = (body) =>
  api.post('/transactions', body)

export const getTransaction = (txId) =>
  api.get(`/transactions/${txId}`)

export const listTransactions = (params) =>
  api.get('/transactions', { params })

export const getTxStateHistory = (txId) =>
  api.get(`/transactions/${txId}/state-history`)

export const cancelTransaction = (txId, reason) =>
  api.post(`/transactions/${txId}/cancel`, { reason })

export const completeTransaction = (txId) =>
  api.post(`/transactions/${txId}/complete`)

// ── Conflicts ────────────────────────────────────────────────────────
export const getConflict = (conflictId) =>
  api.get(`/conflicts/${conflictId}`)

export const getConflictScore = (conflictId, txId) =>
  api.get(`/conflicts/${conflictId}/score-breakdown`, { params: { tx_id: txId } })

export const listConflicts = (params) =>
  api.get('/conflicts', { params })

// ── Bundles ──────────────────────────────────────────────────────────
export const getBundleStatus = (txId) =>
  api.get(`/bundles/${txId}/prepare-status`)

export const commitBundle = (txId) =>
  api.post(`/bundles/${txId}/commit`)

export const rollbackBundle = (txId) =>
  api.post(`/bundles/${txId}/rollback`)

// ── Recovery ─────────────────────────────────────────────────────────
export const getIncompleteTransactions = () =>
  api.get('/recovery/incomplete-transactions')

export const resolveRecovery = (txId) =>
  api.post(`/recovery/${txId}/resolve`)

export const getRecoveryRuns = (params) =>
  api.get('/recovery/runs', { params })

// ── Audit ────────────────────────────────────────────────────────────
export const listAuditEvents = (params) =>
  api.get('/audit/events', { params })

export const getFullTrace = (txId) =>
  api.get(`/audit/${txId}/full-trace`)

// ── Compensation ─────────────────────────────────────────────────────
export const getCompensationGraph = (txId) =>
  api.get(`/compensation/${txId}/dependency-graph`)

export const getCompensationStatus = (txId) =>
  api.get(`/compensation/${txId}/status`)

// ── Admin ────────────────────────────────────────────────────────────
export const getPolicies = () =>
  api.get('/admin/policies')

export const updatePolicies = (body) =>
  api.put('/admin/policies', body)

export const getAdminConfig = () =>
  api.get('/admin/config')

export const updateAdminConfig = (body) =>
  api.put('/admin/config', body)

// ── AI Recommendations ───────────────────────────────────────────────
export const getRecommendations = (patients) =>
  api.post('/recommendations', { patients })

// ── Operation Record PDF ─────────────────────────────────────────────
export const getRecordStatus = (txId) =>
  api.get(`/records/${txId}/status`)

export const downloadRecordPdf = (txId) =>
  api.get(`/records/${txId}/pdf`, { responseType: 'blob' })

export const regenerateRecord = (txId) =>
  api.post(`/records/${txId}/regenerate`)

// ── Public Donation Board & Shortage Alerts ──────────────────────────
export const getPublicAlerts = () =>
  api.get('/public/board/alerts')

export const resolveAlert = (alertId) =>
  api.post(`/admin/alerts/${alertId}/resolve`)

export const getShortageThresholds = () =>
  api.get('/admin/shortage-thresholds')

export const updateShortageThreshold = (body) =>
  api.put('/admin/shortage-thresholds', body)

export default api
