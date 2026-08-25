import React from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
  ResponsiveContainer,
} from 'recharts'

export default function ConflictScoreChart({ transactions = [], winnerId = null }) {
  if (!transactions || transactions.length <= 1) {
    return null
  }

  const chartData = transactions.map((tx) => ({
    name: tx.tx_id,
    'Base Acuity': tx.base_acuity || 0,
    'Wait Contribution': tx.wait_contribution || 0,
    isWinner: tx.tx_id === winnerId,
  }))

  return (
    <div style={{ width: '100%', height: 160 }}>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={chartData} margin={{ top: 8, right: 16, left: -24, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
          <XAxis
            dataKey="name"
            tick={{ fontFamily: 'var(--font-mono)', fontSize: 12, fill: 'var(--ink-muted)' }}
          />
          <YAxis
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
          {/* Stacked bars: Base Acuity + Wait Contribution */}
          <Bar dataKey="Base Acuity" stackId="score" fill="var(--pulse-blue)" />
          <Bar
            dataKey="Wait Contribution"
            stackId="score"
            fill="var(--signal-green)"
            radius={[4, 4, 0, 0]}
          >
            {chartData.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.isWinner ? 'var(--signal-green)' : 'var(--alert-amber)'}
                opacity={entry.isWinner ? 1 : 0.6}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
