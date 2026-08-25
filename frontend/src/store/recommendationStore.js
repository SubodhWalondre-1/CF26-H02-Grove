import { create } from 'zustand'
import { getRecommendations } from '../lib/api'

export const useRecommendationStore = create((set, get) => ({
  results: [],
  selectedBundles: {}, // map of patientId -> BundleOption
  loading: false,
  error: null,

  fetchRecommendations: async (patients) => {
    set({ loading: true, error: null })
    try {
      const response = await getRecommendations(patients)
      const data = response.data?.results || []
      
      // Auto-select greedy_reserved or top pick for convenience
      const initialSelected = {}
      data.forEach((pRec) => {
        if (pRec.recommendations && pRec.recommendations.length > 0) {
          const topPick = pRec.recommendations.find((r) => r.greedy_reserved) || pRec.recommendations[0]
          initialSelected[pRec.patient_id] = topPick
        }
      })

      set({ results: data, selectedBundles: initialSelected, loading: false })
      return data
    } catch (err) {
      const message = err.response?.data?.detail || err.message || 'Failed to fetch recommendations'
      set({ error: message, loading: false })
      throw err
    }
  },

  selectBundle: (patientId, bundle) => {
    set((state) => ({
      selectedBundles: {
        ...state.selectedBundles,
        [patientId]: bundle,
      },
    }))
  },

  clearRecommendations: () => {
    set({ results: [], selectedBundles: {}, error: null })
  },
}))
