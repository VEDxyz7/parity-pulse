// Generated browser reports never replace committed historical inputs.
import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
export async function diagnosticOutput(name) {
  if (!name || /[/\\]/.test(name) || name === '.' || name === '..') throw new Error('Diagnostic output must be a filename')
  const directory = new URL('../var/diagnostics/', import.meta.url)
  await mkdir(directory, { recursive: true })
  return fileURLToPath(new URL(name, directory))
}
