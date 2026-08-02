import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Input } from '../ui/input'
import { Label } from '../ui/label'
import { Button } from '../ui/button'
import { Skeleton } from '../ui/skeleton'
import { ErrorState } from '../ui/error-state'
import { useTradingConfig, useUpdateTradingConfig } from '../../hooks/use-trading-config'

const configSchema = z.object({
  min_cash_reserve: z.number().int().min(0),
  max_risk_per_trade: z.number().int().min(0),
  low_cash_threshold: z.number().int().min(0),
  max_concurrent_positions: z.number().int().min(1).max(10),
  transaction_cost_pct: z.number().min(0).max(1),
  monthly_contribution: z.number().int().min(0),
  concentration_exit_pct: z.number().min(0).max(100),
  swing_trim_weight_pct: z.number().min(0).max(100),
  swing_trim_gain_pct: z.number().min(0).max(100),
  longterm_trim_weight_high_pct: z.number().min(0).max(100),
  longterm_trim_weight_med_pct: z.number().min(0).max(100),
  longterm_review_weight_pct: z.number().min(0).max(100),
  sector_concentration_high_pct: z.number().min(0).max(100),
  sector_concentration_med_pct: z.number().min(0).max(100),
  breakeven_gain_pct: z.number().min(0).max(100),
  half_trail_gain_pct: z.number().min(0).max(100),
  tight_trail_gain_pct: z.number().min(0).max(100),
  tight_current_floor_pct: z.number().min(0).max(100),
  tight_gain_lock_pct: z.number().min(0).max(100),
  longterm_catastrophic_pct: z.number().min(0).max(100),
  full_winrate_threshold: z.number().min(0).max(100),
  reduced_winrate_threshold: z.number().min(0).max(100),
  half_winrate_threshold: z.number().min(0).max(100),
  minimal_scale_factor: z.number().min(0).max(1),
  retro_severe_winrate: z.number().min(0).max(100),
  retro_moderate_winrate: z.number().min(0).max(100),
  retro_severe_max_entries: z.number().int().min(0).max(10),
  retro_severe_min_rr: z.number().min(0).max(20),
  retro_severe_scale: z.number().min(0).max(1),
  retro_moderate_max_entries: z.number().int().min(0).max(10),
  retro_moderate_min_rr: z.number().min(0).max(20),
})

type ConfigForm = z.infer<typeof configSchema>

type FieldDef = { name: keyof ConfigForm; label: string; desc: string; unit: string; step: string }

const SECTIONS: Array<{ title: string; desc: string; fields: FieldDef[] }> = [
  {
    title: 'Core Risk',
    desc: 'Capital protection and position sizing limits',
    fields: [
      { name: 'min_cash_reserve', label: 'Cash reserve', desc: 'Minimum cash that must never be deployed', unit: 'VND', step: '1' },
      { name: 'max_risk_per_trade', label: 'Risk per trade', desc: 'Maximum loss allowed per single trade', unit: 'VND', step: '1' },
      { name: 'low_cash_threshold', label: 'Low cash threshold', desc: 'Below this → LOW_CASH trading mode', unit: 'VND', step: '1' },
      { name: 'max_concurrent_positions', label: 'Max positions', desc: 'Maximum simultaneous open positions', unit: '#', step: '1' },
      { name: 'transaction_cost_pct', label: 'Transaction cost', desc: 'Round-trip cost (decimal, e.g. 0.003 = 0.3%)', unit: 'dec', step: '0.0001' },
      { name: 'monthly_contribution', label: 'Monthly contribution', desc: 'Maximum monthly capital addition', unit: 'VND', step: '1' },
    ],
  },
  {
    title: 'Concentration Limits',
    desc: 'Position weight thresholds for TRIM and EXIT signals',
    fields: [
      { name: 'concentration_exit_pct', label: 'Exit threshold', desc: 'Position weight above this → forced EXIT', unit: '%', step: '0.5' },
      { name: 'swing_trim_weight_pct', label: 'Swing trim weight', desc: 'Swing weight above this → TRIM', unit: '%', step: '0.5' },
      { name: 'swing_trim_gain_pct', label: 'Swing trim gain', desc: 'Swing gain above this → TRIM', unit: '%', step: '0.5' },
      { name: 'longterm_trim_weight_high_pct', label: 'Longterm trim (high)', desc: 'Longterm weight above this → aggressive TRIM', unit: '%', step: '0.5' },
      { name: 'longterm_trim_weight_med_pct', label: 'Longterm trim (medium)', desc: 'Longterm weight above this → moderate TRIM', unit: '%', step: '0.5' },
      { name: 'longterm_review_weight_pct', label: 'Review threshold', desc: 'Flag for high-concentration review', unit: '%', step: '0.5' },
      { name: 'sector_concentration_high_pct', label: 'Sector high', desc: 'Cluster above this → HIGH flag', unit: '%', step: '0.5' },
      { name: 'sector_concentration_med_pct', label: 'Sector medium', desc: 'Cluster above this → MEDIUM flag', unit: '%', step: '0.5' },
    ],
  },
  {
    title: 'Trailing Stops',
    desc: 'Gain-based stop-loss tiers for swing and long-term positions',
    fields: [
      { name: 'breakeven_gain_pct', label: 'Breakeven zone', desc: 'Up to this gain → stop at entry price', unit: '%', step: '0.5' },
      { name: 'half_trail_gain_pct', label: 'Half trail zone', desc: 'This range → trail at 50% of gain', unit: '%', step: '0.5' },
      { name: 'tight_trail_gain_pct', label: 'Tight trail zone', desc: 'Above this → tight trailing stop', unit: '%', step: '0.5' },
      { name: 'tight_current_floor_pct', label: 'Tight floor', desc: 'Floor = current × this %', unit: '%', step: '0.5' },
      { name: 'tight_gain_lock_pct', label: 'Gain lock', desc: 'Lock = entry + gain × this %', unit: '%', step: '0.5' },
      { name: 'longterm_catastrophic_pct', label: 'Longterm catastrophic', desc: 'Floor = entry × (1 − this %)', unit: '%', step: '0.5' },
    ],
  },
  {
    title: 'Win Rate Scale',
    desc: 'Position size multipliers based on recent win rate',
    fields: [
      { name: 'full_winrate_threshold', label: 'Full size', desc: 'Win rate ≥ this → 1.0× size', unit: '%', step: '1' },
      { name: 'reduced_winrate_threshold', label: 'Reduced size', desc: 'Win rate ≥ this → 0.75× size', unit: '%', step: '1' },
      { name: 'half_winrate_threshold', label: 'Half size', desc: 'Win rate ≥ this → 0.5× size', unit: '%', step: '1' },
      { name: 'minimal_scale_factor', label: 'Minimal factor', desc: 'Below half threshold → this multiplier', unit: 'x', step: '0.001' },
    ],
  },
  {
    title: 'Retro Constraints',
    desc: 'Entry quality gates applied when win rate drops — raise the bar, not shut the door',
    fields: [
      { name: 'retro_severe_winrate', label: 'Severe threshold', desc: 'Win rate below this → severe entry cap (1 entry, higher R:R)', unit: '%', step: '1' },
      { name: 'retro_moderate_winrate', label: 'Moderate threshold', desc: 'Win rate below this → moderate entry cap (2 entries, elevated R:R)', unit: '%', step: '1' },
      { name: 'retro_severe_max_entries', label: 'Severe max entries', desc: 'Max new entries allowed at severe win rate', unit: '#', step: '1' },
      { name: 'retro_severe_min_rr', label: 'Severe min R:R', desc: 'Minimum R:R required per entry at severe level', unit: 'R:R', step: '0.1' },
      { name: 'retro_severe_scale', label: 'Severe scale', desc: 'Position size multiplier at severe win rate', unit: 'x', step: '0.05' },
      { name: 'retro_moderate_max_entries', label: 'Moderate max entries', desc: 'Max new entries allowed at moderate win rate', unit: '#', step: '1' },
      { name: 'retro_moderate_min_rr', label: 'Moderate min R:R', desc: 'Minimum R:R required per entry at moderate level', unit: 'R:R', step: '0.1' },
    ],
  },
]

function ConfigSkeleton() {
  return (
    <div className="space-y-6">
      {[6, 8, 6, 4].map((count, i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-64" />
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5">
              {Array.from({ length: count }).map((_, j) => (
                <div key={j} className="space-y-1.5">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-48" />
                  <Skeleton className="h-9 w-full" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export function TradingConfigForm() {
  const { data, isLoading, error, refetch } = useTradingConfig()
  const update = useUpdateTradingConfig()
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const { register, handleSubmit, reset, formState: { isDirty, isSubmitting, errors } } =
    useForm<ConfigForm>({ resolver: zodResolver(configSchema) })

  useEffect(() => {
    if (data) reset(data)
  }, [data, reset])

  async function onSubmit(values: ConfigForm) {
    setSaveError(null)
    try {
      const result = await update.mutateAsync(values)
      reset(result)
      setSavedAt(result.updated_at)
    } catch {
      setSaveError('Failed to save. Check the console for details.')
    }
  }

  if (isLoading) return <ConfigSkeleton />
  if (error) return <ErrorState description="Could not load trading config." retry={refetch} />

  const formattedSavedAt = savedAt
    ? new Date(savedAt).toLocaleString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
      })
    : null

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      {SECTIONS.map((section) => (
        <Card key={section.title}>
          <CardHeader>
            <CardTitle className="text-sm font-semibold tracking-wide uppercase text-muted-foreground">
              {section.title}
            </CardTitle>
            <CardDescription>{section.desc}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5">
              {section.fields.map((field) => (
                <div key={field.name} className="space-y-1.5">
                  <Label htmlFor={field.name}>{field.label}</Label>
                  <p className="text-xs text-muted-foreground leading-snug">{field.desc}</p>
                  <div className="flex items-center gap-2">
                    <Input
                      id={field.name}
                      type="number"
                      step={field.step}
                      min={0}
                      className={errors[field.name] ? 'border-destructive' : ''}
                      {...register(field.name, { valueAsNumber: true })}
                    />
                    <span className="text-xs font-mono text-muted-foreground shrink-0 w-8 text-right">
                      {field.unit}
                    </span>
                  </div>
                  {errors[field.name] && (
                    <p className="text-xs text-destructive">{errors[field.name]?.message}</p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      <div className="flex items-center justify-between pt-2">
        <div className="text-xs text-muted-foreground font-mono space-y-0.5">
          {formattedSavedAt && <p>Saved {formattedSavedAt}</p>}
          {saveError && <p className="text-destructive">{saveError}</p>}
          {data?.updated_at && !formattedSavedAt && (
            <p>
              Last updated{' '}
              {new Date(data.updated_at).toLocaleString('en-GB', {
                day: '2-digit', month: 'short', year: 'numeric',
                hour: '2-digit', minute: '2-digit',
              })}
            </p>
          )}
        </div>
        <Button
          type="submit"
          disabled={!isDirty || isSubmitting}
          data-test-id="config-save-button"
        >
          {isSubmitting ? 'Saving...' : 'Save changes'}
        </Button>
      </div>
    </form>
  )
}
