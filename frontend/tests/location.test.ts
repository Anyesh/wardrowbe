import { describe, expect, it } from 'vitest'

import {
  DEFAULT_NETWORK_LOCATION_URL,
  formatReverseGeocodedLocation,
  getNetworkLocationUrl,
  getGeolocationFailureMessage,
  resolveNetworkLocation,
} from '@/lib/location'

const mockT = (key: string, params?: Record<string, string | number>) =>
  params ? `${key}:${JSON.stringify(params)}` : key

describe('location helpers', () => {
  it('uses the default network provider URL when no env override is set', () => {
    const original = process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL
    delete process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL

    expect(getNetworkLocationUrl()).toBe(DEFAULT_NETWORK_LOCATION_URL)

    if (original === undefined) {
      delete process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL
    } else {
      process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL = original
    }
  })

  it('uses the configured network provider URL when provided', () => {
    const original = process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL
    process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL = 'https://geo.example.com/json'

    expect(getNetworkLocationUrl()).toBe('https://geo.example.com/json')

    if (original === undefined) {
      delete process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL
    } else {
      process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL = original
    }
  })

  it('resolves network location with formatted city label and timezone', () => {
    const result = resolveNetworkLocation({
      success: true,
      latitude: 40.7128,
      longitude: -74.006,
      city: 'New York',
      region: 'New York',
      country: 'United States',
      timezone: { id: 'America/New_York' },
    }, 'UTC')

    expect(result).toEqual({
      lat: '40.712800',
      lon: '-74.006000',
      locationName: 'New York, New York',
      timezone: 'America/New_York',
    })
  })

  it('falls back to provided timezone when network response omits one', () => {
    const result = resolveNetworkLocation({
      success: true,
      latitude: 40.7128,
      longitude: -74.006,
    }, 'America/New_York')

    expect(result.timezone).toBe('America/New_York')
  })

  it('supports alternate provider response shapes', () => {
    const result = resolveNetworkLocation({
      latitude: 37.7749,
      longitude: -122.4194,
      city: 'San Francisco',
      region: 'California',
      country_name: 'United States',
      timezone: 'America/Los_Angeles',
    }, 'UTC')

    expect(result).toEqual({
      lat: '37.774900',
      lon: '-122.419400',
      locationName: 'San Francisco, California',
      timezone: 'America/Los_Angeles',
    })
  })

  it('throws when network location is incomplete', () => {
    expect(() => resolveNetworkLocation({ success: false }, 'UTC')).toThrow(
      'Unable to determine location from network'
    )
  })

  it('formats reverse geocoding responses consistently', () => {
    expect(formatReverseGeocodedLocation({
      address: { city: 'London', country: 'United Kingdom' },
    })).toBe('London, United Kingdom')

    expect(formatReverseGeocodedLocation({
      display_name: 'Paris, Ile-de-France, France',
    })).toBe('Paris, Ile-de-France')
  })

  it('maps geolocation failure reasons to user-facing messages', () => {
    expect(getGeolocationFailureMessage({ code: 1 }, mockT)).toBe('location.errors.geolocationDenied')
    expect(getGeolocationFailureMessage({ code: 2 }, mockT)).toBe('location.errors.geolocationUnavailable')
    expect(getGeolocationFailureMessage({ code: 3 }, mockT)).toBe('location.errors.geolocationTimeout')
    expect(getGeolocationFailureMessage({ message: 'Permission prompt dismissed' }, mockT)).toBe(
      'location.errors.geolocationFailed:{"message":"Permission prompt dismissed"}'
    )
    expect(getGeolocationFailureMessage({}, mockT)).toBe('location.errors.geolocationFailedGeneric')
  })
})
