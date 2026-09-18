import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const settingsSource = readFileSync(
  resolve(process.cwd(), 'app/dashboard/settings/page.tsx'),
  'utf8',
)
describe('body measurement session UX', () => {
  it('keeps measurement inputs empty and shows the last value as placeholder', () => {
    expect(settingsSource).toContain("value={measurementSession[field.key] ?? ''}")
    expect(settingsSource).toContain('placeholder={measurements[field.key] ?? placeholder}')
  })

  it('marks focused measurements active and lets an accidental activation be cleared', () => {
    expect(settingsSource).toContain('handleActivateMeasurement')
    expect(settingsSource).toContain('onFocus={() => handleActivateMeasurement(field.key)}')
    expect(settingsSource).toContain('handleDeactivateMeasurement')
    expect(settingsSource).toContain('isActive &&')
  })
})
