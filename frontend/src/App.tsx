import { Routes, Route, Navigate } from 'react-router-dom'
import { LandingPage } from '@/pages/LandingPage'
import { AuthPage } from '@/pages/AuthPage'
import { AboutPage } from '@/pages/AboutPage'
import { InstructionsPage } from '@/pages/InstructionsPage'
import { CanvasPage } from '@/pages/CanvasPage'
import { PricingPage } from '@/pages/PricingPage'
import { BillingPage } from '@/pages/BillingPage'
import { UpgradeModal } from '@/components/billing/UpgradeModal'

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<AuthPage mode="login" />} />
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/instructions" element={<InstructionsPage />} />
        <Route path="/canvas" element={<CanvasPage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <UpgradeModal />
    </>
  )
}
