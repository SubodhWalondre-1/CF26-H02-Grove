import { create } from 'zustand'
import {
  getConflict as apiGetConflict,
  getConflictScore as apiGetConflictScore,
  listConflicts as apiListConflicts,
} from '../lib/api'
import { wsManager } from '../lib/websocket'

let wsSubscriptions = []

export const useConflictStore = create((set, get) => ({
  conflicts: [],
  currentConflict: null,
  currentScoreBreakdown: null,
  filters: { status: 'open' },
  hasNewConflict: false,
  isLoading: false,
  error: null,

  fetchConflicts: async (customParams = {}) => {
    set({ isLoading: true, error: null })
    try {
      const { filters } = get()
      const queryParams = {
        status: customParams.status !== undefined ? customParams.status : filters.status,
        resource_id: customParams.resource_id,
        tx_id: customParams.tx_id,
      }

      Object.keys(queryParams).forEach(
        (key) => (queryParams[key] == null || queryParams[key] === '') && delete queryParams[key]
      )

      const response = await apiListConflicts(queryParams)
      const data = response.data

      set({
        conflicts: data.items || [],
        isLoading: false,
      })
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        'Failed to load clinical conflicts'
      set({ isLoading: false, error: errorMsg })
    }
  },

  fetchConflict: async (conflictId) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiGetConflict(conflictId)
      set({ currentConflict: response.data, isLoading: false })
      return response.data
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        `Failed to load conflict ${conflictId}`
      set({ isLoading: false, error: errorMsg, currentConflict: null })
      throw err
    }
  },

  fetchScoreBreakdown: async (conflictId, txId) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiGetConflictScore(conflictId, txId)
      set({ currentScoreBreakdown: response.data, isLoading: false })
      return response.data
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        `Failed to load score breakdown for conflict ${conflictId}`
      set({ isLoading: false, error: errorMsg, currentScoreBreakdown: null })
      throw err
    }
  },

  setFilters: (newFilters) => {
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
    }))
    get().fetchConflicts()
  },

  clearNewConflictFlag: () => {
    set({ hasNewConflict: false })
  },

  subscribeToWS: () => {
    get().unsubscribeFromWS()

    const onConflictDetected = (msg) => {
      const { conflict_id, resource_id, transactions } = msg
      if (!conflict_id) return

      set((state) => {
        const exists = state.conflicts.some((c) => c.conflict_id === conflict_id)
        if (exists) return state

        const newConflict = {
          conflict_id,
          resource_contested: resource_id || null,
          transactions: transactions || [],
          winner_tx_id: null,
          resolution: 'transaction_level',
          resolved_at: null,
          created_at: msg.timestamp || new Date().toISOString(),
        }

        return {
          conflicts: [newConflict, ...state.conflicts],
          hasNewConflict: true,
        }
      })
    }

    const onArbitrationResult = (msg) => {
      const { conflict_id, winner_tx_id } = msg
      if (!conflict_id) return

      set((state) => {
        const updatedList = state.conflicts.map((c) =>
          c.conflict_id === conflict_id
            ? {
                ...c,
                winner_tx_id: winner_tx_id || c.winner_tx_id,
                resolved_at: msg.timestamp || new Date().toISOString(),
              }
            : c
        )

        let updatedCurrent = state.currentConflict
        if (state.currentConflict && state.currentConflict.conflict_id === conflict_id) {
          updatedCurrent = {
            ...state.currentConflict,
            winner_tx_id: winner_tx_id || state.currentConflict.winner_tx_id,
            resolved_at: msg.timestamp || new Date().toISOString(),
          }
        }

        return {
          conflicts: updatedList,
          currentConflict: updatedCurrent,
        }
      })
    }

    wsSubscriptions = [
      wsManager.subscribe('CONFLICT_DETECTED', onConflictDetected),
      wsManager.subscribe('ARBITRATION_RESULT', onArbitrationResult),
    ]
  },

  unsubscribeFromWS: () => {
    wsSubscriptions.forEach((unsub) => unsub && unsub())
    wsSubscriptions = []
  },
}))
