import { Link } from 'react-router-dom'
import { useState, useCallback } from 'react'

// ── Table of Contents items ───────────────────────────────────────────────────

const TOC = [
  { id: 'quick-start', label: 'Quick Start' },
  { id: 'baseline-sandbox', label: 'Baseline vs Sandbox' },
  { id: 'step-import', label: 'Import / Draw' },
  { id: 'step-sandbox', label: 'Sandbox Layers' },
  { id: 'step-goal', label: 'Optimization Goals' },
  { id: 'step-simulate', label: 'Simulation' },
  { id: 'step-results', label: 'Results' },
  { id: 'step-promote', label: 'Promote to PR' },
  { id: 'yaml-ref', label: 'YAML Reference' },
  { id: 'best-practices', label: 'Best Practices' },
]

export function InstructionsPage() {
  return (
    <div className="min-h-screen bg-canvas-bg flex flex-col">
      <Nav />

      <div className="flex-1 flex">
        {/* ── Sidebar TOC (desktop) ──────────────────────────────────── */}
        <aside className="hidden lg:block w-52 shrink-0 border-r border-canvas-border sticky top-14 h-[calc(100vh-3.5rem)] overflow-y-auto py-6 px-4">
          <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-3 font-semibold">Contents</div>
          <nav className="space-y-1">
            {TOC.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                className="block text-[12px] text-slate-500 hover:text-canvas-accent py-1 transition-colors"
              >
                {item.label}
              </a>
            ))}
          </nav>
        </aside>

        {/* ── Main content ───────────────────────────────────────────── */}
        <main className="flex-1 max-w-[820px] mx-auto px-6 py-10">
          {/* Header */}
          <h1 className="text-2xl font-bold text-slate-100 mb-2">Instructions</h1>
          <p className="text-sm text-slate-400 mb-6 max-w-lg">
            Use ArchTwin to model architecture, test what-if changes,
            run simulations, and promote safe designs through Git PR.
          </p>

          {/* Workflow strip */}
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500 mb-8 flex-wrap">
            {['Import / Draw', 'Sandbox Layer', 'Goal', 'Simulate', 'Review', 'Promote'].map((s, i) => (
              <span key={s} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-canvas-accent/40">&#8594;</span>}
                <span className="px-2 py-0.5 rounded bg-canvas-surface/50 border border-canvas-border/60 text-slate-400">{s}</span>
              </span>
            ))}
          </div>

          {/* ── Quick Start ────────────────────────────────────────────── */}
          <section id="quick-start" className="mb-10 scroll-mt-20">
            <SectionTitle>Quick Start</SectionTitle>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
              <QuickStep num={1} text="Open the demo Canvas or import YAML" />
              <QuickStep num={2} text="Create a What-if sandbox layer" />
              <QuickStep num={3} text="Run simulation with an optimization goal" />
              <QuickStep num={4} text="Review veto gates and required actions" />
            </div>
            <div className="flex gap-3">
              <Link to="/canvas" className="text-[12px] px-4 py-2 bg-canvas-accent text-white rounded-lg font-medium hover:bg-canvas-accent/80 transition-colors">
                Open Demo Canvas
              </Link>
              <CopyButton text={MINIMAL_YAML} label="Copy Example YAML" />
            </div>
          </section>

          {/* ── Baseline vs Sandbox ────────────────────────────────────── */}
          <section id="baseline-sandbox" className="mb-10 scroll-mt-20">
            <SectionTitle>Baseline vs Sandbox</SectionTitle>
            <div className="bg-canvas-surface/50 border border-canvas-border rounded-xl p-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <div className="text-xs font-semibold text-slate-200 mb-1.5 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-status-pass" /> Baseline
                  </div>
                  <p className="text-[12px] text-slate-400 leading-relaxed">
                    Your current production architecture. Read-only reference. Never modified by Canvas edits.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-200 mb-1.5 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-purple-400" /> Sandbox
                  </div>
                  <p className="text-[12px] text-slate-400 leading-relaxed">
                    What-if proposals. Isolated from production. Editable. Promotion creates an isa.yaml patch and ADR draft through Git PR.
                  </p>
                </div>
              </div>
              <NoteCard className="mt-4">
                Editing a sandbox never changes production. Promotion always goes through Git PR.
              </NoteCard>
            </div>
          </section>

          {/* ── Step 1: Import / Draw ──────────────────────────────────── */}
          <StepCard id="step-import" number={1} title="Import or Draw Your Architecture" badge="Beginner">
            <p>Two options:</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li><strong>Import YAML</strong> — click &quot;Import YAML&quot; in the toolbar and paste your architecture description</li>
              <li><strong>Draw on Canvas</strong> — drag components from the left palette onto the canvas, then connect them</li>
            </ul>
            <YamlExample />
          </StepCard>

          {/* ── Step 2: Sandbox ────────────────────────────────────────── */}
          <StepCard id="step-sandbox" number={2} title="Create a Sandbox Layer" badge="Beginner">
            <p>
              Click <Code>+ Layer</Code> in the toolbar to create a new what-if layer.
              You can have multiple layers to compare different approaches.
            </p>
            <p className="mt-2">
              Example: &quot;Layer A — Replace PostgreSQL with Aurora Serverless&quot; vs
              &quot;Layer B — Add read replicas&quot;
            </p>
          </StepCard>

          {/* ── Step 3: Goal ───────────────────────────────────────────── */}
          <StepCard id="step-goal" number={3} title="Select Optimization Goal" badge="Recommended">
            <p>Switch to the <strong>Simulation</strong> tab and choose a goal:</p>
            <div className="grid grid-cols-2 gap-2 mt-3">
              <GoalCard label="Balanced" desc="Equal weight on all factors" />
              <GoalCard label="Cost Efficiency" desc="Minimize TCO and egress" />
              <GoalCard label="Max Reliability" desc="Maximize uptime and redundancy" />
              <GoalCard label="Min Complexity" desc="Reduce operational burden" />
            </div>
          </StepCard>

          {/* ── Step 4: Simulate ───────────────────────────────────────── */}
          <StepCard id="step-simulate" number={4} title="Run Simulation" badge="Recommended">
            <p>
              Select layers for comparison (click the <Code>&#8652;</Code> icon), then press <strong>Run Simulation</strong>.
              The AI pipeline runs four reviewers in parallel:
            </p>
            <div className="grid grid-cols-2 gap-2 mt-3">
              {[
                { label: 'Cost', desc: 'TCO, egress, cache hit ratio', color: 'text-amber-400' },
                { label: 'Performance', desc: 'Latency, throughput, bottlenecks', color: 'text-cyan-400' },
                { label: 'Security', desc: 'Trust boundaries, PII, compliance', color: 'text-red-400' },
                { label: 'Blast Radius', desc: 'Impacted stable components', color: 'text-purple-400' },
              ].map((r) => (
                <div key={r.label} className="bg-canvas-bg/80 border border-canvas-border rounded-lg p-3">
                  <div className={`text-xs font-semibold ${r.color} mb-0.5`}>{r.label}</div>
                  <div className="text-[11px] text-slate-500">{r.desc}</div>
                </div>
              ))}
            </div>
          </StepCard>

          {/* ── Step 5: Results ─────────────────────────────────────────── */}
          <StepCard id="step-results" number={5} title="Review Results" badge="Recommended">
            <p>The <strong>Results</strong> tab shows:</p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li><strong>Trade-off Matrix</strong> — score comparison across all factors</li>
              <li><strong>Fidelity Report</strong> — data freshness and confidence level</li>
              <li><strong>Veto Gates</strong> — PASS/FAIL for security, reliability, compliance</li>
              <li><strong>Required Actions</strong> — ranked todo list by role</li>
              <li><strong>Blast Radius</strong> — overlay on canvas showing impacted nodes</li>
            </ul>

            {/* Mini simulation result example */}
            <div className="mt-4 bg-canvas-bg/80 border border-canvas-border rounded-lg p-4">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Example Result</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12px]">
                <span className="text-slate-500">Recommendation</span>
                <span className="text-status-fail font-semibold">BLOCKED</span>
                <span className="text-slate-500">Reason</span>
                <span className="text-slate-300">Reliability gate failed</span>
                <span className="text-slate-500">Confidence</span>
                <span className="text-slate-300">80%</span>
                <span className="text-slate-500">Score</span>
                <span className="text-status-fail font-mono">0.00</span>
                <span className="text-slate-500">Required Action</span>
                <span className="text-slate-300">Fix throughput regression before promotion</span>
              </div>
            </div>
          </StepCard>

          {/* ── Step 6: Promote ─────────────────────────────────────────── */}
          <StepCard id="step-promote" number={6} title="Promote to PR" badge="Optional">
            <p>
              If all veto gates pass and confidence is sufficient (&gt;65%), you can promote the layer. This generates:
            </p>
            <ul className="list-disc list-inside mt-2 space-y-1">
              <li><Code>isa.yaml</Code> patch with all architecture changes</li>
              <li>ADR (Architecture Decision Record) draft</li>
              <li>PR description ready for Git</li>
            </ul>
            <NoteCard className="mt-3">
              Canvas never mutates production directly. Promotion always goes through Git PR.
            </NoteCard>
          </StepCard>

          {/* ── YAML Reference ─────────────────────────────────────────── */}
          <section id="yaml-ref" className="mb-10 scroll-mt-20">
            <SectionTitle>YAML Format Reference</SectionTitle>
            <div className="bg-canvas-surface/50 border border-canvas-border rounded-xl p-4 overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-slate-500 border-b border-canvas-border">
                    <th className="text-left py-1.5 pr-4">Field</th>
                    <th className="text-left py-1.5 pr-4">Values</th>
                    <th className="text-left py-1.5">Required</th>
                  </tr>
                </thead>
                <tbody className="text-slate-400">
                  <RefRow field="type" values="service, data_store, cache, queue, gateway, external_system" req="Yes" />
                  <RefRow field="tier" values="tier_1, standard, auxiliary" req="No (default: standard)" />
                  <RefRow field="technology" values="Any string (postgresql, redis, fastapi, etc.)" req="No" />
                  <RefRow field="criticality" values="high, medium, low" req="No (default: medium)" />
                  <RefRow field="data_classification" values="public, internal, confidential, restricted" req="No" />
                  <RefRow field="metrics" values="p99_latency_ms, requests_per_second, error_rate, etc." req="No" />
                  <RefRow field="relation type" values="synchronous, asynchronous, data_access, streaming, batch" req="No (default: synchronous)" />
                  <RefRow field="protocol" values="HTTPS, gRPC, PostgreSQL, Redis, SQS, etc." req="No" />
                  <RefRow field="crosses_trust_boundary" values="true / false" req="No (default: false)" />
                </tbody>
              </table>
            </div>
          </section>

          {/* ── Best Practices ──────────────────────────────────────────── */}
          <section id="best-practices" className="mb-10 scroll-mt-20">
            <SectionTitle>Best Practices</SectionTitle>
            <div className="space-y-2">
              <Tip text="Add observed metrics (latency, RPS) for more accurate simulation results" />
              <Tip text='Mark external services as external_system with crosses_trust_boundary for security analysis' />
              <Tip text="Use tier_1 only for critical shared components (DB, auth, core API)" />
              <Tip text="Compare at least two layers for the trade-off matrix to be useful" />
              <Tip text="Keep metrics fresh — stale data (>7 days) creates exploratory estimates and blocks promotion" />
              <Tip text="Use descriptive layer names that include the change (e.g. 'Replace RDS with Aurora Serverless')" />
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}

// ── Shared components ─────────────────────────────────────────────────────────

function Nav() {
  return (
    <nav className="h-14 border-b border-canvas-border flex items-center px-6 shrink-0 sticky top-0 z-50 bg-canvas-bg/80 backdrop-blur-sm">
      <Link to="/" className="text-canvas-accent font-bold font-mono text-lg">ArchTwin</Link>
      <div className="flex-1" />
      <Link to="/about" className="text-xs text-slate-400 hover:text-slate-200 mr-4">About</Link>
      <Link to="/canvas" className="text-xs px-3 py-1.5 bg-canvas-accent text-white rounded-lg hover:bg-canvas-accent/80 transition-colors">
        Open Canvas
      </Link>
    </nav>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-sm font-bold text-slate-200 mb-4 uppercase tracking-wide">{children}</h2>
  )
}

function QuickStep({ num, text }: { num: number; text: string }) {
  return (
    <div className="flex items-center gap-3 bg-canvas-surface/40 border border-canvas-border/60 rounded-lg px-3 py-2.5">
      <span className="w-6 h-6 shrink-0 rounded-full bg-canvas-accent/15 text-canvas-accent text-[11px] font-bold flex items-center justify-center">
        {num}
      </span>
      <span className="text-[12px] text-slate-300">{text}</span>
    </div>
  )
}

function StepCard({ id, number, title, badge, children }: {
  id: string; number: number; title: string; badge: string; children: React.ReactNode
}) {
  const badgeColor: Record<string, string> = {
    Beginner: 'bg-canvas-accent/10 text-canvas-accent border-canvas-accent/20',
    Recommended: 'bg-status-pass/10 text-status-pass border-status-pass/20',
    Advanced: 'bg-purple-500/10 text-purple-400 border-purple-500/20',
    Optional: 'bg-slate-500/10 text-slate-400 border-slate-500/20',
  }

  return (
    <section id={id} className="mb-6 scroll-mt-20">
      <div className="bg-canvas-surface/30 border border-canvas-border rounded-xl p-5">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-8 h-8 shrink-0 rounded-lg bg-canvas-accent/15 text-canvas-accent flex items-center justify-center text-sm font-bold">
            {number}
          </div>
          <h3 className="text-sm font-semibold text-slate-200 flex-1">{title}</h3>
          <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${badgeColor[badge] ?? badgeColor.Beginner}`}>
            {badge}
          </span>
        </div>
        <div className="text-[12px] text-slate-400 leading-relaxed space-y-1 pl-11">{children}</div>
      </div>
    </section>
  )
}

function GoalCard({ label, desc }: { label: string; desc: string }) {
  return (
    <div className="bg-canvas-bg/80 border border-canvas-border rounded-lg p-3">
      <div className="text-xs font-semibold text-slate-200 mb-0.5">{label}</div>
      <div className="text-[11px] text-slate-500">{desc}</div>
    </div>
  )
}

function NoteCard({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`flex items-start gap-2.5 bg-status-warn/5 border border-status-warn/20 rounded-lg px-3.5 py-2.5 ${className}`}>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-warn shrink-0 mt-0.5">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
      <span className="text-[11px] text-slate-400 leading-relaxed">{children}</span>
    </div>
  )
}

function Tip({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2.5 bg-canvas-surface/40 border border-canvas-border/60 rounded-lg px-3.5 py-2.5">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-status-pass shrink-0 mt-0.5">
        <polyline points="20 6 9 17 4 12" />
      </svg>
      <span className="text-[12px] text-slate-400">{text}</span>
    </div>
  )
}

function RefRow({ field, values, req }: { field: string; values: string; req: string }) {
  return (
    <tr className="border-b border-canvas-border/40 last:border-0">
      <td className="py-1.5 pr-4 font-mono text-slate-300">{field}</td>
      <td className="py-1.5 pr-4">{values}</td>
      <td className="py-1.5">{req}</td>
    </tr>
  )
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="px-1.5 py-0.5 bg-canvas-bg rounded text-[11px] text-canvas-accent/80 border border-canvas-border/60">{children}</code>
  )
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => { /* ignore */ })
  }, [text])

  return (
    <button
      onClick={handleCopy}
      className="text-[12px] px-4 py-2 border border-canvas-border text-slate-300 rounded-lg hover:border-slate-500 transition-colors flex items-center gap-1.5"
    >
      {copied ? (
        <>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-pass">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          Copied
        </>
      ) : (
        <>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-slate-400">
            <rect x="9" y="9" width="13" height="13" rx="2" />
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
          </svg>
          {label}
        </>
      )}
    </button>
  )
}

// ── YAML Example with tabs + copy ─────────────────────────────────────────────

const MINIMAL_YAML = `name: "My System"

components:
  - name: "API Gateway"
    type: "gateway"
    technology: "kong"
    tier: "tier_1"

  - name: "Users DB"
    type: "data_store"
    technology: "postgresql"
    tier: "tier_1"

relations:
  - source: "API Gateway"
    target: "Users DB"
    type: "synchronous"
    protocol: "HTTPS"`

const FULL_YAML = `name: "E-Commerce Platform"

components:
  - name: "API Gateway"
    type: "gateway"
    technology: "kong"
    tier: "tier_1"
    metrics:
      p99_latency_ms: 12
      requests_per_second: 25000

  - name: "Orders API"
    type: "service"
    technology: "fastapi"
    tier: "standard"
    metrics:
      p99_latency_ms: 45
      requests_per_second: 3000

  - name: "Orders DB"
    type: "data_store"
    technology: "postgresql"
    tier: "tier_1"
    data_classification: "confidential"
    metrics:
      p99_latency_ms: 8
      requests_per_second: 12000

  - name: "Redis Sessions"
    type: "cache"
    technology: "redis"
    tier: "standard"

  - name: "Stripe"
    type: "external_system"
    technology: "stripe-api"
    tier: "auxiliary"

relations:
  - source: "API Gateway"
    target: "Orders API"
    type: "synchronous"
    protocol: "HTTPS"

  - source: "Orders API"
    target: "Orders DB"
    type: "data_access"
    protocol: "PostgreSQL"

  - source: "Orders API"
    target: "Redis Sessions"
    type: "synchronous"
    protocol: "Redis"

  - source: "Orders API"
    target: "Stripe"
    type: "synchronous"
    protocol: "HTTPS"
    crosses_trust_boundary: true`

function YamlExample() {
  const [tab, setTab] = useState<'minimal' | 'full'>('minimal')
  const yaml = tab === 'minimal' ? MINIMAL_YAML : FULL_YAML

  return (
    <div className="mt-3 rounded-xl border border-canvas-border overflow-hidden bg-canvas-bg">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-canvas-border bg-canvas-surface/40">
        <div className="flex gap-1">
          <TabBtn active={tab === 'minimal'} onClick={() => setTab('minimal')}>Minimal</TabBtn>
          <TabBtn active={tab === 'full'} onClick={() => setTab('full')}>Full</TabBtn>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-600 font-mono">architecture.yaml</span>
          <CopyButton text={yaml} label="Copy" />
        </div>
      </div>
      <pre className="p-3 text-[11px] font-mono text-slate-400 overflow-x-auto max-h-64 overflow-y-auto leading-relaxed">
        {yaml}
      </pre>
    </div>
  )
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
        active
          ? 'bg-canvas-accent/15 text-canvas-accent font-medium'
          : 'text-slate-500 hover:text-slate-300'
      }`}
    >
      {children}
    </button>
  )
}
