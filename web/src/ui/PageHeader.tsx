import type { ReactNode } from "react";

/** A page's title block (spec §5): optional breadcrumb, serif title, muted subtitle, actions on the right. */
export default function PageHeader({ title, subtitle, crumbs, actions }: {
  title: ReactNode; subtitle?: ReactNode; crumbs?: ReactNode; actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div>
        {crumbs && <nav className="crumbs" aria-label="Breadcrumb">{crumbs}</nav>}
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
