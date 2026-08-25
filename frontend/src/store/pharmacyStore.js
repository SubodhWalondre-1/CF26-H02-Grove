// frontend/src/store/pharmacyStore.js
import { create } from 'zustand'
import api from '../lib/api'

export const usePharmacyStore = create((set) => ({
  resources: [],
  shortages: [],
  loading: false,
  error: null,

  fetchResources: async (filters = {}) => {
    set({ loading: true, error: null })
    try {
      const params = new URLSearchParams()
      if (filters.resource_type) params.append('resource_type', filters.resource_type)
      if (filters.sub_type) params.append('sub_type', filters.sub_type)
      if (filters.status) params.append('status', filters.status)
      const res = await api.get(`/pharmacy/resources?${params.toString()}`)
      set({ resources: res.data?.items || [], loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  fetchShortages: async () => {
    try {
      const res = await api.get('/pharmacy/shortage-status')
      set({ shortages: res.data?.items || [] })
    } catch (_) {}
  },

  // Live update: single resource stock change from WebSocket
  updateResourceStock: (resourceId, changes) =>
    set((state) => ({
      resources: state.resources.map((r) =>
        r.id === resourceId ? { ...r, ...changes } : r
      ),
    })),
}))
