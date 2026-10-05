import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { NextIntlClientProvider } from 'next-intl'
import { describe, expect, it, vi } from 'vitest'
import { ChannelCard } from '@/components/notifications/channel-card'
import type { NotificationSettings } from '@/lib/hooks/use-notifications'
import { SUPPORTED_LOCALES } from '@/lib/i18n/locales'

// tests/setup.ts stubs next-intl globally; this test checks the real catalog labels.
vi.unmock('next-intl')

function renderCard(locale: string, setting: NotificationSettings) {
  const notifications = JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, 'notifications.json'), 'utf8'),
  )
  return render(
    <NextIntlClientProvider locale={locale} messages={{ notifications }}>
      <ChannelCard
        setting={setting}
        onTest={() => {}}
        onToggle={() => {}}
        onDelete={() => {}}
        testing={false}
      />
    </NextIntlClientProvider>,
  )
}

const expoSetting: NotificationSettings = {
  id: 'expo-1',
  user_id: 'user-1',
  channel: 'expo_push',
  enabled: true,
  priority: 0,
  config: { push_token: 'ExponentPushToken[abc]' },
  created_at: '2026-10-05T00:00:00Z',
  updated_at: '2026-10-05T00:00:00Z',
}

describe('ChannelCard', () => {
  it('renders a channel registered by the mobile app', () => {
    renderCard('en', expoSetting)
    expect(screen.getByText('Mobile App Push')).toBeInTheDocument()
    expect(screen.getByText('Registered from the mobile app')).toBeInTheDocument()
    expect(screen.queryByText('ExponentPushToken[abc]')).not.toBeInTheDocument()
  })

  it.each(SUPPORTED_LOCALES)('labels expo_push in %s', (locale) => {
    const { container } = renderCard(locale, expoSetting)
    expect(container.textContent).not.toMatch(/notifications\.channels/)
  })
})
