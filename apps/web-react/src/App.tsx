import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppProvider } from './context/AppContext';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Protocols from './pages/Protocols';
import Sentiment from './pages/Sentiment';
import Swap from './pages/Swap';
import SmartRouting from './pages/SmartRouting';
import OnChain from './pages/OnChain';
import OnChainSignals from './pages/OnChainSignals';
import History from './pages/History';
import NotFound from './pages/NotFound';

function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/protocols" element={<Protocols />} />
            <Route path="/sentiment" element={<Sentiment />} />
            <Route path="/swap" element={<Swap />} />
            <Route path="/routing" element={<SmartRouting />} />
            <Route path="/history" element={<History />} />
            <Route path="/onchain" element={<OnChain />} />
            <Route path="/onchain-signals" element={<OnChainSignals />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </AppProvider>
  );
}

export default App;
