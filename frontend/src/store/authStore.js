import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { getMe, login as apiLogin } from '../lib/api'
import { wsManager } from '../lib/websocket'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (username, password) => {
        set({ isLoading: true, error: null })
        try {
          const response = await apiLogin(username, password)
          const { access_token } = response.data

          set({ token: access_token, isAuthenticated: true })

          // Connect realtime WebSocket stream
          wsManager.connect(access_token)

          // Fetch authenticated user profile & dynamic permissions
          const meResponse = await getMe()
          const userData = meResponse.data

          set({
            user: userData,
            isLoading: false,
            error: null,
          })

          return userData
        } catch (err) {
          const errorMsg =
            err.response?.data?.error?.message ||
            err.response?.data?.detail ||
            'Invalid credentials or connection error'
          set({
            token: null,
            user: null,
            isAuthenticated: false,
            isLoading: false,
            error: errorMsg,
          })
          throw new Error(errorMsg)
        }
      },

      logout: () => {
        wsManager.disconnect()
        set({
          token: null,
          user: null,
          isAuthenticated: false,
          isLoading: false,
          error: null,
        })
        if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
      },

      loadMe: async () => {
        const { token } = get()
        if (!token) return

        set({ isLoading: true })
        try {
          wsManager.connect(token)
          const meResponse = await getMe()
          set({
            user: meResponse.data,
            isAuthenticated: true,
            isLoading: false,
          })
        } catch (err) {
          console.warn('Session revalidation failed, logging out:', err)
          get().logout()
        }
      },
    }),
    {
      name: 'mediora_auth',
      partialize: (state) => ({ token: state.token }),
      onRehydrateStorage: () => (state) => {
        if (state && state.token) {
          state.loadMe()
        }
      },
    }
  )
)
