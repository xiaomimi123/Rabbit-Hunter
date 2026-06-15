import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { V5SignalsPage } from './components/pages/V5SignalsPage';
import { V5ActivePositionsPage } from './components/pages/V5ActivePositionsPage';
import { V5OrderHistoryPage } from './components/pages/V5OrderHistoryPage';
import { V5DashboardPage } from './components/pages/V5DashboardPage';
import { V5AIStatusPage } from './components/pages/V5AIStatusPage';
import { V5SignalHistoryPage } from './components/pages/V5SignalHistoryPage';
import { V5StrategyConfigPage } from './components/pages/V5StrategyConfigPage';
import { V5SettingsPage } from './components/pages/V5SettingsPage';
import { V5ManualOrderPage } from './components/pages/V5ManualOrderPage';
import { V5ChartPage } from './components/pages/V5ChartPage';
import { V5GlossaryPage } from './components/pages/V5GlossaryPage';
import { V5ReflectionPage } from './components/pages/V5ReflectionPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/v5/signals" replace />} />
        <Route path="/v5" element={<AppShell />}>
          <Route index element={<Navigate to="signals" replace />} />
          <Route path="signals"      element={<V5SignalsPage />} />
          <Route path="active"       element={<V5ActivePositionsPage />} />
          <Route path="orders"       element={<V5OrderHistoryPage />} />
          <Route path="dashboard"    element={<V5DashboardPage />} />
          <Route path="ai"           element={<V5AIStatusPage />} />
          <Route path="history"      element={<V5SignalHistoryPage />} />
          <Route path="config"       element={<V5StrategyConfigPage />} />
          <Route path="settings"     element={<V5SettingsPage />} />
          <Route path="manual"       element={<V5ManualOrderPage />} />
          <Route path="chart/:symbol" element={<V5ChartPage />} />
          <Route path="glossary"     element={<V5GlossaryPage />} />
          <Route path="reflection"   element={<V5ReflectionPage />} />
        </Route>
        <Route path="/signals"   element={<Navigate to="/v5/signals" replace />} />
        <Route path="/positions" element={<Navigate to="/v5/active" replace />} />
        <Route path="/dashboard" element={<Navigate to="/v5/dashboard" replace />} />
        <Route path="*"          element={<Navigate to="/v5/signals" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
