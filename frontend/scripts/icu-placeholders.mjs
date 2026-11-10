// Collects argument names ({name}, {count, plural, ...}, {when, date, ...}). Deliberately not a
// full ICU parser: it only needs to catch placeholder drift between a source string and its
// translations. A brace opened at a plural or select's option level is branch text, so a one-word
// branch such as `=0 {Filters}` is not mistaken for an argument.
export function placeholders(value) {
  const names = new Set();
  if (typeof value !== 'string') return names;
  const stack = [];
  let i = 0;
  while (i < value.length) {
    const ch = value[i];
    if (ch === '}') {
      stack.pop();
      i++;
      continue;
    }
    if (ch !== '{') {
      i++;
      continue;
    }
    if (stack[stack.length - 1] === 'options') {
      stack.push('branch');
      i++;
      continue;
    }
    const arg = /^\{\s*([a-zA-Z0-9_]+)\s*(?:(\})|,\s*(plural|select|selectordinal)\s*,|,)/.exec(
      value.slice(i)
    );
    if (!arg) {
      stack.push('text');
      i++;
      continue;
    }
    names.add(arg[1]);
    if (!arg[2]) stack.push(arg[3] ? 'options' : 'format');
    i += arg[0].length;
  }
  return names;
}
