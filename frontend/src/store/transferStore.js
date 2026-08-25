// frontend/src/store/transferStore.js
import { create } from 'zustand'
import api from '../lib/api'

export const useTransferStore = create((set) => ({
  activeTransfers: [],
  transferHistory: {},
  loading: false,
  error: null,

  fetchActiveTransfers: async () => {
    set({ loading: true, error: null })
    try {
      const res = await api.get('/transfers/active')
      set({ activeTransfers: res.data?.items || [], loading: false })
    } catch (err) {
      set({ error: err.message, loading: false })
    }
  },

  fetchPatientTransferHistory: async (patientId) => {
    try {
      const res = await api.get(`/patients/${patientId}/transfer-history`)
      set((state) => ({
        transferHistory: {
          ...state.transferHistory,
          [patientId]: res.data?.items || [],
        },
      }))
    } catch (_) {}
  },

  initiateTransfer: async (payload) => {
    const res = await api.post('/transfers', payload)
    return res.data
  },

  confirmTransport: async (txId) => {
    const res = await api.post(`/transfers/${txId}/confirm-transport`)
    return res.data
  },

  commitTransfer: async (txId) => {
    const res = await api.post(`/transfers/${txId}/commit`)
    return res.data
  },

  cancelTransfer: async (txId, reason = 'MANUAL_CANCEL') => {
    const res = await api.post(`/transfers/${txId}/cancel?reason=${encodeURIComponent(reason)}`)
    return res.data
  },

  // Live WebSocket update
  updateTransferState: (txId, newStatus) =>
    set((state) => {
      if (['COMMITTED', 'ROLLED_BACK', 'FAILED'].includes(newStatus)) {
        return {
          activeTransfers: state.activeTransfers.filter((t) => t.tx_id !== txId),
        }
      }
      return {
        activeTransfers: state.activeTransfers.map((t) =>
          t.tx_id === txId ? { ...t, status: newStatus } : t
        ),
      }
    }),
}))
