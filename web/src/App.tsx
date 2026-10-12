import { createBrowserRouter, createRoutesFromElements, Route } from "react-router";
import AcceptInvite from "./auth/AcceptInvite";
import Login from "./auth/Login";
import { RequireAuth } from "./auth/session";
import EditorPage from "./editor/EditorPage";
import SourcePage from "./editor/SourcePage";
import ImportPage from "./library/ImportPage";
import Picker from "./library/Picker";
import SeriesPage from "./library/SeriesPage";
import ProfilesPage from "./settings/ProfilesPage";
import MtSettingsPage from "./settings/MtSettingsPage";
import ShortcutsPage from "./settings/ShortcutsPage";
import Shell from "./Shell";

export const router = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/login" element={<Login />} />
      <Route path="/invite" element={<AcceptInvite />} />
      <Route element={<RequireAuth><Shell /></RequireAuth>}>
        <Route index element={<Picker />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="series/:id" element={<SeriesPage />} />
        <Route path="settings/profiles" element={<ProfilesPage />} />
        <Route path="settings/shortcuts" element={<ShortcutsPage />} />
        <Route path="settings/mt" element={<MtSettingsPage />} />
        <Route path="documents/:id" element={<EditorPage />} />
        <Route path="documents/:id/source" element={<SourcePage mode="edit" />} />
        <Route path="documents/:id/split" element={<SourcePage mode="split" />} />
      </Route>
    </>,
  ),
);
