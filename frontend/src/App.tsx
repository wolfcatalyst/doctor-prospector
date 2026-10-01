import { Routes, Route, Navigate } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import Hospitals from "./pages/Hospitals";
import HospitalDetail from "./pages/HospitalDetail";
import Physicians from "./pages/Physicians";
import PhysicianDetail from "./pages/PhysicianDetail";
import Publications from "./pages/Publications";
import ExportPreview from "./pages/ExportPreview";
import Edwards from "./pages/Edwards";
import Settings from "./pages/Settings";
import Help from "./pages/Help";
import Login from "./pages/Login";

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<AppLayout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/hospitals" element={<Hospitals />} />
        <Route path="/hospitals/:siteId" element={<HospitalDetail />} />
        <Route path="/physicians" element={<Physicians />} />
        <Route path="/physicians/:npi" element={<PhysicianDetail />} />
        <Route path="/edwards" element={<Edwards />} />
        <Route path="/publications" element={<Publications />} />
        <Route path="/export" element={<ExportPreview />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/help" element={<Help />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
