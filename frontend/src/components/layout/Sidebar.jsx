import React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/authStore'

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard' },
  { path: '/recommendations', label: 'AI Recommender' },
  { path: '/resource-grid', label: 'Resource Grid' },
  { path: '/transactions', label: 'Transactions' },
  { path: '/conflicts', label: 'Conflicts' },
  { path: '/resources', label: 'Resources' },
  { path: '/bundles', label: 'Bundles' },
  { path: '/audit', label: 'Audit Logs' },
  { path: '/admin', label: 'Admin', adminOnly: true },
]

export default function Sidebar() {
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)

  const isAdmin = user?.role === 'admin'

  const visibleItems = NAV_ITEMS.filter((item) => {
    if (item.adminOnly && !isAdmin) return false
    return true
  })

  return (
    <>
      <style>{`
        .mediora-sidebar {
          position: fixed;
          top: 76px;
          left: 0;
          bottom: 0;
          width: var(--sidebar-width);
          background-color: var(--surface-recessed);
          border-right: 1px solid var(--line);
          display: flex;
          flex-direction: column;
          padding: var(--space-2) 0;
          z-index: 90;
          overflow-y: auto;
        }

        .mediora-nav-item {
          display: flex;
          align-items: center;
          padding: 10px 20px;
          cursor: pointer;
          font-family: var(--font-body);
          font-size: var(--text-body);
          text-decoration: none;
          user-select: none;
          transition: background-color 0.15s ease, color 0.15s ease;
          border-left: 2px solid transparent;
        }

        .mediora-nav-item:hover {
          background-color: var(--surface);
          color: var(--ink);
        }

        .mediora-nav-item.active {
          border-left: 2px solid var(--pulse-blue);
          color: var(--ink);
          font-weight: 600;
          background-color: var(--surface);
        }

        .mediora-nav-item.inactive {
          color: var(--ink-muted);
          font-weight: 500;
        }

        @media (max-width: 768px) {
          .mediora-sidebar {
            top: auto;
            bottom: 0;
            left: 0;
            right: 0;
            width: 100%;
            height: 56px;
            flex-direction: row;
            border-right: none;
            border-top: 1px solid var(--line);
            padding: 0;
            justify-content: space-around;
            align-items: center;
            overflow-x: auto;
          }

          .mediora-nav-item {
            flex: 1;
            justify-content: center;
            padding: 8px 6px;
            font-size: 0.75rem;
            border-left: none !important;
            border-top: 2px solid transparent;
            white-space: nowrap;
          }

          .mediora-nav-item.active {
            border-top: 2px solid var(--pulse-blue) !important;
          }
        }
      `}</style>

      <nav aria-label="Main Navigation" className="mediora-sidebar">
        {visibleItems.map((item) => {
          const isActive =
            item.path === '/'
              ? location.pathname === '/'
              : location.pathname === item.path || location.pathname.startsWith(`${item.path}/`)

          return (
            <div
              key={item.path}
              onClick={() => navigate(item.path)}
              className={`mediora-nav-item ${isActive ? 'active' : 'inactive'}`}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && navigate(item.path)}
            >
              <span>{item.label}</span>
            </div>
          )
        })}
      </nav>
    </>
  )
}
