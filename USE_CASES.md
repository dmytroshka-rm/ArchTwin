# ArchTwin — Use Cases & Navigation Guide

## Site Map

```
/                 → Landing Page (public)
/about            → About Page (public)
/instructions     → Documentation (public)
/pricing          → Pricing & Plans (public)
/login            → Sign In (public)
/register         → Create Account (public)
/canvas           → Architecture Canvas (protected — requires auth)
/billing          → Billing Settings (protected)
```

---

## Use Case 1: New User — First Visit

**Goal:** Understand the product and try the demo.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Open site | `/` Landing | See hero, product preview, feature cards |
| 2 | Click "Try Demo Canvas" | Hero CTA | Navigate to `/canvas` |
| 3 | Redirected to `/login` | Auth page | Not logged in yet |
| 4 | Click "Create Account" | Login page | Navigate to `/register` |
| 5 | Fill email + password | Register form | Firebase creates account |
| 6 | Auto-redirect | → `/canvas` | Demo architecture loaded |

**Alternative path:**
- Landing → "See How It Works" → scrolls to `#how-it-works` section
- Landing → "Pricing" in nav → `/pricing` → compare plans → "Start Free"
- Landing → "Docs" in nav → `/instructions` → read workflow

---

## Use Case 2: Existing User — Daily Workflow

**Goal:** Open Canvas, make architecture changes, run simulation.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Sign in | `/login` | Email/password or Google |
| 2 | Canvas loads | `/canvas` | Firestore restores saved state |
| 3 | Drag component from palette | Left panel | New node on canvas |
| 4 | Connect nodes | Canvas | Draw edge between nodes |
| 5 | Click "+ Layer" | Layer bar | New sandbox layer created |
| 6 | Click "Run Simulation" | Top bar CTA | Simulation starts (SSE stream) |
| 7 | View results | Right panel → Decision Panel | Score, veto gates, actions |
| 8 | Switch to "Cost View" | Top bar view toggle | Cost annotations on nodes |

---

## Use Case 3: Import YAML Architecture

**Goal:** Load an existing architecture from YAML.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Click "Import YAML" | Top bar button | Modal opens |
| 2 | Paste YAML content | Text area in modal | Validates format |
| 3 | Click "Import" | Modal button | Layer created with components + relations |
| 4 | Auto-layout applied | Canvas | Nodes positioned in grid |
| 5 | Verify graph | Canvas | All components and edges visible |

**Where to get YAML example:**
- `/instructions` → Step 1 → YAML Example → "Minimal" or "Full" tab → "Copy" button

---

## Use Case 4: Compare What-if Scenarios

**Goal:** Compare two architecture alternatives.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Have baseline loaded | Canvas | E.g., "E-Commerce Baseline" |
| 2 | Click "+ Layer" | Layer bar | Creates "Layer A" |
| 3 | Make changes in Layer A | Canvas | E.g., replace PostgreSQL with Aurora |
| 4 | Click "+ Layer" again | Layer bar | Creates "Layer B" |
| 5 | Make different changes | Canvas | E.g., add read replicas |
| 6 | Click ⇄ on both layers | Layer bar (hover) | Both selected for comparison |
| 7 | Click "Run Simulation" | Top bar | Simulation compares both |
| 8 | View Trade-off Matrix | Decision Panel | Side-by-side scores |

---

## Use Case 5: Review Simulation Results

**Goal:** Understand why a simulation is BLOCKED and what to fix.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Simulation completes | Auto | Floating insights appear (bottom-left) |
| 2 | Click to expand insights | SimulationInsights card | Full result summary |
| 3 | See "BLOCKED — reliability fail" | Insights card | Red status, score 0.00 |
| 4 | Open Decision Panel | Right panel (auto-opens) | Full details |
| 5 | Check Veto Gates | Decision Panel → Gates section | SEC ✓, REL ✗, CMP ✓ |
| 6 | Scroll to Required Actions | Decision Panel → Actions | Ranked: BLOCKING → REQUIRED → RECOMMENDED |
| 7 | Fix the issue | Canvas | E.g., add throughput metrics |
| 8 | Re-run simulation | Top bar CTA | New run with fresh data |

---

## Use Case 6: Use AI Command Palette

**Goal:** Ask AI about the architecture.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Press `Ctrl+K` | Anywhere on Canvas | Command palette opens |
| 2 | Type question | Input field | E.g., "Compare Orders DB alternatives" |
| 3 | Press Enter | Palette | AI processes command |
| 4 | View structured response | Palette result area | Table/cards with analysis |
| 5 | Click suggestion button | Below result | Follow-up query auto-fills |

**Example queries:**
- "Optimize this layer for cost"
- "Show security risks for API Gateway"
- "What is the blast radius of changing Orders API?"
- "Explain why reliability gate failed"

---

## Use Case 7: Promote to PR

**Goal:** Generate ADR and isa.yaml patch from approved design.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Run simulation | Canvas | Result: all gates PASS |
| 2 | Confidence > 65% | Decision Panel | "Decision-grade · safe to promote" |
| 3 | Click "Promote to PR" | Decision Panel → Actions | Backend generates artifacts |
| 4 | View generated ADR | Expandable preview | Architecture Decision Record |
| 5 | View isa.yaml patch | Expandable preview | YAML diff for PR |

**Blocked scenario:**
- If gates fail → CTA shows "Resolve Blocker" (red)
- If plan is Free → Upgrade Modal opens → "Feature requires Team plan"

---

## Use Case 8: View Different Modes

**Goal:** Switch between topology, cost, security, and blast radius views.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Default view | Canvas | "Topology" — structural graph |
| 2 | Click "Cost View" | Top bar view switcher | Nodes show $/mo annotations |
| 3 | Click "Security View" | Top bar view switcher | Risk badges: LOW/MED/HIGH |
| 4 | Click "Blast Radius" | Top bar view switcher | Impact halos on nodes |
| 5 | Click "Topology" | Top bar view switcher | Back to structural view |

---

## Use Case 9: Upgrade Plan

**Goal:** User hits a limit and upgrades.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Try to create 2nd sandbox layer on Free | Canvas | Upgrade Modal appears |
| 2 | Modal shows "Feature: Create more sandbox layers" | Modal | "Available on Pro plan" |
| 3 | Click "Upgrade to Pro" | Modal button | Checkout initiated |
| 4 | Plan upgrades (simulated) | Backend | Subscription updated |
| 5 | Redirect to Canvas | `/canvas?upgraded=pro` | New limits active |

**Alternative path:**
- Nav → "Pricing" → `/pricing` → compare plans → choose plan → checkout
- Canvas → user bar → "Billing" → `/billing` → "Change Plan" → `/pricing`

---

## Use Case 10: Manage Billing

**Goal:** Check usage, manage subscription.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Click "Billing" in Canvas user bar | Top bar | Navigate to `/billing` |
| 2 | See current plan + status | Billing page | Plan badge + "Active" |
| 3 | Check usage bars | Usage section | Simulations: 42/300, Projects: 3/10 |
| 4 | Click "Manage Billing" | Button | Opens payment portal |
| 5 | Click "Change Plan" | Button | Navigate to `/pricing` |

---

## Use Case 11: Explore Documentation

**Goal:** Learn how to use ArchTwin.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Click "Docs" in any nav | Nav link | Navigate to `/instructions` |
| 2 | Use sidebar TOC | Left panel (desktop) | Jump to section |
| 3 | Read Quick Start | Top section | 4 steps overview |
| 4 | Read "Baseline vs Sandbox" | Section | Understand isolation model |
| 5 | Copy YAML example | Step 1 → "Copy" button | Clipboard filled |
| 6 | Switch to "Full" YAML | Tab in code block | See complete example |
| 7 | Click "Open Demo Canvas" | CTA button | Go to Canvas |

---

## Use Case 12: Delete Components

**Goal:** Remove a component from the Canvas.

| Step | Action | Where | Result |
|------|--------|-------|--------|
| 1 | Click on a node | Canvas | Node selected (blue ring) |
| 2 | Press `Delete` or `Backspace` | Keyboard | Node removed from canvas |
| 3 | Connected edges also removed | Canvas | Relations cleaned up |
| 4 | Firestore auto-saves | Background | Persisted in 2s |

**Note:** Delete is disabled when `editingBlocked=true` (backend incompatible or veto active).

---

## Navigation Quick Reference

### From Landing Page (`/`)
| Click | Goes to |
|-------|---------|
| "Try Demo Canvas" | `/canvas` (→ `/login` if not auth'd) |
| "See How It Works" | Scroll to `#how-it-works` |
| "How It Works" (nav) | Scroll to `#how-it-works` |
| "Demo" (nav) | `/canvas` |
| "Docs" (nav) | `/instructions` |
| "Pricing" (nav) | `/pricing` |
| "Sign In" (nav) | `/login` |
| "Get Started" (nav) | `/register` |

### From Canvas (`/canvas`)
| Click | Goes to |
|-------|---------|
| "Pricing" (user bar) | `/pricing` |
| "Billing" (user bar) | `/billing` |
| "Instructions" (user bar) | `/instructions` |
| "Sign Out" (user bar) | `/` |
| `Ctrl+K` | Opens Command Palette |

### From Pricing (`/pricing`)
| Click | Goes to |
|-------|---------|
| Plan CTA buttons | Checkout → upgrade → `/canvas` |
| "Enterprise" CTA | Opens email to sales |
| "About" (nav) | `/about` |
| "Docs" (nav) | `/instructions` |
| "Open Canvas" (nav) | `/canvas` |

### From Billing (`/billing`)
| Click | Goes to |
|-------|---------|
| "Change Plan" / "Upgrade" | `/pricing` |
| "Manage Billing" | Payment portal |
| "Pricing" (nav) | `/pricing` |

---

## Feature Gating Matrix

| Feature | Free | Pro | Team | Enterprise |
|---------|------|-----|------|------------|
| Demo Canvas | Y | Y | Y | Y |
| YAML Import | Y | Y | Y | Y |
| Simulations | 10/mo | 300/mo | 3,000/mo | Unlimited |
| Projects | 1 | 10 | 50 | Unlimited |
| Sandbox Layers | 1 | 5 | 20 | Unlimited |
| Nodes/Project | 15 | 100 | 500 | Unlimited |
| ADR Generation | - | Y | Y | Y |
| Promote to PR | - | - | Y | Y |
| Team Collaboration | - | - | Y | Y |
| Git Integration | - | - | Y | Y |
| SSO | - | - | - | Y |
| Audit Logs | - | - | - | Y |

When a gated feature is attempted on a lower plan, the **Upgrade Modal** opens automatically showing:
- Which feature is locked
- Which plan unlocks it
- "Upgrade" and "View plans" buttons
