# Series Gallery tab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Gallery tab on the series page shows every image of the series (volume covers first) and lets the
user set an image as its volume's cover, move it to the Illustrations chapter, or delete it.

**Architecture:** A new router `api/routers/gallery.py` with a listing route and three image actions, built on
`api/image_moves.py` from the first plan. The SPA adds `GalleryTab.tsx`, a pure grouping module and a native
`<dialog>` viewer.

**Tech Stack:** FastAPI, SQLAlchemy 2; React 19, TanStack Query; vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-30-series-page-revision-design.md` §3. Depends on the first plan,
`2026-10-30-series-page-table.md` (Task 2's `api/image_moves.py`); build it after that plan is merged.

## Global Constraints

- Routers via `api_router()`; handlers `flush()` only; ownership via `scoped()` / `scoped_image()`; foreign ids 404.
- Image bytes are never in a listing; tiles load `GET /images/{id}` / `GET /covers/{id}` with `loading="lazy"`.
- No stored thumbnails or derived images.
- No "open in editor" action anywhere in the Gallery.
- An Illustrations chapter left with no images by a Gallery Delete or Move is deleted in the same request, then
  `arrange()`; its WordPress page is left untouched.
- Viewer is a native `<dialog>` opened with `showModal()`; confirms use `ConfirmDialog`.
- Stylesheets use tokens only.

## Review Focus

1. Set as cover on an image whose bytes are not a known raster type (an imported SVG) — refused with 415 and the
   `covers.NOT_IMAGE` message, never stored as a cover. Test in Task 1.
2. Deleting the only image of an Illustrations chapter that is the volume's only chapter — chapter deleted, volume
   kept, arrange runs without error. Test in Task 1.
3. Moving an image out of a text chapter into an Illustrations chapter that has the same file name — renamed
   (`free_name`), never dropped. Test in Task 1.
4. A series with hundreds of images — the listing stays one query without bytes. Test in Task 1 (assert `data`
   unloaded, as `tests/test_images.py` does).
5. A loose chapter's image — no Set as cover and no Move actions; the API refuses both (409/422) if called. Test in Task 1.

---

### Task 1: Gallery API

**Files:**
- Create: `api/routers/gallery.py`, `api/schemas/gallery.py`
- Modify: `api/main.py` (include the router after `images.router`), `api/image_moves.py` (add `drop_if_empty`)
- Test: `tests/test_gallery.py`

**Interfaces:**
- Consumes: `image_moves.check_can_move`, `image_moves.move_images`, `free_name`; `covers.set_cover`,
  `covers.NOT_IMAGE`; `images.scoped_image`; `api.uploads.sniff_image`; `api.library.arrange`.
- Produces:
  - `GET /series/{series_id}/images` → `list[GalleryImageOut]`:
    `GalleryImageOut { id: int; kind: Literal["image", "cover"]; volume_id: int | None; document_id: int | None; src_path: str; anchor_position: int; exclude_export: bool }`,
    ordered: volumes by `volume_order, id` (loose last), within a volume the cover first, then chapters by
    `series_order, id`, then images by `anchor_position, id`. Cover rows use the `volume_covers.id`.
  - `POST /images/{image_id}/cover` → `VolumeCoverOut` (409 `"a chapter outside a volume has no volume cover"`
    for a loose chapter; 415 `covers.NOT_IMAGE` when `sniff_image` fails; src name `cover.<ext>`).
  - `POST /images/{image_id}/move` → `204` (409 from `check_can_move`, mapped by `rule_conflict`).
  - `DELETE /images/{image_id}` → `204`.
  - `image_moves.drop_if_empty(db: Session, doc: Document) -> bool` — when `doc.is_illustrations` and it has no
    `document_images` left, delete it and `arrange()` its series; returns whether it did.

- [ ] **Step 1: Failing tests**

```python
def test_listing_orders_covers_then_chapters_then_anchors(app_client, db, gallery): ...
    # gallery fixture: V1 (cover), chapters c1 [img a anchor 2, img b anchor 0], c2 [img c]; loose chapter L [img d]
    assert [(r["kind"], r["src_path"]) for r in body] == [("cover", "cover.png"), ("image", "b.png"), ("image", "a.png"), ("image", "c.png"), ("image", "d.png")]
def test_listing_never_loads_bytes(app_client, db, gallery): ...  # as test_images.test_list_is_ordered_by_anchor_without_bytes
def test_listing_other_users_series_is_404(app_client, other_users_series_id): ...
def test_set_cover_copies_bytes(app_client, db, gallery): ...      # new volume_covers row, same bytes, cover.png; old cover row gone
def test_set_cover_refuses_svg(app_client, db, gallery): ...       # 415, cover unchanged
def test_set_cover_refuses_loose_chapter(app_client, db, gallery): ...  # 409
def test_move_renames_on_clash(app_client, db, gallery): ...       # Illustrations holds b.png; moving c1's b.png -> b-2.png
def test_move_refused_for_loose_and_syosetu(app_client, db, gallery): ...
def test_move_last_image_of_illustrations_impossible(...)          # moving out of the Illustrations chapter itself -> 409 IS_ILLUSTRATIONS
def test_delete_image(app_client, db, gallery): ...                # 204, row gone, chapter's other images intact
def test_delete_last_illustrations_image_deletes_chapter(app_client, db, gallery): ...  # chapter gone, volume kept
def test_image_actions_on_other_users_image_are_404(app_client, db, make_user, ...): ...
```

- [ ] **Step 2: Run** — `pytest tests/test_gallery.py -v` — FAIL.
- [ ] **Step 3: Implement** per Interfaces. Moving from a text chapter calls `move_images(db, user, volume, [image], order=doc.series_order)`
  then `arrange()`. Delete: remove the row, then `drop_if_empty(doc)`. Keep the module under ~400 lines.
- [ ] **Step 4: Run** — `pytest tests/test_gallery.py tests/test_image_moves.py tests/test_covers.py -v` — PASS.
- [ ] **Step 5: Commit**

```bash
cd web && npm run gen:api && cd ..
git add api/routers/gallery.py api/schemas/gallery.py api/main.py api/image_moves.py tests/test_gallery.py web/src/api/schema.d.ts
git commit -m "feat(gallery): list a series' images; set cover, move, delete"
```

---

### Task 2: Gallery tab

**Files:**
- Create: `web/src/library/gallery/galleryGroups.ts`, `galleryGroups.test.ts`, `GalleryTab.tsx`, `ImageViewer.tsx`
- Modify: `web/src/library/SeriesPage.tsx` (tab `gallery` between Volumes and Glossary), `web/src/styles/library.css`

**Interfaces:**
- Consumes: `GET /series/{id}/images` and the three actions (Task 1); `useDocuments()` for chapter titles and
  numbers; volumes from the existing series query (`VolumeOut`, `Volume.label`).
- Produces: `galleryGroups(images: GalleryImage[], docs: Doc[], volumes: Volume[], filter: number | "all"): GalleryVolume[]`
  where `GalleryVolume { key: string; label: string; cover: GalleryImage | null; chapters: { doc: Doc; heading: string; images: GalleryImage[] }[] }`,
  `heading` = `Ch. ${chapter_number} · ${shownTitle}` (no number → the title alone); "No volume" last;
  `flatten(groups): GalleryImage[]` for previous/next in the viewer.

- [ ] **Step 1: Failing vitest**

```ts
test("groups by volume with the cover first and loose chapters last", () => { /* 2 volumes + loose */ });
test("filters to one volume", () => { expect(galleryGroups(imgs, docs, vols, 7).map((g) => g.key)).toEqual(["v7"]); });
test("chapter heading without a number", () => { /* Illustrations chapter -> "Illustrations" */ });
test("flatten follows display order", () => { /* cover, then images in order */ });
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Volume filter `<select>` (All / each volume). Tiles are buttons with an `<img loading="lazy" decoding="async">`
  in a fixed square, `object-fit: cover`, CSS grid `repeat(auto-fill, minmax(140px, 1fr))`. Clicking opens
  `ImageViewer` (`showModal()`, Esc closes, ←/→ and Previous/Next buttons step through `flatten`), full image
  `object-fit: contain`. Actions for an `image` tile: **Set as volume cover** (not for loose), **Move to
  Illustrations** (not for loose, syosetu series or an image already in the Illustrations chapter), **Delete**
  (`ConfirmDialog`; when it is the last image of an Illustrations chapter the message adds "This is the last
  image; the Illustrations chapter will be deleted too."). Cover tiles: view only. After any action invalidate
  the gallery query and `invalidateLibrary`; an action's error shows in the viewer (`role="alert"`). Empty series:
  "No images in this series yet."
- [ ] **Step 4: Run** — `npx vitest run`, `npm run build` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat(series): Gallery tab"`.

---

### Task 3: E2E and docs

**Files:**
- Modify: `tools/e2e_seed.py` (series `Gallery spec`: one volume with a cover, a text chapter with two images,
  an Illustrations chapter with one), `CLAUDE.md`
- Create: `web/e2e/gallery.spec.ts`

- [ ] **Step 1: Spec**: open `?tab=gallery` → 4 tiles in order (cover first); open the second tile → Set as volume
  cover → the cover tile changes; Delete the Illustrations chapter's only image → confirm mentions the chapter →
  the Volumes tab no longer lists "Illustrations"; no button or link in the Gallery points at `/documents/`.
- [ ] **Step 2: Run** — `cd web && npm run e2e -- gallery` — PASS; then full `npm run e2e`.
- [ ] **Step 3: Docs** — `CLAUDE.md`: Gallery tab paragraph (routes, `drop_if_empty`, no thumbnails), spec path.
- [ ] **Step 4: Full check** — `ruff check .`, `pytest`, `cd web && npm test && npm run build` — PASS.
- [ ] **Step 5: Commit** — `git commit -m "test(e2e): Gallery tab; docs"`.
