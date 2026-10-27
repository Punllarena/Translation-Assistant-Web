const MIN = 12;

/** Why the backup form cannot submit, or null. The restore check comes first: while one runs,
 *  nothing about the passphrase matters. */
export function backupProblem(pass: string, repeat: string, restoring: boolean): string | null {
  if (restoring) return "A restore is in progress.";
  if (pass.length < MIN) return "Use at least 12 characters.";
  if (pass !== repeat) return "The passphrases do not match.";
  return null;
}
