import BackupPanel from "../admin/BackupPanel";
import DictionaryPanel from "../admin/DictionaryPanel";
import InvitesPanel from "../admin/InvitesPanel";
import ServerSettingsForm from "../admin/ServerSettingsForm";
import PageHeader from "../ui/PageHeader";

/** The server panel is a bare form on the old Admin page; it gets the same panel look as the others. */
export function AdminServer() {
  return (
    <div className="settings">
      <PageHeader title="Server" subtitle="Server-wide settings, overridden from the database." />
      <section className="panel sec" aria-labelledby="server-h">
        <div className="sec-head"><h2 id="server-h">Server</h2></div>
        <ServerSettingsForm />
      </section>
    </div>
  );
}

export function AdminInvites() {
  return (
    <div className="settings">
      <PageHeader title="Invites" subtitle="Invite links let someone create an account." />
      <InvitesPanel />
    </div>
  );
}

export function AdminDictionary() {
  return (
    <div className="settings">
      <PageHeader title="Dictionary" subtitle="Glossaries JParser and MeCab look words up in." />
      <DictionaryPanel />
    </div>
  );
}

export function AdminBackup() {
  return (
    <div className="settings">
      <PageHeader title="Backup & restore" subtitle="Export this server as one file, or restore it from one." />
      <BackupPanel />
    </div>
  );
}
