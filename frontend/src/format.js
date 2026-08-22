export function formatINR(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const num = Number(value)
  const sign = num < 0 ? '-' : ''
  const [wholeRaw, frac] = Math.abs(num).toFixed(2).split('.')
  let whole = wholeRaw
  if (whole.length > 3) {
    const last3 = whole.slice(-3)
    let rest = whole.slice(0, -3)
    const groups = []
    while (rest.length > 2) {
      groups.unshift(rest.slice(-2))
      rest = rest.slice(0, -2)
    }
    if (rest) groups.unshift(rest)
    whole = [...groups, last3].join(',')
  }
  return `${sign}₹${whole}.${frac}`
}

export function formatPercent(fraction, digits = 2) {
  if (fraction === null || fraction === undefined) return '—'
  return `${(Number(fraction) * 100).toFixed(digits)}%`
}

export function formatCount(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString('en-IN')
}

export function formatSeconds(seconds) {
  if (seconds === null || seconds === undefined) return '—'
  return seconds >= 0.01 ? `${seconds.toFixed(2)} sec` : `${seconds.toFixed(4)} sec`
}
