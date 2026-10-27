import PageHeader from "../ui/PageHeader";
import { useMe } from "../auth/session";
import BackupPanel from "./BackupPanel";
import InvitesPanel from "./InvitesPanel";
import DictionaryPanel from "./DictionaryPanel";
import ServerSettingsForm from "./ServerSettingsForm";

export default function AdminPage() {
  const me = useMe();
  if (!me.data?.is_admin) return <main className="settings"><p className="box danger">Admin only.</p></main>;
  return (
    <main className="settings">
      <PageHeader title="Admin" subtitle="Server-wide settings, invites and dictionaries." />
      <div className="cols">
        <section className="panel sec" aria-labelledby="server-h">
          <div className="sec-head"><h2 id="server-h">Server</h2></div>
          <ServerSettingsForm />
        </section>
        <InvitesPanel />
        <DictionaryPanel />
        <BackupPanel />
      </div>
    </main>
  );
}
