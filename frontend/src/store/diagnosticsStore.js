// frontend/src/store/diagnosticsStore.js
import { create } from 'zustand'
import api from '../lib/api'

export const useDiagnosticsStore = create((set) => ({
  equipment: [],
  selectedEquipment: null,
  availability: {},
  loading: false,
  error: null,

  fetchEquipment: async (filters = {}) => {
    set({ loading: true, error: null })
    try {
      const params = new URLSearchParams()
      if (filters.resource_type) params.append('resource_type', filters.resource_type)
      if (filters.status) params.append('status', filters.status)
      const res = await api.get(`/diagnostics/equipment?${params.toString()}`)
      set({ equipment: res.data?.items || [], loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  fetchAvailability: async (equipmentId, dateStr) => {
    try {
      const q = dateStr ? `?date=${dateStr}` : ''
      const res = await api.get(`/diagnostics/equipment/${equipmentId}/availability${q}`)
      set((state) => ({
        availability: {
          ...state.availability,
          [equipmentId]: res.data || {},
        },
      }))
    } catch (_) {}
  },

  setSelectedEquipment: (eq) => set({ selectedEquipment: eq }),

  // Live update: equipment status change from WebSocket
  updateEquipmentStatus: (equipmentId, changes) =>
    set((state) => ({
      equipment: state.equipment.map((eq) =>
        eq.id === equipmentId ? { ...eq, ...changes } : eq
      ),
    })),
}))
