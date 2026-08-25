import React, { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/layout/Layout'
import ErrorBoundary from './components/ui/ErrorBoundary'
import PrivateRoute from './router/PrivateRoute'
import { useAuthStore } from './store/authStore'
import { useConflictStore } from './store/conflictStore'
import { useResourceStore } from './store/resourceStore'
import { useTransactionStore } from './store/transactionStore'

// Lazy-loaded clinical page components
const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Transactions = lazy(() => import('./pages/Transactions'))
const TransactionDetails = lazy(() => import('./pages/TransactionDetails'))
const Conflicts = lazy(() => import('./pages/Conflicts'))
const Resources = lazy(() => import('./pages/Resources'))
const Bundles = lazy(() => import('./pages/Bundles'))
const AuditLogs = lazy(() => import('./pages/AuditLogs'))
const Admin = lazy(() => import('./pages/Admin'))
const Recommendations = lazy(() => import('./pages/Recommendations'))
const PublicBoard = lazy(() => import('./pages/PublicBoard'))
const ResourceGrid = lazy(() => import('./pages/ResourceGrid'))

export default function App() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  const subscribeTxWS = useTransactionStore((state) => state.subscribeToWS)
  const unsubscribeTxWS = useTransactionStore((state) => state.unsubscribeFromWS)

  const subscribeResWS = useResourceStore((state) => state.subscribeToWS)
  const unsubscribeResWS = useResourceStore((state) => state.unsubscribeFromWS)

  const subscribeConflictWS = useConflictStore((state) => state.subscribeToWS)
  const unsubscribeConflictWS = useConflictStore((state) => state.unsubscribeFromWS)

  useEffect(() => {
    if (isAuthenticated) {
      subscribeTxWS()
      subscribeResWS()
      subscribeConflictWS()
    }

    return () => {
      unsubscribeTxWS()
      unsubscribeResWS()
      unsubscribeConflictWS()
    }
  }, [
    isAuthenticated,
    subscribeTxWS,
    unsubscribeTxWS,
    subscribeResWS,
    unsubscribeResWS,
    subscribeConflictWS,
    unsubscribeConflictWS,
  ])

  return (
    <ErrorBoundary showDetail={import.meta.env.DEV}>
      <BrowserRouter>
        <Suspense
          fallback={
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: '100vh',
                fontFamily: 'var(--font-body)',
                color: 'var(--ink-muted)',
                backgroundColor: 'var(--surface)',
              }}
            >
              Loading Mediora...
            </div>
          }
        >
          <Routes>
            {/* Public Authentication & Donation Board Routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/public/board" element={<PublicBoard />} />

            {/* Protected Application Routes */}
            <Route element={<PrivateRoute />}>
              <Route element={<Layout />}>
                <Route index element={<Dashboard />} />
                <Route path="transactions" element={<Transactions />} />
                <Route path="transactions/:txId" element={<TransactionDetails />} />
                <Route path="conflicts" element={<Conflicts />} />
                <Route path="resources" element={<Resources />} />
                <Route path="resource-grid" element={<ResourceGrid />} />
                <Route path="bundles" element={<Bundles />} />
                <Route path="recommendations" element={<Recommendations />} />
                <Route path="audit" element={<AuditLogs />} />
                <Route path="admin" element={<Admin />} />
              </Route>
            </Route>

            {/* Catch-all redirect */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
