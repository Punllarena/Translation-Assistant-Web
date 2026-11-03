import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { api, call, type Schemas } from "../api/client";
import { clearCache, imageUrl, type Branding } from "../brand/brand";
import { invalidateBranding, useBranding } from "../brand/useBranding";
import { postForm } from "../library/upload";
import { ConfirmDialog } from "../ui/Dialog";

type Kind = "logo" | "logo_dark" | "favicon";

const LABEL: Record<Kind, string> = {
  logo: "Logo",
  logo_dark: "Dark-mode logo",
  favicon: "Favicon",
};
const ACCEPT: Record<Kind, string> = {
  logo: "image/png,image/webp,image/svg+xml",
  logo_dark: "image/png,image/webp,image/svg+xml",
  favicon: "image/png,image/webp,image/svg+xml,image/x-icon",
};
const HINT: Record<Kind, string> = {
  logo: "PNG, WebP or SVG, up to 1 MB. It replaces the 訳 mark in the header.",
  logo_dark: "Shown instead of the logo while the dark theme is on. Optional.",
  favicon: "The browser tab's icon: PNG, WebP, SVG or ICO, up to 1 MB. Without one, the 訳 mark is used.",
};

function imageId(brand: Branding, kind: Kind): number | null {
  if (kind === "logo") return brand.logoId;
  return kind === "logo_dark" ? brand.logoDarkId : brand.faviconId;
}

function clearBrowserCache(): void {
  try {
    clearCache(window.localStorage);
  } catch {
    // Blocked storage: nothing to clear.
  }
}

/** One image: a preview on its swatch, and upload / replace / remove that apply at once. */
function ImageField({ kind, brand }: { kind: Kind; brand: Branding }) {
  const queryClient = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const id = imageId(brand, kind);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return postForm<Schemas["BrandingOut"]>(`/admin/branding/${kind}`, form, "PUT");
    },
    onSuccess: () => invalidateBranding(queryClient),
  });
  const remove = useMutation({
    mutationFn: () =>
      call(api.DELETE("/admin/branding/{kind}", { params: { path: { kind } } })),
    onSuccess: () => invalidateBranding(queryClient),
  });
  const busy = upload.isPending || remove.isPending;
  const error = upload.error ?? remove.error;
  return (
    <fieldset className="brand-image" aria-busy={busy}>
      <legend>{LABEL[kind]}</legend>
      <div className="brand-image-row">
        <span className={kind === "logo_dark" ? "brand-preview dark" : "brand-preview"}>
          {id !== null ? (
            <img src={imageUrl(id)} alt={`${LABEL[kind]} preview`} />
          ) : kind === "favicon" ? (
            <img src="/favicon.svg" alt="Default favicon" />
          ) : (
            <span className="muted">{kind === "logo_dark" ? "Same as the logo" : "The 訳 mark"}</span>
          )}
        </span>
        <div className="brand-image-actions">
          <div className="toolbar">
            <button type="button" disabled={busy} onClick={() => input.current?.click()}>
              {upload.isPending ? "Uploading…" : id === null ? "Upload…" : "Replace…"}
            </button>
            {id !== null && (
              <button type="button" disabled={busy} onClick={() => remove.mutate()}>Remove</button>
            )}
          </div>
          <span className="hint">{HINT[kind]}</span>
          {error && <p className="error" role="alert">{error.message}</p>}
        </div>
      </div>
      <input ref={input} type="file" hidden accept={ACCEPT[kind]} aria-label={`Upload ${LABEL[kind]}`}
        onChange={(e) => {
          const picked = e.target.files?.[0];
          e.target.value = "";
          if (picked) upload.mutate(picked);
        }} />
    </fieldset>
  );
}

export default function BrandingPanel() {
  const queryClient = useQueryClient();
  const brand = useBranding();
  const [editedName, setEditedName] = useState<string | null>(null);
  const [editedShow, setEditedShow] = useState<boolean | null>(null);
  const [resetting, setResetting] = useState(false);
  const name = editedName ?? brand.name;
  const showName = editedShow ?? brand.showName;
  const save = useMutation({
    mutationFn: () =>
      call(api.PUT("/admin/branding", { body: { name, show_name: showName } })),
    onSuccess: (body) => {
      setEditedName(body.name);
      setEditedShow(body.show_name);
      invalidateBranding(queryClient);
    },
  });
  const reset = useMutation({
    mutationFn: () => call(api.DELETE("/admin/branding")),
    onSuccess: () => {
      clearBrowserCache();
      setEditedName(null);
      setEditedShow(null);
      invalidateBranding(queryClient);
      setResetting(false);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };
  return (
    <section className="panel sec" aria-labelledby="branding-h">
      <div className="sec-head"><h2 id="branding-h">Branding</h2></div>
      <form onSubmit={submit}>
        <label className="field"><span>Brand name</span>
          <input value={name} maxLength={60} onChange={(e) => setEditedName(e.target.value)} /></label>
        <p className="hint">Shown in the header, on the sign-in pages and in the browser tab. Leave it blank for Translation Assistant.</p>
        <label className="check">
          <input type="checkbox" checked={showName} onChange={(e) => setEditedShow(e.target.checked)} />
          Show the brand name next to the logo
        </label>
        <p className="hint">Only matters when a logo is set; without one the name always shows.</p>
        {save.error && <p className="error" role="alert">{save.error.message}</p>}
        <div className="toolbar">
          <button type="submit" className="primary" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
      <ImageField kind="logo" brand={brand} />
      <ImageField kind="logo_dark" brand={brand} />
      <ImageField kind="favicon" brand={brand} />
      <div className="toolbar">
        <button type="button" onClick={() => setResetting(true)}>Reset to default</button>
      </div>
      {resetting && (
        <ConfirmDialog title="Reset branding" confirmLabel="Reset" danger busy={reset.isPending}
          message={<>Remove the brand name, the logos and the favicon, and go back to the defaults?</>}
          error={reset.error?.message ?? null}
          onConfirm={() => reset.mutate()}
          onClose={() => { reset.reset(); setResetting(false); }} />
      )}
    </section>
  );
}
