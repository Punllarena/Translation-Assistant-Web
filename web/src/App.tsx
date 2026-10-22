import { createBrowserRouter, createRoutesFromElements, Route, Navigate } from "react-router";
import AcceptInvite from "./auth/AcceptInvite";
import Login from "./auth/Login";
import { RequireAuth, SetupGate } from "./auth/session";
import EditorPage from "./editor/EditorPage";
import SourcePage from "./editor/SourcePage";
import ImportPage from "./library/ImportPage";
import Library from "./library/Library";
import NewSeriesPage from "./library/newSeries/NewSeriesPage";
import SeriesPage from "./library/SeriesPage";
import EditorSettingsPage from "./settings/EditorSettingsPage";
import MtSettingsPage from "./settings/MtSettingsPage";
import WpSettingsPage from "./settings/WpSettingsPage";
import ShortcutsPage from "./settings/ShortcutsPage";
import StatsPage from "./stats/StatsPage";
import AdminPage from "./admin/AdminPage";
import SetupPage from "./setup/SetupPage";
import Shell from "./Shell";

export const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route element={<SetupGate />}>
        <Route path="/setup" element={<SetupPage />} />
        <Route path="/login" element={<Login />} />
        <Route path="/invite" element={<AcceptInvite />} />
        <Route element={<RequireAuth><Shell /></RequireAuth>}>
          <Route index element={<Library />} />
          <Route path="admin" element={<AdminPage />} />
          <Route path="new" element={<NewSeriesPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="series/:id" element={<SeriesPage />} />
          <Route path="settings/editor" element={<EditorSettingsPage />} />
          <Route path="settings/profiles" element={<Navigate to="/settings/editor" replace />} />
          <Route path="settings/shortcuts" element={<ShortcutsPage />} />
          <Route path="settings/mt" element={<MtSettingsPage />} />
          <Route path="settings/wp" element={<WpSettingsPage />} />
          <Route path="documents/:id" element={<EditorPage />} />
          <Route path="documents/:id/source" element={<SourcePage mode="edit" />} />
          <Route path="documents/:id/split" element={<SourcePage mode="split" />} />
        </Route>
      </Route>
    </>,
  ),
);
