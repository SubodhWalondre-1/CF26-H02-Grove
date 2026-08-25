import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { useAuthStore } from './store/authStore'
import './styles/globals.css'

// On boot: restore auth from localStorage and validate token
useAuthStore.getState().loadMe()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
