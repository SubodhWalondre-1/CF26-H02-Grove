// frontend/src/store/escalationStore.js
import { create } from 'zustand'
import api from '../lib/api'

export const useEscalationStore = create((set) => ({
  escalations: [],
  preemptionAlert: null,
  loading: false,
  error: null,

  fetchEscalations: async (resourceId = null) => {
    set({ loading: true, error: null })
    try {
      const url = resourceId ? `/escalations?resource_id=${encodeURIComponent(resourceId)}` : '/escalations'
      const res = await api.get(url)
      set({ escalations: res.data?.items || [], loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  submitEscalation: async (patientId, targetResourceId, reason = '') => {
    set({ loading: true, error: null })
    try {
      const res = await api.post('/escalations', {
        patient_id: patientId,
        target_resource_id: targetResourceId,
        reason,
      })
      set({ loading: false })
      return res.data
    } catch (err) {
      set({ error: err.message, loading: false })
      throw err
    }
  },

  setPreemptionAlert: (alert) => set({ preemptionAlert: alert }),
  clearPreemptionAlert: () => set({ preemptionAlert: null }),
}))
