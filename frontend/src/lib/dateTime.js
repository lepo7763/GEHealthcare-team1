export function toLocalDateTime(date, time) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime()) || !time) return '';

  // Calendar dates and the selected wall-clock time belong to the log service.
  // Combining them as a JS Date would apply the browser's time zone and DST.
  const year = String(date.getFullYear()).padStart(4, '0');
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}T${time}`;
}
