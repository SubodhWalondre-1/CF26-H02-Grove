import { create } from 'zustand'
import {
  getResource as apiGetResource,
  getResourceHistory as apiGetResourceHistory,
  getResources as apiGetResources,
} from '../lib/api'
import { wsManager } from '../lib/websocket'

let wsSubscriptions = []

export const useResourceStore = create((set, get) => ({
  resources: [],
  currentResource: null,
  resourceHistory: [],
  filters: { type: null, status: null },
  isLoading: false,
  error: null,

  fetchResources: async (customParams = {}) => {
    set({ isLoading: true, error: null })
    try {
      const { filters } = get()
      const queryParams = {
        type: customParams.type !== undefined ? customParams.type : filters.type,
        status: customParams.status !== undefined ? customParams.status : filters.status,
      }

      // Strip null or empty query params
      Object.keys(queryParams).forEach(
        (key) => (queryParams[key] == null || queryParams[key] === '') && delete queryParams[key]
      )

      const response = await apiGetResources(queryParams)
      const data = response.data

      set({
        resources: data.items || [],
        isLoading: false,
      })
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        'Failed to load clinical resources'
      set({ isLoading: false, error: errorMsg })
    }
  },

  fetchResource: async (resourceId) => {
    set({ isLoading: true, error: null })
    try {
      const response = await apiGetResource(resourceId)
      set({ currentResource: response.data, isLoading: false })
      return response.data
    } catch (err) {
      const errorMsg =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        `Failed to load resource ${resourceId}`
      set({ isLoading: false, error: errorMsg, currentResource: null })
      throw err
    }
  },

  fetchResourceHistory: async (resourceId) => {
    try {
      const response = await apiGetResourceHistory(resourceId)
      set({ resourceHistory: response.data.events || [] })
      return response.data.events
    } catch (err) {
      console.warn(`Failed to fetch history for resource ${resourceId}:`, err)
      set({ resourceHistory: [] })
    }
  },

  setFilters: (newFilters) => {
    set((state) => ({
      filters: { ...state.filters, ...newFilters },
    }))
    get().fetchResources()
  },

  subscribeToWS: () => {
    get().unsubscribeFromWS()

    const onResourceStateChange = () => {
      get().fetchResources()
      const { currentResource } = get()
      if (currentResource && currentResource.resource_id) {
        get().fetchResource(currentResource.resource_id)
        get().fetchResourceHistory(currentResource.resource_id)
      }
    }

    wsSubscriptions = [
      wsManager.subscribe('TRANSACTION_UPDATED', onResourceStateChange),
      wsManager.subscribe('BUNDLE_PREPARE_UPDATE', onResourceStateChange),
      wsManager.subscribe('COMPENSATION_PROGRESS', onResourceStateChange),
      wsManager.subscribe('BUNDLE_COMMITTED', onResourceStateChange),
      wsManager.subscribe('BUNDLE_ROLLBACK', onResourceStateChange),
      wsManager.subscribe('RECOVERY_ACTION', onResourceStateChange),
    ]
  },

  unsubscribeFromWS: () => {
    wsSubscriptions.forEach((unsub) => unsub && unsub())
    wsSubscriptions = []
  },
}))
