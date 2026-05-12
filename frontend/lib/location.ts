export interface NetworkLocationApiResponse {
  success?: boolean;
  latitude?: number;
  longitude?: number;
  city?: string;
  region?: string;
  country?: string;
  country_name?: string;
  timezone?: {
    id?: string;
  } | string;
  error?: boolean;
  reason?: string;
  message?: string;
}

export interface ResolvedLocation {
  lat: string;
  lon: string;
  locationName?: string;
  timezone?: string;
}

export interface ReverseGeocodeResponse {
  address?: {
    city?: string;
    town?: string;
    village?: string;
    municipality?: string;
    country?: string;
  };
  display_name?: string;
}

export const DEFAULT_NETWORK_LOCATION_URL = 'https://ipapi.co/json/';

export function getNetworkLocationUrl(): string {
  return process.env.NEXT_PUBLIC_NETWORK_LOCATION_URL || DEFAULT_NETWORK_LOCATION_URL;
}

export function resolveNetworkLocation(
  data: NetworkLocationApiResponse,
  fallbackTimezone?: string
): ResolvedLocation {
  if (
    data.success === false ||
    data.error === true ||
    typeof data.latitude !== 'number' ||
    typeof data.longitude !== 'number'
  ) {
    throw new Error(data.reason || data.message || 'Unable to determine location from network');
  }

  const city = typeof data.city === 'string' ? data.city : '';
  const region = typeof data.region === 'string' ? data.region : '';
  const country =
    typeof data.country === 'string'
      ? data.country
      : typeof data.country_name === 'string'
        ? data.country_name
        : '';
  const labelParts = [city, region, country].filter(Boolean);
  const timezoneId =
    typeof data.timezone === 'string'
      ? data.timezone
      : data.timezone?.id;

  return {
    lat: data.latitude.toFixed(6),
    lon: data.longitude.toFixed(6),
    locationName: labelParts.length > 0 ? labelParts.slice(0, 2).join(', ') : undefined,
    timezone:
      typeof timezoneId === 'string' && timezoneId
        ? timezoneId
        : fallbackTimezone,
  };
}

export function formatReverseGeocodedLocation(
  data: ReverseGeocodeResponse
): string | undefined {
  const city =
    data.address?.city ||
    data.address?.town ||
    data.address?.village ||
    data.address?.municipality;
  const country = data.address?.country;

  if (city && country) return `${city}, ${country}`;
  if (city) return city;
  if (data.display_name) {
    return data.display_name.split(',').slice(0, 2).join(',').trim();
  }
  return undefined;
}

export function getGeolocationFailureMessage(error: {
  code?: number;
  message?: string;
}): string {
  const reasons: Record<number, string> = {
    1: 'Location access was denied.',
    2: 'Location is currently unavailable.',
    3: 'Location request timed out.',
  };

  if (typeof error.code === 'number' && reasons[error.code]) {
    return reasons[error.code];
  }
  if (error.message) {
    return `Failed to get exact location: ${error.message}`;
  }
  return 'Failed to get exact location.';
}
