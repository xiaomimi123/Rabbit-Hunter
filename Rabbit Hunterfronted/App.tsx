import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { DashboardPage } from './components/pages-v4/DashboardPage';
import { PortfolioPage } from './components/pages-v4/PortfolioPage';
import { MarketPage } from './components/pages-v4/MarketPage';
import { HistoryPage } from './components/pages-v4/HistoryPage';
import { BacktestPage } from './components/pages-v4/BacktestPage';
import { ReliabilityPage } from './components/pages-v4/ReliabilityPage';
import { AuditPage } from './components/pages-v4/AuditPage';
import { DiagnosticsPage } from './components/pages-v4/DiagnosticsPage';
import { SettingsPage } from './components/pages-v4/SettingsPage';
import { V5ChartPage } from './components/pages/V5ChartPage';
import { V5ManualOrderPage } from './components/pages/V5ManualOrderPage';
import { V5GlossaryPage } from './components/pages/V5GlossaryPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route element={<AppShell />}>
          <Route path="/dashboard"   element={<DashboardPage />} />
          <Route path="/portfolio"   element={<PortfolioPage />} />
          <Route path="/market"      element={<MarketPage />} />
          <Route path="/history"     element={<HistoryPage />} />
          <Route path="/backtest"    element={<BacktestPage />} />
          <Route path="/reliability" element={<ReliabilityPage />} />
          <Route path="/audit"       element={<AuditPage />} />
          <Route path="/diagnostics" element={<DiagnosticsPage />} />
          <Route path="/settings"    element={<SettingsPage />} />
          <Route path="/chart/:symbol" element={<V5ChartPage />} />
          <Route path="/manual"      element={<V5ManualOrderPage />} />
          <Route path="/glossary"    element={<V5GlossaryPage />} />
        </Route>
        {/* Legacy URL redirects */}
        <Route path="/v5/dashboard"  element={<Navigate to="/dashboard" replace />} />
        <Route path="/v5/active"     element={<Navigate to="/portfolio" replace />} />
        <Route path="/v5/orders"     element={<Navigate to="/history" replace />} />
        <Route path="/v5/history"    element={<Navigate to="/history" replace />} />
        <Route path="/v5/signals"    element={<Navigate to="/diagnostics" replace />} />
        <Route path="/v5/ai"         element={<Navigate to="/diagnostics" replace />} />
        <Route path="/v5/reflection" element={<Navigate to="/audit" replace />} />
        <Route path="/v5/config"     element={<Navigate to="/settings" replace />} />
        <Route path="/v5/settings"   element={<Navigate to="/settings" replace />} />
        <Route path="/v5/manual"     element={<Navigate to="/manual" replace />} />
        <Route path="/v5/glossary"   element={<Navigate to="/glossary" replace />} />
        <Route path="/v5/chart/:symbol" element={<V5ChartPage />} />
        <Route path="*"              element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
