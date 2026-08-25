// frontend/src/store/labStore.js
import { create } from 'zustand'
import api from '../lib/api'

export const useLabStore = create((set) => ({
  stations: [],
  samples: [],
  totalActive: 0,
  loading: false,
  error: null,

  fetchLabQueue: async () => {
    set({ loading: true, error: null })
    try {
      const res = await api.get('/diagnostics/lab/queue')
      set({
        stations: res.data?.stations || [],
        samples: res.data?.samples || [],
        totalActive: res.data?.total_active_samples || 0,
        loading: false,
      })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  // Live update: lab load or sample state from WebSocket
  updateStationLoad: (slotId, changes) =>
    set((state) => ({
      stations: state.stations.map((st) =>
        st.id === slotId ? { ...st, ...changes } : st
      ),
    })),
}))
