import { Route, Routes } from "react-router";
import AcceptInvite from "./auth/AcceptInvite";
import Login from "./auth/Login";
import { RequireAuth } from "./auth/session";
import Picker from "./library/Picker";
import SeriesPage from "./library/SeriesPage";
import Shell from "./Shell";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/invite" element={<AcceptInvite />} />
      <Route element={<RequireAuth><Shell /></RequireAuth>}>
        <Route index element={<Picker />} />
        <Route path="series/:id" element={<SeriesPage />} />
      </Route>
    </Routes>
  );
}
