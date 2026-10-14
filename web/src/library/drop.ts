/** Split dropped or picked files into those with an accepted extension (case-insensitive) and the rest.
 *  A dropped folder arrives as a File without an extension, so it lands in `rejected`. */
export function acceptFiles<T extends { name: string }>(files: T[], extensions: string[]): { accepted: T[]; rejected: T[] } {
  const ok = (file: T) => extensions.some((ext) => file.name.toLowerCase().endsWith(ext.toLowerCase()));
  return { accepted: files.filter(ok), rejected: files.filter((file) => !ok(file)) };
}
