
import React, { useState } from 'react';
import Layout from './components/Layout';
import KillBoard from './components/KillBoard';
import Dashboard from './components/Dashboard';
import OrderPage from './components/OrderPage';
import PositionsPage from './components/PositionsPage';
import SettingsPage from './components/SettingsPage';
import WeightHistory from './components/WeightHistory';
import TradeScores from './components/TradeScores';
import StrategyConfig from './components/StrategyConfig';
import AIStatus from './components/AIStatus';
import { ToastContainer, useToast } from './components/Toast';
import { ViewType } from './types';

const App: React.FC = () => {
  const [activeView, setActiveView] = useState<ViewType>('KILL_BOARD');
  const { toasts, removeToast } = useToast();

  const renderView = () => {
    switch (activeView) {
      case 'KILL_BOARD':      return <KillBoard />;
      case 'DASHBOARD':       return <Dashboard />;
      case 'ORDER':           return <OrderPage />;
      case 'POSITIONS':       return <PositionsPage />;
      case 'SETTINGS':        return <SettingsPage />;
      case 'WEIGHT_HISTORY':  return <WeightHistory />;
      case 'TRADE_SCORES':    return <TradeScores />;
      case 'STRATEGY_CONFIG': return <StrategyConfig />;
      case 'AI_STATUS':       return <AIStatus />;
      default:                return <KillBoard />;
    }
  };

  return (
    <>
      <Layout activeView={activeView} onViewChange={setActiveView}>
        {renderView()}
      </Layout>
      <ToastContainer toasts={toasts} onClose={removeToast} />
    </>
  );
};

export default App;
