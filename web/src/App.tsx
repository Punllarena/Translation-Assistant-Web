import { Route, Routes } from "react-router";

export default function App() {
  return (
    <Routes>
      <Route path="*" element={<p>Translation Assistant</p>} />
    </Routes>
  );
}
