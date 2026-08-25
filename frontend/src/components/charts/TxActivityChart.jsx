import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import EmptyState from '../ui/EmptyState'

export default function TxActivityChart({ transactions = [] }) {
  if (!transactions || transactions.length === 0) {
    return <EmptyState message="No transaction activity yet." />
  }

  // Group last 60 transactions by index-based buckets of 10 transactions each
  const bucketSize = 10
  const maxCount = Math.min(transactions.length, 60)
  const buckets = []

  for (let i = 0; i < maxCount; i += bucketSize) {
    const slice = transactions.slice(i, i + bucketSize)
    const upper = Math.min(i + bucketSize, maxCount)
    buckets.push({
      label: `${i + 1}–${upper}`,
      COMMITTED: slice.filter((t) =>
        ['COMMITTED', 'ACTIVE', 'COMPLETED', 'CLOSED'].includes(
          (t.status || '').toUpperCase()
        )
      ).length,
      ABORTED: slice.filter((t) =>
        ['ABORTED', 'CANCELLED', 'ROLLINGBACK'].includes(
          (t.status || '').toUpperCase()
        )
      ).length,
      QUEUED: slice.filter((t) =>
        ['QUEUED', 'ARBITRATING', 'PREPARING', 'COMMITTING', 'NO_CONFLICT'].includes(
          (t.status || '').toUpperCase()
        )
      ).length,
    })
  }

  return (
    <div style={{ width: '100%', height: 180 }}>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={buckets} margin={{ top: 8, right: 16, left: -24, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis
            dataKey="label"
            tick={{ fontFamily: 'var(--font-mono)', fontSize: 11, fill: 'var(--ink-muted)' }}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontFamily: 'var(--font-mono)', fontSize: 11, fill: 'var(--ink-muted)' }}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--surface)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--radius-input)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--ink)',
            }}
          />
          <Legend wrapperStyle={{ fontFamily: 'var(--font-body)', fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="COMMITTED"
            stroke="var(--signal-green)"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="ABORTED"
            stroke="var(--critical-red)"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="QUEUED"
            stroke="var(--pulse-blue)"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
