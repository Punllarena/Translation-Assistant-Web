import { Modal } from "../ui/Dialog";
import { groupActions } from "../settings/shortcutGroups";
import { ACTIONS } from "./keymap";

/** The effective keys, so a rebinding shows here at once. */
export default function KeyHelp({ bindings, onClose, onChange }: {
  bindings: Record<string, string>; onClose(): void; onChange(): void;
}) {
  return (
    <Modal title="Keyboard shortcuts" onClose={onClose}>
      <div className="dlg-head"><h2>Keyboard shortcuts</h2></div>
      <div className="dlg-body key-help">
        {groupActions(ACTIONS).map((g) => (
          <section key={g.title} aria-label={g.title}>
            <h3 className="label">{g.title}</h3>
            <dl>
              {g.actions.map((a) => (
                <div key={a.key}><dt>{a.label}</dt><dd><kbd>{bindings[a.key]}</kbd></dd></div>
              ))}
            </dl>
          </section>
        ))}
      </div>
      <div className="dlg-foot">
        <button type="button" onClick={onChange}>Change keys</button>
        <button type="button" className="primary" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
