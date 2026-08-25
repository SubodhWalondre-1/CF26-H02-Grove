import React from 'react'
import Button from './Button'

export default function Pagination({
  page = 1,
  pageSize = 25,
  total = 0,
  onPageChange,
  className = '',
}) {
  const totalPages = Math.max(1, Math.ceil((total || 0) / (pageSize || 25)))
  const isFirstPage = page <= 1
  const isLastPage = page >= totalPages

  if (total <= pageSize && page === 1) {
    return null
  }

  return (
    <div
      className={`mediora-pagination ${className}`}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-2)',
        padding: 'var(--space-2) 0',
      }}
    >
      <Button
        variant="secondary"
        size="sm"
        disabled={isFirstPage}
        onClick={() => onPageChange && onPageChange(page - 1)}
      >
        Previous
      </Button>

      <span
        style={{
          fontFamily: 'var(--font-body)',
          fontSize: 'var(--text-caption)',
          color: 'var(--ink-muted)',
          fontWeight: 500,
          userSelect: 'none',
          padding: '0 8px',
        }}
      >
        Page {page} of {totalPages}
      </span>

      <Button
        variant="secondary"
        size="sm"
        disabled={isLastPage}
        onClick={() => onPageChange && onPageChange(page + 1)}
      >
        Next
      </Button>
    </div>
  )
}
