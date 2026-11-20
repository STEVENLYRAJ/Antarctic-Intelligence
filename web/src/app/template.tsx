/** Route-level enter transition (CSS only; disabled by the global reduced-motion rule). */
export default function Template({ children }: { children: React.ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
