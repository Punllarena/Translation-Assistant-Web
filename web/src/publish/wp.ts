const ENDPOINT_PATH = "/wp-json/ta-publisher/v1/publish";

/** The desktop wp_publisher.slugify: lowercase ASCII words joined by dashes. */
export const slugify = (text: string): string =>
  text.toLowerCase().replace(/[^a-z0-9\s-]/g, "").replace(/[-\s]+/g, "-").replace(/^-+|-+$/g, "");

/** The series TOC page: the site root plus the slug (desktop toc_page_url). */
export function tocUrl(endpoint: string, slug: string): string {
  let base = endpoint.replace(/\/+$/, "");
  if (base.endsWith(ENDPOINT_PATH)) base = base.slice(0, -ENDPOINT_PATH.length);
  return `${base}/${slug}/`;
}

/** The 409 detail for an Illustrations page already live (api/routers/wp.py ILLUSTRATIONS_LIVE);
 *  only this one asks to overwrite, not the "upload busy" 409. */
export const ILLUSTRATIONS_LIVE = "already published; publishing again overwrites the illustrations page";

export const asksOverwrite = (status: number, message: string): boolean =>
  status === 409 && message === ILLUSTRATIONS_LIVE;
