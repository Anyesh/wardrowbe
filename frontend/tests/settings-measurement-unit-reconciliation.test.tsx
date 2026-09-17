import React from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  recordMeasurements: vi.fn(),
  updateProfile: vi.fn(),
  preferences: {},
  userProfile: {
    id: 'user-1',
    display_name: 'User',
    email: 'user@example.com',
    timezone: 'UTC',
    locale: 'en',
    role: 'user',
    onboarding_completed: true,
    body_measurements: { waist: 101.6, shirt_size: 'M' },
  },
  idleMutation: () => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn().mockResolvedValue(undefined),
    isPending: false,
  }),
}))

vi.mock('@/components/ui/slider', () => ({
  Slider: () => <div data-testid="slider" />,
}))

vi.mock('@/lib/hooks/use-preferences', () => ({
  usePreferences: () => ({ data: mocks.preferences, isLoading: false }),
  useUpdatePreferences: mocks.idleMutation,
  useResetPreferences: mocks.idleMutation,
  useTestAIEndpoint: mocks.idleMutation,
}))
vi.mock('@/lib/hooks/use-user', () => ({
  useUserProfile: () => ({ data: mocks.userProfile, isLoading: false }),
  useUpdateUserProfile: () => ({
    mutateAsync: mocks.updateProfile,
    isPending: false,
  }),
  useRecordBodyMeasurements: () => ({
    mutateAsync: mocks.recordMeasurements,
    isPending: false,
  }),
}))

vi.mock('@/lib/hooks/use-translated-constants', () => ({
  useClothingColors: () => [],
  useOccasions: () => [],
}))
import SettingsPage from '@/app/dashboard/settings/page'

describe('settings measurement unit reconciliation', () => {
  beforeEach(() => {
    mocks.recordMeasurements.mockReset()
    mocks.updateProfile.mockReset()
    mocks.updateProfile.mockResolvedValue(undefined)
    localStorage.setItem('wardrowbe_unit_system', 'metric')
  })

  it('keeps canonical semantics when units change during a pending save', async () => {
    let resolveSave!: () => void
    mocks.recordMeasurements
      .mockImplementationOnce(() => new Promise<void>((resolve) => { resolveSave = resolve }))
      .mockResolvedValueOnce(undefined)

    render(<SettingsPage />)
    const waist = screen.getByPlaceholderText('101.6')
    fireEvent.focus(waist)
    expect(waist).toHaveValue(101.6)

    fireEvent.click(screen.getByRole('button', { name: 'body.saveMeasurements' }))
    fireEvent.click(screen.getByRole('button', { name: 'body.metric' }))
    expect(waist).toHaveValue(40)
    await act(async () => {
      resolveSave()
      await Promise.resolve()
    })

    fireEvent.focus(waist)
    expect(waist).toHaveValue(40)
    fireEvent.click(screen.getByRole('button', { name: 'body.saveMeasurements' }))

    await act(async () => {
      await Promise.resolve()
    })

    expect(mocks.recordMeasurements).toHaveBeenNthCalledWith(1, { waist: 101.6 })
    expect(mocks.recordMeasurements).toHaveBeenNthCalledWith(2, { waist: 101.6 })
  })
})
