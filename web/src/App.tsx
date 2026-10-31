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
import SettingsLayout from "./settings/SettingsLayout";
import AdminOnly from "./settings/AdminOnly";
import { AdminBackup, AdminDictionary, AdminInvites, AdminServer } from "./settings/AdminSections";
import StatsPage from "./stats/StatsPage";
import JobsPage from "./jobs/JobsPage";
import SetupPage from "./setup/SetupPage";
import RestorePage from "./restore/RestorePage";
import Shell from "./Shell";

export const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/restore" element={<RestorePage />} />
      <Route element={<SetupGate />}>
        <Route path="/setup" element={<SetupPage />} />
        <Route path="/login" element={<Login />} />
        <Route path="/invite" element={<AcceptInvite />} />
        <Route element={<RequireAuth><Shell /></RequireAuth>}>
          <Route index element={<Library />} />
          <Route path="admin" element={<Navigate to="/settings/admin/server" replace />} />
          <Route path="new" element={<NewSeriesPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="jobs" element={<JobsPage />} />
          <Route path="series/:id" element={<SeriesPage />} />
          <Route path="settings" element={<SettingsLayout />}>
            <Route index element={<Navigate to="/settings/editor" replace />} />
            <Route path="editor" element={<EditorSettingsPage />} />
            <Route path="profiles" element={<Navigate to="/settings/editor" replace />} />
            <Route path="shortcuts" element={<ShortcutsPage />} />
            <Route path="mt" element={<MtSettingsPage />} />
            <Route path="wp" element={<WpSettingsPage />} />
            <Route path="admin" element={<Navigate to="/settings/admin/server" replace />} />
            <Route element={<AdminOnly />}>
              <Route path="admin/server" element={<AdminServer />} />
              <Route path="admin/invites" element={<AdminInvites />} />
              <Route path="admin/dictionary" element={<AdminDictionary />} />
              <Route path="admin/backup" element={<AdminBackup />} />
            </Route>
          </Route>
          <Route path="documents/:id" element={<EditorPage />} />
          <Route path="documents/:id/source" element={<SourcePage mode="edit" />} />
          <Route path="documents/:id/split" element={<SourcePage mode="split" />} />
        </Route>
      </Route>
    </>,
  ),
);
