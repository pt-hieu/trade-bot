import { useState } from 'react'
import { Target } from 'lucide-react'
import { Button } from './ui/button'
import { ConfirmDialog } from './ui/confirm-dialog'
import { EmptyState } from './ui/empty-state'
import { ErrorState } from './ui/error-state'
import { useGoals, useDeleteGoal } from '../hooks/use-goals'
import { useAllTrades } from '../hooks/use-trades'
import { GoalDialog } from './goal-dialog'
import { GoalCard } from './goals/goal-card'
import type { Goal } from '../types/index'

export function GoalsSection() {
  const { data: goals, isLoading, error, refetch } = useGoals()
  const { data: trades } = useAllTrades()
  const deleteGoal = useDeleteGoal()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [selectedGoal, setSelectedGoal] = useState<Goal | undefined>(undefined)
  const [deleteTarget, setDeleteTarget] = useState<Goal | undefined>(undefined)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const handleNewGoal = () => {
    setSelectedGoal(undefined)
    setDialogOpen(true)
  }

  const handleEditGoal = (goal: Goal) => {
    setSelectedGoal(goal)
    setDialogOpen(true)
  }

  const handleDeleteClick = (goal: Goal) => {
    setDeleteTarget(goal)
    setConfirmOpen(true)
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteGoal.mutateAsync(deleteTarget.id)
      setConfirmOpen(false)
      setDeleteTarget(undefined)
    } catch (error) {
      console.error('Failed to delete goal:', error)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button onClick={handleNewGoal}>New Goal</Button>
        </div>
        <div className="h-24 flex items-center justify-center text-muted-foreground">
          Loading goals...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button onClick={handleNewGoal}>New Goal</Button>
        </div>
        <ErrorState description="Could not load goals." retry={refetch} />
      </div>
    )
  }

  return (
    <>
      <div className="space-y-4">
        {!goals?.length ? (
          <EmptyState
            icon={Target}
            title="No goals yet"
            description="Create your first trading goal to track progress toward your monthly targets."
            action={{ label: 'New Goal', onClick: handleNewGoal }}
          />
        ) : (
          <>
            <div className="flex justify-end">
              <Button onClick={handleNewGoal}>New Goal</Button>
            </div>
            <div className="space-y-3">
              {goals.map((goal) => (
                <GoalCard
                  key={goal.id}
                  goal={goal as any}
                  trades={(trades ?? []) as any}
                  onEdit={() => handleEditGoal(goal as any)}
                  onDelete={() => handleDeleteClick(goal as any)}
                />
              ))}
            </div>
          </>
        )}
      </div>
      <GoalDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        goal={selectedGoal}
      />
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete Goal"
        description={`Are you sure you want to delete "${deleteTarget?.name}"? This action cannot be undone.`}
        confirmText="Delete"
        variant="destructive"
        onConfirm={handleConfirmDelete}
        isPending={deleteGoal.isPending}
      />
    </>
  )
}
