import { brandView } from "./brand";
import { useBranding } from "./useBranding";

/** The brand as every place shows it: the 訳 mark or the logo, and the name. Each caller keeps
 *  its own wrapper (`Link className="brand"` in the header, `span className="brand"` on the
 *  auth pages), so the markup stays one unit there and the rules live here.
 *
 *  The file is SiteBrand.tsx, not Brand.tsx: on a case-insensitive filesystem (Windows, the
 *  default macOS one) it would otherwise collide with brand.ts. The component is still Brand. */
export default function Brand() {
  const brand = useBranding();
  const view = brandView(brand);
  const alt = view.showName ? "" : brand.name;
  return (
    <>
      {view.showMark && <span className="mark" aria-hidden="true">訳</span>}
      {view.logo && <img className="brand-logo" src={view.logo} alt={alt} />}
      {view.logoDark && <img className="brand-logo-dark" src={view.logoDark} alt={alt} />}
      {view.showName && brand.name}
    </>
  );
}
