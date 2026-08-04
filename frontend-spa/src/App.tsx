import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import TestConsole from "./pages/TestConsole";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/test" element={<TestConsole />} />
        <Route path="*" element={<Navigate to="/test" replace />} />
      </Route>
    </Routes>
  );
}
