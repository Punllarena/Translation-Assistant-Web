import { Link } from "react-router";
import { sizeLabel, type SeriesCard } from "./shelf";

function Cover({ card }: { card: SeriesCard }) {
  return card.coverImageId != null
    ? <img className="cover" src={`/api/images/${card.coverImageId}`} alt="" loading="lazy" />
    : <span className="cover cover-tile" aria-hidden="true">{card.series.title}</span>;
}

function Progress({ value }: { value: number }) {
  return (
    <div className="prog" role="progressbar" aria-label="Translated" aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={value}><i style={{ width: `${value}%` }} /></div>
  );
}

export function Shelf({ cards }: { cards: SeriesCard[] }) {
  return (
    <ul className="shelf">
      {cards.map((c) => (
        <li key={c.series.id}>
          <Link to={`/series/${c.series.id}`} aria-label={c.series.title}>
            <Cover card={c} />
            <span className="shelf-title">{c.series.title}</span>
            <span className="muted shelf-size">{sizeLabel(c)}</span>
            <Progress value={c.progress} />
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function CompactList({ cards }: { cards: SeriesCard[] }) {
  return (
    <ul className="rows">
      <li className="row row-head muted" aria-hidden="true">
        <span /><span>Series</span><span>Size</span><span>Progress</span><span>Edited</span>
      </li>
      {cards.map((c) => (
        <li key={c.series.id} className="row">
          <Cover card={c} />
          <Link to={`/series/${c.series.id}`}>{c.series.title}</Link>
          <span className="muted">{sizeLabel(c)}</span>
          <Progress value={c.progress} />
          <span className="muted">{c.editedAt ? new Date(c.editedAt).toLocaleDateString() : "-"}</span>
        </li>
      ))}
    </ul>
  );
}
