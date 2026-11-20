import { Link } from "react-router";
import { sizeLabel, type SeriesCard, type SeriesRow } from "./shelf";
import type { NightlyBadge } from "./nightlyStatus";

type Badges = Map<number, NightlyBadge>;

/** Last night's syosetu check: "+N new" (to the first untranslated chapter) and a warning when it failed. */
function NightlyMarks({ series, badge }: { series: SeriesRow; badge?: NightlyBadge }) {
  if (!badge && !series.syosetu_check_error) return null;
  const failed = `Nightly check failed: ${series.syosetu_check_error}`;
  return (
    <span className="nightly-marks">
      {badge && (
        <Link className="nightly-new" to={badge.href}
          title={`${badge.newChapters} new from the nightly check; opens the first untranslated chapter`}>
          +{badge.newChapters} new
        </Link>
      )}
      {series.syosetu_check_error && <span className="nightly-warn" role="img" aria-label={failed} title={failed}>⚠</span>}
    </span>
  );
}

function Cover({ card }: { card: SeriesCard }) {
  return card.coverImageId != null
    ? <img className="cover" src={`/api/covers/${card.coverImageId}`} alt="" loading="lazy" />
    : <span className="cover cover-tile" aria-hidden="true"><span>{card.series.title}</span></span>;
}

function Progress({ value }: { value: number }) {
  return (
    <div className="prog" role="progressbar" aria-label="Translated" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={value}><i style={{ width: `${value}%` }} /></div>
  );
}

export function Shelf({ cards, badges }: { cards: SeriesCard[]; badges: Badges }) {
  return (
    <ul className="shelf">
      {cards.map((c) => (
        <li key={c.series.id} className="shelf-item">
          <Link to={`/series/${c.series.id}`} aria-label={c.series.title} title={c.series.title}>
            <Cover card={c} />
            <span className="shelf-title">{c.series.title}</span>
            <span className="muted shelf-size">{sizeLabel(c)}</span>
            <Progress value={c.progress} />
          </Link>
          <NightlyMarks series={c.series} badge={badges.get(c.series.id)} />
        </li>
      ))}
    </ul>
  );
}

export function CompactList({ cards, badges }: { cards: SeriesCard[]; badges: Badges }) {
  return (
    <ul className="rows">
      <li className="row row-head muted" aria-hidden="true">
        <span /><span>Series</span><span>Size</span><span>Progress</span><span>Edited</span>
      </li>
      {cards.map((c) => (
        <li key={c.series.id} className="row">
          <Cover card={c} />
          <span className="row-title">
            <Link to={`/series/${c.series.id}`}>{c.series.title}</Link>
            <NightlyMarks series={c.series} badge={badges.get(c.series.id)} />
          </span>
          <span className="muted">{sizeLabel(c)}</span>
          <Progress value={c.progress} />
          <span className="muted">{c.editedAt ? new Date(c.editedAt).toLocaleDateString() : "-"}</span>
        </li>
      ))}
    </ul>
  );
}
