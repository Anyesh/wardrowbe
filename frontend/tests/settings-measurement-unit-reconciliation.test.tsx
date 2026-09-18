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
    body_measurements: { waist: 101.6, shirt_size: 'M' } as Record<string, number | string | null>,
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
    mocks.userProfile.body_measurements = { waist: 101.6, shirt_size: 'M' }
    localStorage.setItem('wardrowbe_unit_system', 'metric')
  })

  it('formats stored metric measurements to one decimal without forcing a trailing zero', () => {
    mocks.userProfile.body_measurements = {
      waist: 82.34,
      weight: 83.7124,
      height: 178,
    }

    render(<SettingsPage />)

    expect(screen.getByPlaceholderText('82.3')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('83.7')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('178')).toBeInTheDocument()
  })

  it('formats stored measurements to one decimal in imperial units', () => {
    localStorage.setItem('wardrowbe_unit_system', 'imperial')
    mocks.userProfile.body_measurements = {
      waist: 82.34,
      weight: 83.7124,
    }

    render(<SettingsPage />)

    expect(screen.getByPlaceholderText('32.4')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('184.6')).toBeInTheDocument()
  })

  it('confirms a single measurement with the check button', async () => {
    mocks.userProfile.body_measurements = { weight: 83.6 }

    render(<SettingsPage />)
    const weight = screen.getByPlaceholderText('83.6')

    fireEvent.focus(weight)
    fireEvent.change(weight, { target: { value: '84.2' } })
    fireEvent.click(
      screen.getByRole('button', { name: 'body.saveMeasurements body.fields.weight' }),
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(mocks.recordMeasurements).toHaveBeenCalledTimes(1)
    expect(mocks.recordMeasurements).toHaveBeenCalledWith({ weight: 84.2 })
    expect(weight).toHaveValue(null)
    expect(weight).toHaveAttribute('placeholder', '84.2')
  })

  it('writes an activated measurement through the record mutation', async () => {
    render(<SettingsPage />)
    const waist = screen.getByPlaceholderText('101.6')

    fireEvent.focus(waist)
    fireEvent.change(waist, { target: { value: '99.5' } })
    fireEvent.click(screen.getByRole('button', { name: 'body.saveMeasurements' }))

    await act(async () => {
      await Promise.resolve()
    })

    expect(mocks.recordMeasurements).toHaveBeenCalledTimes(1)
    expect(mocks.recordMeasurements).toHaveBeenCalledWith({ waist: 99.5 })
  })

  it('renders cleared size values as empty inputs instead of the text null', () => {
    mocks.userProfile.body_measurements = { waist: 101.6, shirt_size: null }

    render(<SettingsPage />)

    expect(screen.getByPlaceholderText('body.sizePlaceholders.shirt_size')).toHaveValue('')
  })

  it('sends only clothing size fields edited in the current draft', async () => {
    mocks.userProfile.body_measurements = {
      waist: 101.6,
      shirt_size: 'M',
      pants_size: '32',
      dress_size: '40',
      shoe_size: '43',
    }

    render(<SettingsPage />)
    const shirtSize = screen.getByPlaceholderText('body.sizePlaceholders.shirt_size')
    fireEvent.change(shirtSize, { target: { value: 'L' } })
    fireEvent.click(screen.getByRole('button', { name: 'body.saveMeasurements' }))

    await act(async () => {
      await Promise.resolve()
    })

    expect(mocks.updateProfile).toHaveBeenCalledWith({
      body_measurements: { shirt_size: 'L' },
    })
  })

  it('sends an explicit null only for the clothing size field that was cleared', async () => {
    mocks.userProfile.body_measurements = {
      waist: 101.6,
      shirt_size: 'M',
      pants_size: '32',
      dress_size: '40',
      shoe_size: '43',
    }

    render(<SettingsPage />)
    const shirtSize = screen.getByPlaceholderText('body.sizePlaceholders.shirt_size')
    fireEvent.change(shirtSize, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'body.saveMeasurements' }))

    await act(async () => {
      await Promise.resolve()
    })

    expect(mocks.updateProfile).toHaveBeenCalledWith({
      body_measurements: { shirt_size: null },
    })
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
