import { Boxes, Database, Globe2, HardDrive, Network, Server, Shield, type LucideIcon } from 'lucide-react'

const categoryIcons: Record<string, LucideIcon> = {
  application: Globe2,
  compute: Server,
  database: Database,
  networking: Network,
  security: Shield,
  storage: HardDrive,
}

interface ResourceIconProps {
  category?: string
  size?: number
}

export function ResourceIcon({ category, size = 18 }: ResourceIconProps) {
  const Icon = categoryIcons[category?.toLowerCase() ?? ''] ?? Boxes
  return <Icon size={size} aria-hidden="true" />
}
