export type TempUnit = 'celsius' | 'fahrenheit';

export function toF(celsius: number): number {
  return celsius * 9 / 5 + 32;
}

export function toCelsius(fahrenheit: number): number {
  return (fahrenheit - 32) * 5 / 9;
}

export function formatTemp(celsius: number, unit: TempUnit): string {
  if (unit === 'fahrenheit') {
    return `${Math.round(toF(celsius))}°F`;
  }
  return `${Math.round(celsius)}°C`;
}

export function tempSymbol(unit: TempUnit): string {
  return unit === 'fahrenheit' ? '°F' : '°C';
}

export function displayValue(celsius: number, unit: TempUnit): number {
  return unit === 'fahrenheit' ? Math.round(toF(celsius)) : Math.round(celsius);
}
