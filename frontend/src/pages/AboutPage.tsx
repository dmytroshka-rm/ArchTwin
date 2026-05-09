import { Link } from 'react-router-dom'
import { useState } from 'react'

export function AboutPage() {
  return (
    <div className="min-h-screen bg-canvas-bg flex flex-col">
      <Nav />

      <main className="flex-1">
        {/* ── Hero / Mission ───────────────────────────────────────────── */}
        <section className="py-16 px-6 border-b border-canvas-border/50 relative">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(79,110,247,0.06)_0%,_transparent_70%)]" />
          <div className="relative max-w-[780px] mx-auto text-center">
            <h1 className="text-2xl font-bold text-slate-100 mb-3">About ArchTwin</h1>
            <p className="text-base text-slate-300 leading-relaxed max-w-xl mx-auto">
              ArchTwin turns software architecture from static diagrams into decision-grade simulations.
            </p>
            <p className="text-sm text-slate-500 mt-3 max-w-lg mx-auto leading-relaxed">
              It helps teams model architecture changes, compare what-if scenarios, and understand
              cost, performance, security, reliability, and blast-radius impact before code is deployed.
            </p>
          </div>
        </section>

        <div className="max-w-[780px] mx-auto px-6">
          {/* ── Why It Exists ────────────────────────────────────────────── */}
          <section className="py-12 border-b border-canvas-border/40">
            <SectionTitle>Why ArchTwin exists</SectionTitle>
            <p className="text-sm text-slate-400 leading-relaxed mb-6">
              Architecture decisions are usually reviewed too late — after code is written,
              infrastructure is deployed, or costs have already changed.
              ArchTwin moves this review earlier by giving teams a living model and a simulation pipeline.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <PainPoint text="Architecture diagrams go stale within weeks" />
              <PainPoint text="Cloud costs grow silently until the invoice" />
              <PainPoint text="Dependencies create hidden blast radius" />
              <PainPoint text="Security issues appear after deployment" />
            </div>
          </section>

          {/* ── Who It Is For ────────────────────────────────────────────── */}
          <section className="py-12 border-b border-canvas-border/40">
            <SectionTitle>Built for</SectionTitle>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <PersonaCard
                title="Platform Teams"
                desc="Design infrastructure changes and simulate their impact before implementation."
                color="text-canvas-accent"
              />
              <PersonaCard
                title="Software Architects"
                desc="Compare trade-offs across proposals and document decisions with evidence."
                color="text-purple-400"
              />
              <PersonaCard
                title="Engineering Leads"
                desc="Reduce production risk and review architecture changes backed by simulation data."
                color="text-cyan-400"
              />
              <PersonaCard
                title="Security / Ops Teams"
                desc="Catch exposure, compliance, and reliability risks before deployment."
                color="text-status-warn"
              />
            </div>
          </section>

          {/* ── How It Works ─────────────────────────────────────────────── */}
          <section className="py-12 border-b border-canvas-border/40">
            <SectionTitle>How it works</SectionTitle>
            <div className="flex flex-col sm:flex-row items-stretch gap-2">
              {[
                { step: 'Canvas', desc: 'Draw or import architecture' },
                { step: 'Sandbox', desc: 'Create what-if layers' },
                { step: 'Simulate', desc: 'Run parallel reviewers' },
                { step: 'Decide', desc: 'Review veto gates & scores' },
                { step: 'Promote', desc: 'Generate PR with patch' },
              ].map((s, i) => (
                <div key={s.step} className="flex items-center flex-1 gap-2">
                  {i > 0 && <span className="text-canvas-accent/30 hidden sm:block text-lg">&#8594;</span>}
                  <div className="flex-1 bg-canvas-surface/40 border border-canvas-border/60 rounded-lg px-3 py-2.5 text-center">
                    <div className="text-xs font-semibold text-slate-200">{s.step}</div>
                    <div className="text-[10px] text-slate-500 mt-0.5">{s.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ── Core Capabilities ─────────────────────────────────────────── */}
          <section className="py-12 border-b border-canvas-border/40">
            <SectionTitle>Core capabilities</SectionTitle>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              <CapCard title="Cost Simulation" desc="TCO, egress, inter-region, cache hit ratio analysis" color="text-amber-400" />
              <CapCard title="Performance Review" desc="Latency delta, throughput ceiling, bottleneck detection" color="text-cyan-400" />
              <CapCard title="Security Review" desc="Trust boundaries, PII flows, compliance checks" color="text-red-400" />
              <CapCard title="Blast Radius" desc="Tier-aware impact: which stable components are affected?" color="text-purple-400" />
              <CapCard title="Fidelity Engine" desc="Data freshness scoring: decision-grade vs exploratory" color="text-status-pass" />
              <CapCard title="Decision Output" desc="Required actions, ADR drafts, isa.yaml patches" color="text-canvas-accent" />
            </div>
          </section>

          {/* ── Not Just Diagrams ─────────────────────────────────────────── */}
          <section className="py-12 border-b border-canvas-border/40">
            <SectionTitle>Not just a diagram tool</SectionTitle>
            <div className="bg-canvas-surface/40 border border-canvas-border rounded-xl p-5">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div>
                  <div className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Traditional diagrams</div>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    Describe what a system <em>looks like</em>. Go stale after creation.
                    No connection to cost, security, or reliability.
                  </p>
                </div>
                <div>
                  <div className="text-xs font-semibold text-canvas-accent uppercase tracking-wider mb-2">ArchTwin</div>
                  <p className="text-sm text-slate-400 leading-relaxed">
                    Predicts what a system <em>will do</em> when it changes.
                    Living model with simulation, veto gates, and confidence scoring.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ── Technical Foundation ──────────────────────────────────────── */}
          <section className="py-12 border-b border-canvas-border/40">
            <SectionTitle>Technical foundation</SectionTitle>
            <p className="text-sm text-slate-400 leading-relaxed mb-4">
              ArchTwin is built around a convention-driven architecture model.
              The frontend Canvas owns interaction and visualization.
              The backend owns simulation logic, veto gates, confidence scoring,
              blast-radius analysis, and promotion rules.
              This prevents UI and backend behavior from drifting apart.
            </p>

            {/* Tech stack tags */}
            <div className="flex flex-wrap gap-2 mb-4">
              {['React', 'TypeScript', 'React Flow', 'Tailwind CSS', 'FastAPI', 'LangGraph', 'Firebase', 'Zustand'].map((t) => (
                <span key={t} className="text-[11px] font-mono bg-canvas-surface/50 border border-canvas-border rounded px-2 py-1 text-slate-500">
                  {t}
                </span>
              ))}
            </div>

            {/* Collapsible pipeline */}
            <PipelineToggle />
          </section>

          {/* ── Bottom CTA ───────────────────────────────────────────────── */}
          <section className="py-14 text-center">
            <h2 className="text-lg font-bold text-slate-200 mb-2">Ready to explore ArchTwin?</h2>
            <p className="text-sm text-slate-500 mb-6">
              Open the Canvas with a pre-loaded architecture or read the full documentation.
            </p>
            <div className="flex justify-center gap-3">
              <Link
                to="/canvas"
                className="px-6 py-2.5 bg-canvas-accent text-white rounded-lg font-semibold text-sm hover:bg-canvas-accent/80 transition-all shadow-lg shadow-canvas-accent/20"
              >
                Open Canvas
              </Link>
              <Link
                to="/instructions"
                className="px-6 py-2.5 border border-canvas-border text-slate-300 rounded-lg text-sm hover:border-slate-500 transition-colors"
              >
                Read Instructions
              </Link>
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Nav() {
  return (
    <nav className="h-14 border-b border-canvas-border flex items-center px-6 shrink-0 sticky top-0 z-50 bg-canvas-bg/80 backdrop-blur-sm">
      <Link to="/" className="text-canvas-accent font-bold font-mono text-lg">ArchTwin</Link>
      <div className="flex-1" />
      <Link to="/instructions" className="text-xs text-slate-400 hover:text-slate-200 mr-4">Instructions</Link>
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

function PainPoint({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2.5 bg-canvas-surface/40 border border-canvas-border/60 rounded-lg px-3.5 py-2.5">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-fail shrink-0">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
      <span className="text-sm text-slate-400">{text}</span>
    </div>
  )
}

function PersonaCard({ title, desc, color }: { title: string; desc: string; color: string }) {
  return (
    <div className="bg-canvas-surface/40 border border-canvas-border/60 rounded-xl p-4">
      <div className={`text-sm font-semibold ${color} mb-1`}>{title}</div>
      <p className="text-[12px] text-slate-500 leading-relaxed">{desc}</p>
    </div>
  )
}

function CapCard({ title, desc, color }: { title: string; desc: string; color: string }) {
  return (
    <div className="bg-canvas-surface/40 border border-canvas-border/60 rounded-lg p-3.5">
      <div className={`text-xs font-semibold ${color} mb-0.5`}>{title}</div>
      <div className="text-[11px] text-slate-500 leading-relaxed">{desc}</div>
    </div>
  )
}

function PipelineToggle() {
  const [open, setOpen] = useState(false)

  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="text-[12px] text-slate-500 hover:text-slate-300 transition-colors flex items-center gap-1.5"
      >
        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`transition-transform ${open ? 'rotate-90' : ''}`}
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
        {open ? 'Hide' : 'Show'} AI pipeline details (17 nodes)
      </button>

      {open && (
        <div className="mt-3 bg-canvas-bg border border-canvas-border rounded-lg p-4 font-mono text-[11px] text-slate-500 leading-loose">
          context_freshness &rarr; build_design_delta &rarr; parallel_reviewer<br/>
          &rarr; [security_veto, reliability_veto, compliance_veto, fidelity_veto]<br/>
          &rarr; tradeoff_veto &rarr; blast_radius &rarr; calibration &rarr; state_persistence<br/>
          &rarr; reflect_decide &rarr; required_actions &rarr; isa_yaml_patch<br/>
          &rarr; sandbox_recommendation &rarr; human_review_gate
        </div>
      )}
    </div>
  )
}
