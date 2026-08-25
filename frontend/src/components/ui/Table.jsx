import React from 'react'
import EmptyState from './EmptyState'

export default function Table({
  columns = [],
  rows = [],
  onRowClick,
  emptyMessage = 'No records found.',
  className = '',
}) {
  return (
    <div
      className={`mediora-table-container ${className}`}
      style={{
        width: '100%',
        overflowX: 'auto',
        borderRadius: 'var(--radius-card)',
        border: '1px solid var(--line)',
        backgroundColor: 'var(--surface)',
      }}
    >
      <style>{`
        .mediora-table tr.clickable-row:hover {
          background-color: var(--pulse-blue-soft) !important;
        }
      `}</style>
      <table
        className="mediora-table"
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          textAlign: 'left',
        }}
      >
        <thead>
          <tr
            style={{
              backgroundColor: 'var(--surface-recessed)',
              borderBottom: '1px solid var(--line)',
            }}
          >
            {columns.map((col) => (
              <th
                key={col.key || col.label}
                style={{
                  padding: '10px 16px',
                  fontFamily: 'var(--font-body)',
                  fontSize: 'var(--text-caption)',
                  fontWeight: 600,
                  color: 'var(--ink-muted)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  textAlign: col.align || 'left',
                }}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length || 1} style={{ padding: 0 }}>
                <EmptyState message={emptyMessage} />
              </td>
            </tr>
          ) : (
            rows.map((row, index) => {
              const isEven = index % 2 === 0
              const rowKey = row.tx_id || row.resource_id || row.conflict_id || row.id || row.audit_id || index

              return (
                <tr
                  key={rowKey}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={onRowClick ? 'clickable-row' : ''}
                  style={{
                    backgroundColor: isEven ? 'var(--surface)' : 'var(--surface-recessed)',
                    borderBottom: '1px solid var(--line)',
                    cursor: onRowClick ? 'pointer' : 'default',
                    transition: 'background-color 150ms ease',
                  }}
                >
                  {columns.map((col) => {
                    const cellContent = col.render ? col.render(row) : row[col.key]

                    return (
                      <td
                        key={col.key || col.label}
                        style={{
                          padding: '10px 16px',
                          color: 'var(--ink)',
                          fontSize: col.mono ? 'var(--text-mono)' : 'var(--text-body)',
                          fontFamily: col.mono ? 'var(--font-mono)' : 'var(--font-body)',
                          textAlign: col.align || 'left',
                          whiteSpace: col.nowrap ? 'nowrap' : 'normal',
                        }}
                      >
                        {cellContent != null ? cellContent : '—'}
                      </td>
                    )
                  })}
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
