import { Link } from 'react-router-dom'

export function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas-bg flex flex-col overflow-x-hidden">
      {/* Nav */}
      <nav className="h-14 border-b border-canvas-border flex items-center px-6 backdrop-blur-sm bg-canvas-bg/80 sticky top-0 z-50">
        <span className="text-canvas-accent font-bold font-mono text-lg">ArchTwin</span>
        <div className="flex-1" />
        <a href="#how-it-works" className="text-sm text-slate-400 hover:text-slate-200 mr-5">How It Works</a>
        <Link to="/canvas" className="text-sm text-slate-400 hover:text-slate-200 mr-5">Demo</Link>
        <Link to="/instructions" className="text-sm text-slate-400 hover:text-slate-200 mr-5">Docs</Link>
        <Link to="/pricing" className="text-sm text-slate-400 hover:text-slate-200 mr-5">Pricing</Link>
        <Link to="/login" className="text-sm text-slate-400 hover:text-slate-200 mr-4">Sign In</Link>
        <Link to="/register" className="text-sm px-4 py-1.5 bg-canvas-accent text-white rounded-lg hover:bg-canvas-accent/80 transition-colors">
          Get Started
        </Link>
      </nav>

      <main className="flex-1">
        {/* ── Hero Section ─────────────────────────────────────────────── */}
        <section className="relative py-20 px-6">
          {/* Background effects */}
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(79,110,247,0.1)_0%,_transparent_65%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(rgba(45,49,72,0.3)_1px,transparent_1px),linear-gradient(90deg,rgba(45,49,72,0.3)_1px,transparent_1px)] bg-[size:60px_60px] opacity-40" />
          <div className="absolute top-16 left-1/4 w-96 h-48 bg-canvas-accent/6 blur-[100px] rounded-full pointer-events-none" />

          <div className="relative max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
            {/* Hero Left */}
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-canvas-border bg-canvas-surface/50 text-[11px] text-slate-400 mb-6">
                <span className="w-2 h-2 rounded-full bg-status-pass animate-pulse" />
                Decision-grade architecture simulation
              </div>

              <h1 className="text-4xl lg:text-5xl font-bold text-slate-100 leading-[1.15] mb-5">
                <span className="text-canvas-accent">AI-native</span> CAD for<br />
                software architecture
              </h1>

              <p className="text-[15px] text-slate-400 leading-relaxed mb-8 max-w-lg">
                Model your system on a visual Canvas, compare what-if scenarios,
                and simulate cost, performance, security, and blast radius before deployment.
              </p>

              <div className="flex flex-wrap gap-3">
                <Link
                  to="/canvas"
                  className="px-7 py-3 bg-canvas-accent text-white rounded-lg font-semibold hover:bg-canvas-accent/80 transition-all shadow-lg shadow-canvas-accent/20 hover:shadow-canvas-accent/40"
                >
                  Try Demo Canvas
                </Link>
                <a
                  href="#how-it-works"
                  className="px-7 py-3 border border-canvas-border text-slate-300 rounded-lg hover:border-slate-500 transition-colors"
                >
                  See How It Works
                </a>
              </div>
            </div>

            {/* Hero Right — Product Preview */}
            <div className="relative lg:translate-x-4">
              <div className="absolute -inset-8 bg-canvas-accent/8 rounded-3xl blur-[60px] -z-10" />

              <div className="rounded-xl border border-canvas-accent/20 bg-canvas-surface/60 shadow-2xl shadow-canvas-accent/10 overflow-hidden backdrop-blur-sm">
                <div className="h-9 bg-canvas-bg border-b border-canvas-border flex items-center px-3 gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
                  <div className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
                  <span className="ml-3 text-[10px] text-slate-500 font-mono">ArchTwin Canvas — Cost View</span>
                </div>

                <div className="p-5 relative h-80 bg-canvas-bg">
                  <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(79,110,247,0.12)_1px,transparent_1px)] bg-[size:18px_18px]" />

                  <MockNode x={8} y={12} label="API Gateway" tier="1" cost="$420/mo" />
                  <MockNode x={50} y={6} label="Orders API" tier="standard" cost="$180/mo" />
                  <MockNode x={50} y={42} label="Payments API" tier="1" cost="$310/mo" />
                  <MockNode x={8} y={52} label="Redis Cache" tier="standard" cost="$95/mo" />
                  <MockNode x={50} y={75} label="Inventory Svc" tier="standard" cost="$140/mo" />

                  <svg className="absolute inset-0 w-full h-full pointer-events-none">
                    <line x1="28%" y1="24%" x2="50%" y2="18%" stroke="rgba(79,110,247,0.35)" strokeWidth="1.5" strokeDasharray="4 3" />
                    <line x1="28%" y1="24%" x2="50%" y2="54%" stroke="rgba(79,110,247,0.35)" strokeWidth="1.5" strokeDasharray="4 3" />
                    <line x1="28%" y1="64%" x2="50%" y2="18%" stroke="rgba(245,158,11,0.35)" strokeWidth="1.5" strokeDasharray="4 3" />
                    <line x1="50%" y1="54%" x2="50%" y2="87%" stroke="rgba(79,110,247,0.25)" strokeWidth="1.5" strokeDasharray="4 3" />
                  </svg>

                  <div className="absolute bottom-3 right-3 bg-canvas-surface/95 border border-canvas-border rounded-lg px-3 py-2.5 shadow-xl">
                    <div className="text-[9px] text-slate-500 uppercase tracking-wider mb-1">Simulation Result</div>
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-status-fail animate-pulse" />
                      <span className="text-[11px] font-bold text-status-fail">BLOCKED</span>
                      <span className="text-[10px] text-slate-500">reliability veto</span>
                    </div>
                  </div>

                  <div className="absolute top-3 right-3 bg-canvas-surface/95 border border-canvas-border rounded-lg px-2.5 py-1.5 shadow-lg">
                    <div className="text-[9px] text-slate-500 mb-1">Veto Gates</div>
                    <div className="flex gap-2 text-[10px] font-semibold">
                      <span className="text-status-pass">SEC</span>
                      <span className="text-status-fail">REL</span>
                      <span className="text-status-pass">CMP</span>
                      <span className="text-status-pass">FID</span>
                    </div>
                  </div>

                  <div className="absolute bottom-3 left-3 bg-canvas-surface/95 border border-canvas-border rounded px-2 py-1 shadow-lg">
                    <div className="text-[9px] text-slate-500">Cost Delta</div>
                    <div className="text-[11px] text-status-warn font-semibold">+$245/mo</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Problem Statement ────────────────────────────────────────── */}
        <section className="py-14 px-6 border-t border-canvas-border/50">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-lg font-bold text-slate-200 text-center mb-8">
              Why architecture teams need ArchTwin
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
              <ProblemCard text="Architecture diagrams go stale within weeks of creation" />
              <ProblemCard text="Cloud costs drift silently until the invoice arrives" />
              <ProblemCard text="Dependencies become hidden risks nobody tracks" />
              <ProblemCard text="Security issues surface after deployment, not before" />
            </div>

            <div className="text-center">
              <div className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-status-pass/5 border border-status-pass/20">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-status-pass">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span className="text-sm text-slate-300 font-medium">
                  ArchTwin catches these risks <span className="text-status-pass">before</span> production.
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ── How It Works ─────────────────────────────────────────────── */}
        <section id="how-it-works" className="py-16 px-6 border-t border-canvas-border/50 bg-canvas-surface/20 scroll-mt-16">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-lg font-bold text-slate-200 text-center mb-2">How ArchTwin works</h2>
            <p className="text-sm text-slate-500 text-center mb-12 max-w-md mx-auto">
              From diagram to decision in four steps.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-5 relative">
              {/* Connector line (desktop) */}
              <div className="hidden md:block absolute top-[26px] left-[14%] right-[14%] h-[2px] bg-gradient-to-r from-canvas-accent/10 via-canvas-accent/40 to-canvas-accent/10" />

              <HowStep
                number={1}
                title="Model"
                description="Create or import a C4-style architecture graph."
                icon={<CanvasIcon />}
                color="text-canvas-accent"
                bg="bg-canvas-accent/10 border-canvas-accent/30"
              />
              <HowStep
                number={2}
                title="Sandbox"
                description="Test alternatives in isolated what-if layers."
                icon={<LayersIcon />}
                color="text-purple-400"
                bg="bg-purple-400/10 border-purple-400/30"
              />
              <HowStep
                number={3}
                title="Simulate"
                description="Run cost, performance, security, and blast-radius reviewers."
                icon={<SimIcon />}
                color="text-cyan-400"
                bg="bg-cyan-400/10 border-cyan-400/30"
              />
              <HowStep
                number={4}
                title="Decide"
                description="Get veto gates, confidence score, required actions, and patches."
                icon={<OutputIcon />}
                color="text-status-pass"
                bg="bg-status-pass/10 border-status-pass/30"
              />
            </div>
          </div>
        </section>

        {/* ── Feature Cards (6) ────────────────────────────────────────── */}
        <section className="py-16 px-6 border-t border-canvas-border/50">
          <div className="max-w-5xl mx-auto">
            <h2 className="text-lg font-bold text-slate-200 text-center mb-2">From diagramming to decision-grade simulation</h2>
            <p className="text-sm text-slate-500 text-center mb-10 max-w-lg mx-auto">
              Every feature turns vague architecture discussions into quantified, reviewable decisions.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <FeatureCard
                icon={<CanvasIcon />}
                title="Visual Architecture Canvas"
                description="Design systems as living C4-style graphs with components, dependencies, and tiers."
                accent="blue"
              />
              <FeatureCard
                icon={<LayersIcon />}
                title="What-if Layers"
                description="Compare multiple architecture proposals side by side without affecting baseline."
                accent="purple"
              />
              <FeatureCard
                icon={<SimIcon />}
                title="Parallel Simulation"
                description="Run cost, performance, and security reviewers in parallel before implementation."
                accent="cyan"
              />
              <FeatureCard
                icon={<ShieldIcon />}
                title="Veto Gates"
                description="Block unsafe designs automatically with security, reliability, and compliance checks."
                accent="red"
              />
              <FeatureCard
                icon={<BlastIcon />}
                title="Blast Radius"
                description="See which stable components are impacted by a proposed change, weighted by tier."
                accent="amber"
              />
              <FeatureCard
                icon={<OutputIcon />}
                title="Decision Output"
                description="Generate required actions, ADR drafts, and isa.yaml patches ready for review."
                accent="green"
              />
            </div>
          </div>
        </section>

        {/* ── Veto Gates Demo ──────────────────────────────────────────── */}
        <section className="py-14 px-6 border-t border-canvas-border/50 bg-canvas-surface/20">
          <div className="max-w-4xl mx-auto text-center">
            <h2 className="text-lg font-bold text-slate-200 mb-2">Non-linear Veto Gates</h2>
            <p className="text-sm text-slate-500 mb-8 max-w-lg mx-auto">
              Security, reliability, compliance, and fidelity gates run in parallel.
              One critical failure blocks promotion, even if other metrics improve.
            </p>

            <div className="inline-flex gap-3 flex-wrap justify-center mb-6">
              <GateBadge label="Security" status="pass" />
              <GateBadge label="Reliability" status="fail" />
              <GateBadge label="Compliance" status="pass" />
              <GateBadge label="Fidelity" status="pass" />
            </div>

            {/* Recommendation score card */}
            <div className="max-w-xs mx-auto bg-canvas-bg/80 border border-canvas-border rounded-lg px-4 py-3 text-left">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider">Recommendation Score</span>
                <span className="text-lg font-bold text-status-fail font-mono">0.00</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-500">Blocked by</span>
                <span className="text-status-fail font-medium">Reliability Gate</span>
              </div>
              <div className="flex items-center justify-between text-[11px] mt-1">
                <span className="text-slate-500">Promotion</span>
                <span className="text-status-fail/80">disabled</span>
              </div>
            </div>
          </div>
        </section>

        {/* ── Final CTA ────────────────────────────────────────────────── */}
        <section className="py-16 px-6 border-t border-canvas-border/50 relative">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_rgba(79,110,247,0.06)_0%,_transparent_70%)]" />
          <div className="relative max-w-xl mx-auto text-center">
            <h2 className="text-xl font-bold text-slate-200 mb-3">Ready to try it?</h2>
            <p className="text-sm text-slate-500 mb-8 leading-relaxed">
              Open a pre-loaded architecture, switch to Cost View, run a simulation,
              and see why the proposal is blocked.
            </p>
            <Link
              to="/canvas"
              className="inline-block px-8 py-3 bg-canvas-accent text-white rounded-lg font-semibold hover:bg-canvas-accent/80 transition-all shadow-lg shadow-canvas-accent/20 hover:shadow-canvas-accent/40"
            >
              Try Demo Canvas
            </Link>
          </div>
        </section>
      </main>

      {/* ── Footer ─────────────────────────────────────────────────────── */}
      <footer className="border-t border-canvas-border py-6 px-6">
        <div className="max-w-5xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="text-canvas-accent font-bold font-mono text-sm">ArchTwin</span>
            <span className="text-[11px] text-slate-600">v0.6.0</span>
          </div>
          <p className="text-[11px] text-slate-600">AI-native CAD for software architecture decisions</p>
          <div className="flex gap-4 text-[11px] text-slate-500">
            <Link to="/instructions" className="hover:text-slate-300 transition-colors">Docs</Link>
            <Link to="/about" className="hover:text-slate-300 transition-colors">About</Link>
            <span className="text-slate-700">|</span>
            <span className="text-slate-600">Privacy</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MockNode({ x, y, label, tier, cost }: { x: number; y: number; label: string; tier: string; cost: string }) {
  const borderColor = tier === '1' ? 'border-tier-1/60' : 'border-canvas-border'
  const tierBadge = tier === '1' ? 'bg-tier-1/20 text-tier-1' : 'bg-canvas-accent/10 text-canvas-accent/70'

  return (
    <div
      className={`absolute rounded-md border ${borderColor} bg-canvas-surface px-2.5 py-2 shadow-lg`}
      style={{ left: `${x}%`, top: `${y}%` }}
    >
      <div className="text-[11px] text-slate-300 font-medium whitespace-nowrap">{label}</div>
      <div className="flex items-center gap-1.5 mt-0.5">
        <span className={`text-[9px] px-1 rounded ${tierBadge}`}>{tier === '1' ? 'T1' : 'STD'}</span>
        <span className="text-[9px] text-status-warn font-medium">{cost}</span>
      </div>
    </div>
  )
}

function ProblemCard({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-3 bg-canvas-surface/40 border border-canvas-border/60 rounded-lg px-4 py-3">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-status-fail shrink-0 mt-0.5">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
      <span className="text-sm text-slate-400">{text}</span>
    </div>
  )
}

function HowStep({ number, title, description, icon, color, bg }: {
  number: number; title: string; description: string;
  icon: React.ReactNode; color: string; bg: string
}) {
  return (
    <div className="text-center relative">
      <div className={`w-[52px] h-[52px] mx-auto mb-4 rounded-xl ${bg} border flex flex-col items-center justify-center relative z-10`}>
        <div className={`${color} mb-0.5`}>{icon}</div>
        <span className={`text-[9px] font-bold ${color} opacity-70`}>{number}</span>
      </div>
      <h3 className="text-sm font-bold text-slate-200 mb-1">{title}</h3>
      <p className="text-[12px] text-slate-500 leading-relaxed">{description}</p>
    </div>
  )
}

const ACCENT_STYLES: Record<string, { iconBg: string; iconBorder: string; iconColor: string; hoverBorder: string }> = {
  blue:   { iconBg: 'bg-blue-500/10',   iconBorder: 'border-blue-500/20',   iconColor: 'text-blue-400',   hoverBorder: 'hover:border-blue-500/30' },
  purple: { iconBg: 'bg-purple-500/10', iconBorder: 'border-purple-500/20', iconColor: 'text-purple-400', hoverBorder: 'hover:border-purple-500/30' },
  cyan:   { iconBg: 'bg-cyan-500/10',   iconBorder: 'border-cyan-500/20',   iconColor: 'text-cyan-400',   hoverBorder: 'hover:border-cyan-500/30' },
  red:    { iconBg: 'bg-red-500/10',     iconBorder: 'border-red-500/20',     iconColor: 'text-red-400',     hoverBorder: 'hover:border-red-500/30' },
  amber:  { iconBg: 'bg-amber-500/10', iconBorder: 'border-amber-500/20', iconColor: 'text-amber-400', hoverBorder: 'hover:border-amber-500/30' },
  green:  { iconBg: 'bg-emerald-500/10', iconBorder: 'border-emerald-500/20', iconColor: 'text-emerald-400', hoverBorder: 'hover:border-emerald-500/30' },
}

function FeatureCard({ icon, title, description, accent }: {
  icon: React.ReactNode; title: string; description: string; accent: string
}) {
  const s = ACCENT_STYLES[accent] ?? ACCENT_STYLES.blue

  return (
    <div className={`bg-canvas-surface/40 border border-canvas-border rounded-xl p-5 ${s.hoverBorder} transition-all group hover:bg-canvas-surface/60`}>
      <div className={`w-10 h-10 rounded-lg ${s.iconBg} border ${s.iconBorder} flex items-center justify-center mb-3 ${s.iconColor} transition-colors`}>
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-slate-200 mb-1.5">{title}</h3>
      <p className="text-[12px] text-slate-500 leading-relaxed">{description}</p>
    </div>
  )
}

function GateBadge({ label, status }: { label: string; status: 'pass' | 'fail' | 'warn' }) {
  const styles = {
    pass: 'border-status-pass/30 bg-status-pass/5 text-status-pass',
    fail: 'border-status-fail/30 bg-status-fail/5 text-status-fail',
    warn: 'border-status-warn/30 bg-status-warn/5 text-status-warn',
  }
  const icons = { pass: 'PASS', fail: 'FAIL', warn: 'WARN' }

  return (
    <div className={`px-4 py-2.5 rounded-lg border ${styles[status]} text-xs font-semibold`}>
      <span className="block text-[10px] opacity-60 mb-0.5">{label}</span>
      {icons[status]}
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────

function CanvasIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </svg>
  )
}

function LayersIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  )
}

function SimIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  )
}

function ShieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  )
}

function BlastIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="12" cy="12" r="3" />
      <circle cx="12" cy="12" r="7" opacity="0.6" />
      <circle cx="12" cy="12" r="10" opacity="0.3" />
    </svg>
  )
}

function OutputIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  )
}
