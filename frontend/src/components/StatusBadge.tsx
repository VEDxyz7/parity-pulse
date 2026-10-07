export function StatusBadge({ children, tone = 'neutral' }: {
  children: React.ReactNode
  tone?: 'green' | 'neutral' | 'amber'
}) {
  return <span className={`status-badge ${tone}`}><i aria-hidden="true" />{children}</span>
}
