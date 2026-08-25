import { create } from 'zustand'
import {
  cancelTransaction as apiCancelTransaction,
  completeTransaction as apiCompleteTransaction,
  createTransaction as apiCreateTransaction,
  getTransaction as apiGetTransaction,
  getTxStateHistory as apiGetTxStateHistory,
  listTransactions as apiListTransactions,
} from '../lib/api'
import { wsManager } from '../lib/websocket'

let wsSubscriptions = []

export const useTransactionStore = create((set, get) => ({
  transactions: [],
  currentTx: null,
  stateHistory: [],
  pagination: { page: 1, page_size: 25, total: 0 },
  filters: { status: null, patient_id: null },
  isLoading: false,
  error: null,

  fetchTransactions: async (customParams = {}) => {
    set({ isLoading: true, error: null })
    try {
      const { filters, pagination } = get()
      const queryParams = {
        page: customParams.page || pagination.page,
        page_size: customParams.page_size || pagination.page_size,
        status: customParams.status !== undefined ? customParams.status : filters.status,
        patient_id:
          customParams.patient_id !== undefined
            ? customParams.patient_id
            : filters.patient_id,
      }

      // Remove null/empty query params
      Object.keys(queryParams).forEach(
        (key) => (queryParams[key] == null || queryParams[key] === '') && delete queryParams[key]
      )

      const response = await apiListTransactions(queryParams)
      const data = response.data

      set({
        transactions: data.items || [],
        pagination: {
          page: data.page || 1,
          page_size: data.page_size || 25,
          total: data.total || 0,
        },
        isLoading: false,
      })
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        'Failed to load transactions'
      set({ isLoading: false, error: errorMsg })
    }
  },

  fetchTransaction: async (txId) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiGetTransaction(txId)
      set({ currentTx: response.data, isLoading: false })
      return response.data
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        `Failed to load transaction ${txId}`
      set({ isLoading: false, error: errorMsg, currentTx: null })
      throw err
    }
  },

  fetchStateHistory: async (txId) => {
    try {
      const response = await apiGetTxStateHistory(txId)
      set({ stateHistory: response.data.history || [] })
      return response.data.history
    } catch (err) {
      console.warn(`Failed to fetch state history for ${txId}:`, err)
      set({ stateHistory: [] })
    }
  },

  createTransaction: async (payload) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiCreateTransaction(payload)
      const createdTx = response.data
      await get().fetchTransactions()
      return createdTx
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        'Failed to create transaction'
      set({ isLoading: false, error: errorMsg })
      throw err
    }
  },

  cancelTransaction: async (txId, reason) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiCancelTransaction(txId, reason)
      await get().fetchTransaction(txId)
      await get().fetchStateHistory(txId)
      await get().fetchTransactions()
      return response.data
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        `Failed to cancel transaction ${txId}`
      set({ isLoading: false, error: errorMsg })
      throw err
    }
  },

  completeTransaction: async (txId) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiCompleteTransaction(txId)
      await get().fetchTransaction(txId)
      await get().fetchStateHistory(txId)
      await get().fetchTransactions()
      return response.data
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        `Failed to complete transaction ${txId}`
      set({ isLoading: false, error: errorMsg })
      throw err
    }
  },

  setFilters: (newFilters) => {
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
      pagination: { ...state.pagination, page: 1 },
    }))
    get().fetchTransactions({ page: 1 })
  },

  setPage: (page) => {
    set((state) => ({
      pagination: { ...state.pagination, page },
    }))
    get().fetchTransactions({ page })
  },

  subscribeToWS: () => {
    // Avoid duplicate subscriptions
    get().unsubscribeFromWS()

    const onTxCreated = (msg) => {
      set((state) => {
        const exists = state.transactions.some((t) => t.tx_id === msg.tx_id)
        if (exists) return state

        const newTx = {
          tx_id: msg.tx_id,
          status: msg.status || 'CREATED',
          request_type: msg.request_type || 'single_resource',
          request_fingerprint: msg.request_fingerprint || '',
          created_at: msg.timestamp || new Date().toISOString(),
        }
        return {
          transactions: [newTx, ...state.transactions],
          pagination: {
            ...state.pagination,
            total: state.pagination.total + 1,
          },
        }
      })
    }

    const onTxUpdated = (msg) => {
      const { tx_id, status } = msg
      if (!tx_id) return

      set((state) => {
        const updatedList = state.transactions.map((t) =>
          t.tx_id === tx_id ? { ...t, status: status || t.status } : t
        )

        let updatedCurrent = state.currentTx
        if (state.currentTx && state.currentTx.tx_id === tx_id) {
          updatedCurrent = {
            ...state.currentTx,
            status: status || state.currentTx.status,
          }
        }

        return {
          transactions: updatedList,
          currentTx: updatedCurrent,
        }
      })
    }

    const onTtlWarning = (msg) => {
      const { tx_id, remaining_seconds } = msg
      if (!tx_id) return

      set((state) => {
        if (state.currentTx && state.currentTx.tx_id === tx_id) {
          return {
            currentTx: {
              ...state.currentTx,
              hold_remaining_seconds: remaining_seconds,
            },
          }
        }
        return state
      })
    }

    wsSubscriptions = [
      wsManager.subscribe('TRANSACTION_CREATED', onTxCreated),
      wsManager.subscribe('TRANSACTION_UPDATED', onTxUpdated),
      wsManager.subscribe('TTL_WARNING', onTtlWarning),
      wsManager.subscribe('BUNDLE_COMMITTED', onTxUpdated),
      wsManager.subscribe('BUNDLE_ROLLBACK', onTxUpdated),
    ]
  },

  unsubscribeFromWS: () => {
    wsSubscriptions.forEach((unsub) => unsub && unsub())
    wsSubscriptions = []
  },
}))
