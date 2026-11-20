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
  const errors = JSON.parse(
    readFileSync(resolve(__dirname, '..', 'messages', locale, 'errors.json'), 'utf8'),
  )
  return render(
    <NextIntlClientProvider locale={locale} messages={{ notifications, errors }}>
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
  config_error: null,
  config_error_code: null,
  config_error_params: null,
}

const rejectedEmailSetting: NotificationSettings = {
  ...expoSetting,
  id: 'email-1',
  channel: 'email',
  config: { address: 'a..b@example.com' },
  config_error: 'Value error, An email address cannot have two periods in a row.',
  config_error_code: 'INVALID_CHANNEL_CONFIG',
}

const shortTopicSetting: NotificationSettings = {
  ...expoSetting,
  id: 'ntfy-1',
  channel: 'ntfy',
  config: { topic: 'ab' },
  config_error: 'Value error, Topic must be at least 3 characters',
  config_error_code: 'NTFY_TOPIC_TOO_SHORT',
  config_error_params: { min_length: 3 },
}

describe('ChannelCard', () => {
  it('renders a channel registered by the mobile app', () => {
    renderCard('en', expoSetting)
    expect(screen.getByText('Mobile App Push')).toBeInTheDocument()
    expect(screen.getByText('Registered from the mobile app')).toBeInTheDocument()
    expect(screen.queryByText('ExponentPushToken[abc]')).not.toBeInTheDocument()
  })

  it.each([
    ['a valid channel', expoSetting, []],
    ['a channel this version rejects', rejectedEmailSetting, ['Invalid settings', "These channel settings aren't valid.", 'These settings are no longer accepted, so nothing is sent through this channel. Delete it and add it again.']],
  ] as const)('flags %s', (_case, setting, shown) => {
    const { container } = renderCard('en', setting)
    for (const text of shown) expect(screen.getByText(text)).toBeInTheDocument()
    expect(container.textContent?.includes('Invalid settings')).toBe(shown.length > 0)
  })

  it('translates the rejection reason with its params, never the English message', () => {
    const { container } = renderCard('en', shortTopicSetting)
    expect(screen.getByText('The topic must be at least 3 characters.')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/Value error/)
  })

  it('falls back to the generic reason for a code it cannot translate', () => {
    renderCard('en', { ...rejectedEmailSetting, config_error_code: 'SOMETHING_NEW' })
    expect(screen.getByText("These channel settings aren't valid.")).toBeInTheDocument()
  })

  it.each(SUPPORTED_LOCALES.flatMap((locale) => [[locale, expoSetting], [locale, rejectedEmailSetting], [locale, shortTopicSetting]] as const))(
    'labels every card text in %s',
    (locale, setting) => {
      const { container } = renderCard(locale, setting)
      expect(container.textContent).not.toMatch(/notifications\.channels|errors\.|[{]min_length[}]/)
    },
  )
})
