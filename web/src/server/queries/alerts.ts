export const ALERTS_BASE_QUERY = `
  SELECT
    a.*,
    COALESCE(
      json_agg(
        json_build_object(
          'id', ac.id::text,
          'condition_type', ac.condition_type,
          'condition_value', ac.condition_value::float,
          'params', COALESCE(ac.params, '{}'::jsonb),
          'sort_order', ac.sort_order
        ) ORDER BY ac.sort_order
      ) FILTER (WHERE ac.id IS NOT NULL),
      '[]'::json
    ) AS conditions
  FROM alerts a
  LEFT JOIN alert_conditions ac ON ac.alert_id = a.id
`

export function parseAlertRows(rows: Record<string, unknown>[]) {
  return rows.map((row) => ({
    ...row,
    conditions: typeof row.conditions === 'string'
      ? JSON.parse(row.conditions as string)
      : (row.conditions ?? []),
  }))
}
