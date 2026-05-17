import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { ProcurementAnalysis } from './pages/ProcurementAnalysis';
import { Diagnostic } from './pages/Diagnostic';
import CostRoom from './pages/CostRoom';
import { SkillsManagement } from './pages/SkillsManagement';
import { SessionHistory } from './pages/SessionHistory';
import { ExecutiveRouteGuard } from './components/Routing/ExecutiveRouteGuard';
import { ErrorBoundary } from './components/Common/ErrorBoundary';
import { useAudience } from './context/AudienceContext';

function HomeRoute() {
  const { isExecutive } = useAudience();
  if (isExecutive) return <Navigate to="/cost-room" replace />;
  return <ProcurementAnalysis />;
}

function App() {
  return (
    <ErrorBoundary>
      <Router basename="/ui">
        <ExecutiveRouteGuard>
          <Routes>
            <Route path="/" element={<HomeRoute />} />
            <Route path="/diagnostic" element={<Diagnostic />} />
            <Route path="/cost-room" element={<CostRoom />} />
            <Route path="/skills" element={<SkillsManagement />} />
            <Route path="/history" element={<SessionHistory />} />
          </Routes>
        </ExecutiveRouteGuard>
      </Router>
    </ErrorBoundary>
  );
}

export default App;
