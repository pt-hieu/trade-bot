import type { ComponentType } from 'react'
import type { LucideProps } from 'lucide-react'

interface SectionHeaderProps {
  icon: ComponentType<LucideProps>
  title: string
  colorClass: string
}

export function SectionHeader({ icon: Icon, title, colorClass }: SectionHeaderProps) {
  return (
    <div className="flex items-center gap-2">
      <Icon className={`h-4 w-4 ${colorClass}`} />
      <h2 className={`text-xs font-medium tracking-widest uppercase ${colorClass}`}>
        {title}
      </h2>
    </div>
  )
}
