import React from 'react'
import { Outlet } from 'react-router-dom'
import Header from './Header'
import LiveStatusStrip from './LiveStatusStrip'
import Sidebar from './Sidebar'

export default function Layout() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        backgroundColor: 'var(--surface)',
      }}
    >
      <style>{`
        .mediora-main-content {
          margin-left: var(--sidebar-width);
          flex: 1;
          display: flex;
          flex-direction: column;
          min-height: calc(100vh - 76px);
          width: calc(100% - var(--sidebar-width));
        }

        @media (max-width: 768px) {
          .mediora-main-content {
            margin-left: 0 !important;
            width: 100% !important;
            padding-bottom: 56px;
          }
        }
      `}</style>

      <Header />

      <div
        style={{
          display: 'flex',
          flex: 1,
          marginTop: '76px', // Offset for fixed Header (56px) + PulseLine (20px)
        }}
      >
        <Sidebar />

        <main className="mediora-main-content">
          <LiveStatusStrip />
          <div
            style={{
              padding: 'var(--space-4)',
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-4)',
            }}
          >
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
