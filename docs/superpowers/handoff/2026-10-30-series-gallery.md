# Series Gallery tab — handover

**Branch:** `opencode/series-gallery`
**Base:** `8cc1d79` `docs(handoff): series page table plan` (tip of `opencode/series-page-table`; the branch
was created from it, not from `main`). `api/image_moves.py` was present with `free_name`, `check_can_move`
and `move_images` before Task 1.

**Commits** (`git log --oneline opencode/series-page-table..HEAD`):

```
2166df1 test(e2e): Gallery tab; docs
2ea7fc0 feat(series): Gallery tab
1a5cd09 feat(gallery): list a series' images; set cover, move, delete
```

plus this handover as its own `docs(handoff): series gallery plan` commit.

## Task 1 — Gallery API: done

Deviations:

- **`move_images` anchor rule changed** (`api/image_moves.py`). It used to set `anchor_position =
  max(original, top)`; a moved row whose anchor equalled the target's top and whose id was *lower* than the
  existing image sorted **before** it under `(anchor_position, id)`. The Gallery move test caught this
  (moving an older `b.png` into an Illustrations chapter already holding `b.png` gave `b-2.png, b.png`).
  Moved images are now numbered `top + 1, top + 2, …`, which is what both plans' "append to the end"
  wording promises. `tests/test_image_moves.py` (delete-with-move) still passes; only ordering of
  previously tied anchors could differ, and no test or caller depended on it.
- `drop_if_empty` deletes the chapter, flushes, then arranges inside itself (the plan said "delete it and
  `arrange()` its series; returns whether it did"). Callers do not arrange again.
- New test `test_delete_keeps_a_non_illustrations_chapter` (the plan's list did not name it) pins that a
  delete outside an Illustrations chapter leaves the chapter alone.
- The 409 detail for a loose chapter is the plan's exact string, held in `api/routers/gallery.py` as
  `NO_VOLUME_COVER`.
- `web/src/api/schema.d.ts` regenerated with `npm run gen:api` (needs `TA_SECRET_KEY` set; the venv's
  `python` must be on `PATH` for the npm script).

## Task 2 — Gallery tab: done

Deviations:

- **Files live under `web/src/library/gallery/`**, all four (`galleryGroups.ts`, `galleryGroups.test.ts`,
  `GalleryTab.tsx`, `ImageViewer.tsx`), not three of them directly in `library/`.
- **Volumes come from `useAllVolumes()`** filtered by `series_id` (as `VolumesTab` does). `SeriesOut` has
  no volumes, so "the existing series query" could not supply them.
- Helper exports added to `galleryGroups.ts`: `imageKey` (a cover id and an image id may collide, so the
  viewer keys on `kind-id`) and `imageSrc`.
- The viewer **closes after a successful action** (the plan only said to invalidate); the error appears in
  the viewer with `role="alert"` and is also passed into the delete `ConfirmDialog`. Cover tiles offer no
  actions, as specified.
- The delete `ConfirmDialog` renders as a sibling of the viewer `<dialog>` (both native modals; the confirm
  is on top). Arrow keys are ignored while it is open.
- Styles appended to `web/src/styles/library.css`; tokens only, no literal colours.
- Nothing in the tab links to `/documents/`; the e2e asserts both the absence of such links and of any
  "open in editor" button.

## Task 3 — E2E and docs: done

Deviations:

- The seeded `Gallery spec` series stores the same 1×1 PNG as every image (and as its cover); the e2e
  proves the cover changed by the cover tile's `src` moving to a new `/api/covers/{id}`, not by pixels.
- The e2e also asserts the `Illustrations` heading disappears and the Volumes tab has no
  "Open Illustrations" link after the delete, and that `Open Gallery chapter` is still there.
- `npm run e2e` (the whole suite) was run in addition to `npm run e2e -- gallery`, as the plan asked.

## Final results

| Check | Result |
| --- | --- |
| `ruff check .` | All checks passed |
| `pytest` (full, `TA_DATABASE_URL=…@127.0.0.1:5432/ta_test`) | 1737 collected, exit 0, no failures |
| `npm test` | 54 files, 379 tests passed |
| `npm run build` | `tsc --noEmit` + `vite build` succeeded (only the pre-existing >500 kB chunk warning) |
| `npm run e2e -- gallery` | 3 passed |
| `npm run e2e` (full) | 89 passed (2.7 m) |

The gallery e2e needs the venv's `python` on `PATH` (the Playwright web server runs
`python -m tools.e2e_seed`), and `TA_E2E_DATABASE_URL` pointing at `127.0.0.1`, not `localhost`.

## Notes for review

### Deleting the last image of an Illustrations chapter

`DELETE /images/{id}` (`api/routers/gallery.py`) loads the image through `scoped_image`, deletes and flushes
it, then calls `image_moves.drop_if_empty(db, doc)`. That function does nothing unless
`doc.is_illustrations`; otherwise it counts the chapter's remaining `document_images` and, when none is
left, deletes the `Document`, flushes and runs `arrange()` on its series. The volume stays (even when the
chapter was its only one), the response is still 204, and the chapter's WordPress illustrations page, if it
had been published, is not touched. Everything is inside the request's transaction, so a failure leaves the
chapter and its images intact.

A Gallery **move** can never empty an Illustrations chapter: `check_can_move` refuses moving *out of* it
(409 `IS_ILLUSTRATIONS`), so `drop_if_empty` is only reached through Delete. The warning in the delete
dialog ("This is the last image; the Illustrations chapter will be deleted too.") is decided client-side
from `doc.is_illustrations` and exactly one listed image of that chapter; the server applies the rule
regardless.

### Editor and EPUB export after an image is deleted from a text chapter

- **Editor:** cards come from `buildRows` (`web/src/editor/rows.ts`), which places each image before the
  line at its `anchor_position` and re-flows around whatever rows the images query returns. Deleting a row
  rewrites nothing: on the next load/refetch the card is simply absent and the surrounding lines keep their
  numbers and anchors. Cross-tab changes are not pushed (nothing in the app is), and the Gallery action
  invalidates only `["gallery", …]` and the library lists, so an editor already open in another tab keeps a
  stale card whose `/api/images/{id}` then 404s until it refetches.
- **EPUB export:** `api/routers/epub.py` (and `api/publish.py`) selects the chapter's `document_images`
  ordered by `(anchor_position, id)`; the deleted row is absent from the export and the other images keep
  their anchors, so their placement relative to the text does not change. A chapter left with no images just
  exports without them.

### Things guessed or chosen

- Volume list source (above), viewer closing on success (above), and the file location (above).
- The `move_images` anchor change (above) is the one behavioural change outside the new files; review it
  first if anything about image order surprises you.
- Tiles show every listed image, including rows with `exclude_export` (the plan lists the flag but does not
  ask to hide such images).
- The empty-state string is the plan's "No images in this series yet." even when a volume filter is what
  hides everything.
- `GalleryImageOut` is a plain pydantic model (not `from_attributes`): the listing projects columns, so no
  ORM `DocumentImage` is loaded at all and `data` is never selected (the test asserts `data` stays unloaded
  on the identity-map rows, as `tests/test_images.py` does).

### Where to read first

1. `api/routers/gallery.py` — listing order (volume rank, cover, chapter order, anchors) and the three actions.
2. `api/image_moves.py` — `drop_if_empty`, and the changed anchor assignment in `move_images`.
3. `tests/test_gallery.py` — the review-focus cases (SVG 415, last-image delete, rename on clash, tenancy 404s).
4. `web/src/library/gallery/galleryGroups.ts` + its test — grouping/filter/heading/flatten rules.
5. `web/src/library/gallery/GalleryTab.tsx` and `ImageViewer.tsx` — query, tiles, dialog, actions.
6. `web/e2e/gallery.spec.ts` and the `Gallery spec` block in `tools/e2e_seed.py`.
